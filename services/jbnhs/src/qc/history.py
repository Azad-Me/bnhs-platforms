from __future__ import annotations

from datetime import datetime, timezone
from difflib import unified_diff
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ....common.constant import (
    AccessLevel,
    AssignmentStatus,
    QCState,
    ReviewDecision,
)
from ....common.models import Assignment, Page, Revision, Review, User
from .schemas import (
    RevisionComparisonRead,
    RevisionDocumentRead,
    RevisionHistoryItem,
    RevisionReviewEvent,
)
from .service import (
    PageNotFoundError,
    _extract_ocr_text,
    _extract_revision_document,
    _extract_revision_text,
    _read_json_object,
)


class RevisionAccessDeniedError(PermissionError):
    pass


class RevisionNotFoundError(LookupError):
    pass


class RevisionConflictError(ValueError):
    pass


async def list_page_revisions(
    session: AsyncSession,
    *,
    page_id: int,
    user: User,
) -> list[RevisionHistoryItem]:
    page = await _authorized_page(session, page_id=page_id, user=user)
    query = (
        select(Revision)
        .options(selectinload(Revision.saved_by_user))
        .where(Revision.page_id == page_id)
        .order_by(Revision.saved_at, Revision.id)
    )
    if _role(user) == AccessLevel.QC_USER.value:
        query = query.where(Revision.saved_by == user.id)

    revisions = list(await session.scalars(query))
    review_events_by_revision: dict[int, list[RevisionReviewEvent]] = {}
    if revisions:
        reviews = await session.scalars(
            select(Review)
            .join(Revision, Review.revision_id == Revision.id)
            .options(selectinload(Review.reviewer))
            .where(
                Revision.page_id == page_id,
                Review.decision.in_(
                    (
                        ReviewDecision.SUBMITTED.value,
                        ReviewDecision.SENT_BACK.value,
                        ReviewDecision.APPROVED.value,
                    )
                ),
            )
            .order_by(Review.reviewed_at, Review.id)
        )
        for review in reviews:
            review_events_by_revision.setdefault(review.revision_id, []).append(
                RevisionReviewEvent(
                    decision=review.decision,
                    actor_id=review.reviewer_id,
                    actor_name=review.reviewer.name,
                    note=review.note,
                    acted_at=review.reviewed_at,
                )
            )

    result: list[RevisionHistoryItem] = []
    if page.ocr_s3_key:
        result.append(
            RevisionHistoryItem(
                id=None,
                page_id=page.id,
                based_on_revision_id=None,
                saved_at=page.created_at,
                saved_by=None,
                author_name="OCR import",
                source="ocr",
                is_approved=False,
            )
        )
    result.extend(
        RevisionHistoryItem(
            id=revision.id,
            page_id=revision.page_id,
            based_on_revision_id=revision.based_on_revision_id,
            saved_at=revision.saved_at,
            saved_by=revision.saved_by,
            author_name=revision.saved_by_user.name,
            source="revision",
            is_approved=page.current_approved_revision_id == revision.id,
            review_events=review_events_by_revision.get(revision.id, []),
        )
        for revision in revisions
    )
    return result


async def read_page_revision(
    session: AsyncSession,
    *,
    page_id: int,
    revision_id: int,
    user: User,
    s3_client: Any,
    bucket: str,
) -> RevisionDocumentRead:
    await _authorized_page(session, page_id=page_id, user=user)
    revision = await _get_revision(
        session,
        page_id=page_id,
        revision_id=revision_id,
        user=user,
    )
    document = _read_json_object(
        s3_client,
        bucket=bucket,
        key=revision.s3_key,
    )
    structured_document = _extract_revision_document(document)
    corrected_text = (
        _extract_ocr_text(structured_document)
        if structured_document is not None
        else _extract_revision_text(document)
    )
    return RevisionDocumentRead(
        id=revision.id,
        page_id=revision.page_id,
        based_on_revision_id=revision.based_on_revision_id,
        saved_at=revision.saved_at,
        saved_by=revision.saved_by,
        author_name=revision.saved_by_user.name,
        corrected_text=corrected_text,
        document=structured_document,
    )


