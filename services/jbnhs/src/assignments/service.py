from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ....common.constant.qc_state_enum import QCState
from ....common.models import Assignment, Page, Revision, User
from .schemas import PageClaimRead


CLAIM_TTL = timedelta(minutes=30)
ACTIVE_ASSIGNMENT_STATUS = "active"
_RELEASED_ASSIGNMENT = "released"
_EXPIRED_ASSIGNMENT = "expired"


class PageNotFoundError(LookupError):
    pass


class PageClaimedError(ValueError):
    pass


class PageClaimRequiredError(ValueError):
    pass


class PageStateConflictError(ValueError):
    pass


async def claim_page(
    session: AsyncSession,
    *,
    page_id: int,
    user: User,
) -> PageClaimRead:
    page = await _lock_page(session, page_id)
    now = datetime.now(timezone.utc)
    assignments = await _active_assignments(session, page.id)
    state = QCState(page.status)
    if state not in {
        QCState.UNVERIFIED,
        QCState.IN_PROGRESS,
        QCState.NEEDS_CHANGES,
    }:
        raise PageStateConflictError(
            f"A page in the {state.value} state cannot be claimed."
        )

    active_assignment = None
    for assignment in assignments:
        if (
            assignment.lock_expires_at is not None
            and assignment.lock_expires_at > now
        ):
            if assignment.user_id != user.id:
                raise PageClaimedError(
                    "Page is actively claimed by another user."
                )
            if active_assignment is None:
                active_assignment = assignment
        else:
            assignment.status = _EXPIRED_ASSIGNMENT

    expires_at = now + CLAIM_TTL
    if active_assignment is None:
        active_assignment = Assignment(
            page_id=page.id,
            user_id=user.id,
            status=ACTIVE_ASSIGNMENT_STATUS,
        )
        session.add(active_assignment)

    page.status = QCState.IN_PROGRESS.value
    active_assignment.lock_expires_at = expires_at
    await session.flush()
    return PageClaimRead(
        page_id=page.id,
        status=QCState.IN_PROGRESS,
        lock_expires_at=expires_at,
    )


async def release_page_claim(
    session: AsyncSession,
    *,
    page_id: int,
    user_id: int,
    release_any_claim: bool = False,
) -> None:
    page = await _lock_page(session, page_id)
    assignments = await _active_assignments(session, page.id)
    now = datetime.now(timezone.utc)
    assignment = next(
        (
            candidate
            for candidate in assignments
            if candidate.lock_expires_at is not None
            and candidate.lock_expires_at > now
            and (candidate.user_id == user_id or release_any_claim)
        ),
        None,
    )
    if assignment is None:
        raise PageClaimRequiredError("There is no active claim to release.")

    assignment.status = _RELEASED_ASSIGNMENT
    if QCState(page.status) == QCState.IN_PROGRESS:
        has_draft = await session.scalar(
            select(Revision.id)
            .where(
                Revision.page_id == page.id,
                Revision.saved_by == assignment.user_id,
            )
            .limit(1)
        )
        page.status = (
            QCState.NEEDS_CHANGES.value
            if has_draft is not None
            else QCState.UNVERIFIED.value
        )


async def _lock_page(session: AsyncSession, page_id: int) -> Page:
    page = await session.scalar(
        select(Page).where(Page.id == page_id).with_for_update()
    )
    if page is None:
        raise PageNotFoundError("Page not found.")
    return page


async def _active_assignments(
    session: AsyncSession,
    page_id: int,
) -> list[Assignment]:
    result = await session.scalars(
        select(Assignment)
        .where(
            Assignment.page_id == page_id,
            Assignment.status == ACTIVE_ASSIGNMENT_STATUS,
        )
        .order_by(Assignment.assigned_at.desc(), Assignment.id.desc())
        .with_for_update()
    )
    return list(result)
