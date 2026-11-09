from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ....common.constant import (
    AccessLevel,
    AssignmentStatus,
    QCState,
    ReviewAction,
    ReviewDecision,
)
from ....common.models import (
    ApprovedPage,
    Assignment,
    Page,
    Revision,
    Review,
    User,
)
from .schemas import PageReviewActionRead


class PageNotFoundError(LookupError):
    pass


class WorkflowAccessDeniedError(PermissionError):
    pass


class WorkflowStateConflictError(ValueError):
    pass


class WorkflowClaimRequiredError(ValueError):
    pass


class WorkflowDraftRequiredError(ValueError):
    pass


async def submit_page_for_review(
    session: AsyncSession,
    *,
    page_id: int,
    user: User,
) -> PageReviewActionRead:
    
    page = await _lock_page(session, page_id)
    if QCState(page.status) != QCState.IN_PROGRESS:
        raise WorkflowStateConflictError(
            "Only an in-progress page can be submitted for review."
        )

    now = datetime.now(timezone.utc)
    assignment = await session.scalar(
        select(Assignment)
        .where(
            Assignment.page_id == page_id,
            Assignment.user_id == user.id,
            Assignment.status == AssignmentStatus.ACTIVE.value,
            Assignment.lock_expires_at > now,
        )
        .order_by(Assignment.assigned_at.desc(), Assignment.id.desc())
        .limit(1)
        .with_for_update()
    )
    if assignment is None:
        raise WorkflowClaimRequiredError(
            "An active page claim is required to submit for review."
        )

    revision = await session.scalar(
        select(Revision)
        .where(
            Revision.page_id == page_id,
            Revision.saved_by == user.id,
        )
        .order_by(Revision.saved_at.desc(), Revision.id.desc())
        .limit(1)
    )
    if revision is None:
        raise WorkflowDraftRequiredError(
            "Save a draft revision before submitting for review."
        )

    page.status = QCState.IN_REVIEW.value
    page.updated_at = now
    assignment.status = AssignmentStatus.RELEASED.value
    assignment.lock_expires_at = None
    assignment.updated_at = now
    session.add(
        Review(
            revision_id=revision.id,
            reviewer_id=user.id,
            decision=ReviewDecision.SUBMITTED.value,
            reviewed_at=now,
        )
    )
    await session.flush()
    return PageReviewActionRead(
        page_id=page_id,
        status=QCState.IN_REVIEW,
        revision_id=revision.id,
        actor_id=user.id,
        decision=ReviewDecision.SUBMITTED,
        note=None,
        acted_at=now,
    )


async def decide_page_review(
    session: AsyncSession,
    *,
    page_id: int,
    user: User,
    decision: ReviewAction,
    note: str | None,
) -> PageReviewActionRead:
    if _role(user) not in {
        AccessLevel.ADMIN.value,
        AccessLevel.PUBLISHER.value,
    }:
        raise WorkflowAccessDeniedError(
            "Only Admins and Publishers can decide page reviews."
        )
    if decision not in {ReviewAction.SEND_BACK, ReviewAction.APPROVE}:
        raise WorkflowStateConflictError("Unsupported review decision.")
    if decision == ReviewAction.SEND_BACK and not (note or "").strip():
        raise WorkflowStateConflictError(
            "A non-empty note is required when sending back."
        )

    page = await _lock_page(session, page_id)
    if QCState(page.status) != QCState.IN_REVIEW:
        raise WorkflowStateConflictError(
            "Only a page in review can receive a reviewer decision."
        )

    submission = await session.scalar(
        select(Review)
        .join(Revision, Review.revision_id == Revision.id)
        .where(
            Revision.page_id == page_id,
            Review.decision == ReviewDecision.SUBMITTED.value,
        )
        .order_by(Review.reviewed_at.desc(), Review.id.desc())
        .limit(1)
        .with_for_update()
    )
    if submission is None:
        raise WorkflowStateConflictError(
            "The in-review page has no recorded submission."
        )

    now = datetime.now(timezone.utc)
    stored_decision = (
        ReviewDecision.SENT_BACK
        if decision == ReviewAction.SEND_BACK
        else ReviewDecision.APPROVED
    )
    session.add(
        Review(
            revision_id=submission.revision_id,
            reviewer_id=user.id,
            decision=stored_decision.value,
            note=note,
            reviewed_at=now,
        )
    )

    if decision == ReviewAction.SEND_BACK:
        page.status = QCState.NEEDS_CHANGES.value
        page.updated_at = now
        assignments = await session.scalars(
            select(Assignment)
            .where(
                Assignment.page_id == page_id,
                Assignment.status == AssignmentStatus.ACTIVE.value,
            )
            .with_for_update()
        )
        for assignment in assignments:
            assignment.status = AssignmentStatus.RELEASED.value
            assignment.lock_expires_at = None
            assignment.updated_at = now
    else:
        page.status = QCState.COMPLETED.value
        page.updated_at = now
        page.current_approved_revision_id = submission.revision_id
        approved_page = await session.scalar(
            select(ApprovedPage)
            .where(ApprovedPage.page_id == page_id)
            .with_for_update()
        )
        if approved_page is None:
            session.add(
                ApprovedPage(
                    page_id=page_id,
                    revision_id=submission.revision_id,
                    approved_by=user.id,
                    approved_at=now,
                )
            )
        else:
            approved_page.revision_id = submission.revision_id
            approved_page.approved_by = user.id
            approved_page.approved_at = now
            approved_page.updated_at = now

    await session.flush()
    return PageReviewActionRead(
        page_id=page_id,
        status=QCState(page.status),
        revision_id=submission.revision_id,
        actor_id=user.id,
        decision=stored_decision,
        note=note,
        acted_at=now,
    )


async def _lock_page(session: AsyncSession, page_id: int) -> Page:
    page = await session.scalar(
        select(Page).where(Page.id == page_id).with_for_update()
    )
    if page is None:
        raise PageNotFoundError("Page not found.")
    return page


def _role(user: User) -> str:
    return user.level.strip().casefold()