async def compare_page_revisions(
    session: AsyncSession,
    *,
    page_id: int,
    revision_id: int,
    against_revision_id: int | None,
    user: User,
    s3_client: Any,
    bucket: str,
) -> RevisionComparisonRead:
    page = await _authorized_page(session, page_id=page_id, user=user)
    target_revision = await _get_revision(
        session,
        page_id=page_id,
        revision_id=revision_id,
        user=user,
    )
    if against_revision_id == revision_id:
        raise RevisionConflictError("A revision cannot be compared with itself.")

    target_text = _load_revision_text(
        s3_client, bucket=bucket, key=target_revision.s3_key
    )
    if against_revision_id is None:
        base_source = "ocr"
        base_text = ""
        if page.ocr_s3_key:
            base_document = _read_json_object(
                s3_client, bucket=bucket, key=page.ocr_s3_key
            )
            base_text = _extract_ocr_text(base_document)
    else:
        base_source = "revision"
        base_revision = await _get_revision(
            session,
            page_id=page_id,
            revision_id=against_revision_id,
            user=user,
        )
        base_text = _load_revision_text(
            s3_client, bucket=bucket, key=base_revision.s3_key
        )

    diff = list(
        unified_diff(
            base_text.splitlines(),
            target_text.splitlines(),
            fromfile=(
                "OCR import"
                if against_revision_id is None
                else f"revision {against_revision_id}"
            ),
            tofile=f"revision {revision_id}",
            lineterm="",
        )
    )
    return RevisionComparisonRead(
        page_id=page_id,
        revision_id=revision_id,
        against_revision_id=against_revision_id,
        base_source=base_source,
        added_lines=sum(
            line.startswith("+") and not line.startswith("+++")
            for line in diff
        ),
        removed_lines=sum(
            line.startswith("-") and not line.startswith("---")
            for line in diff
        ),
        unified_diff=diff,
    )


async def _authorized_page(
    session: AsyncSession,
    *,
    page_id: int,
    user: User,
) -> Page:
    page = await session.scalar(select(Page).where(Page.id == page_id))
    if page is None:
        raise PageNotFoundError("Page not found.")

    if _role(user) == AccessLevel.QC_USER.value:
        if QCState(page.status) in {QCState.IN_REVIEW, QCState.COMPLETED}:
            raise RevisionAccessDeniedError(
                "QC users cannot read revision history for this page."
            )
        now = datetime.now(timezone.utc)
        active_claim = await session.scalar(
            select(Assignment)
            .where(
                Assignment.page_id == page_id,
                Assignment.status == AssignmentStatus.ACTIVE.value,
                Assignment.lock_expires_at > now,
            )
            .order_by(Assignment.assigned_at.desc(), Assignment.id.desc())
            .limit(1)
        )
        if active_claim is not None and active_claim.user_id != user.id:
            raise RevisionConflictError(
                "Page is actively claimed by another user."
            )
    return page


async def _get_revision(
    session: AsyncSession,
    *,
    page_id: int,
    revision_id: int,
    user: User,
) -> Revision:
    query = (
        select(Revision)
        .options(selectinload(Revision.saved_by_user))
        .where(Revision.page_id == page_id, Revision.id == revision_id)
    )
    if _role(user) == AccessLevel.QC_USER.value:
        query = query.where(Revision.saved_by == user.id)
    revision = await session.scalar(query)
    if revision is None:
        raise RevisionNotFoundError("Revision not found.")
    return revision


def _load_revision_text(s3_client: Any, *, bucket: str, key: str) -> str:
    document = _read_json_object(s3_client, bucket=bucket, key=key)
    structured_document = _extract_revision_document(document)
    return (
        _extract_ocr_text(structured_document)
        if structured_document is not None
        else _extract_revision_text(document)
    )


def _role(user: User) -> str:
    return user.level.strip().casefold()
