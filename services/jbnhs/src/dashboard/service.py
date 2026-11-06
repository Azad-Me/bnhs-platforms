from __future__ import annotations

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ....common.constant.qc_state_enum import QCState
from ....common.models import Issue, Page, Volume
from .schemas import DashboardSummary


async def get_dashboard_summary(session: AsyncSession) -> DashboardSummary:
    page_count = func.count(Page.id)
    completed_count = func.coalesce(
        func.sum(case((Page.status == QCState.COMPLETED.value, 1), else_=0)),
        0,
    )
    in_review_count = func.coalesce(
        func.sum(case((Page.status == QCState.IN_REVIEW.value, 1), else_=0)),
        0,
    )
    row = (
        await session.execute(
            select(
                func.count(func.distinct(Volume.id)).label("volume_count"),
                func.count(func.distinct(Issue.id)).label("issue_count"),
                page_count.label("page_count"),
                completed_count.label("completed_page_count"),
                in_review_count.label("in_review_page_count"),
            )
            .select_from(Volume)
            .outerjoin(Issue, Issue.volume_id == Volume.id)
            .outerjoin(Page, Page.issue_id == Issue.id)
        )
    ).one()
    total_pages = row.page_count
    completed_pages = row.completed_page_count
    in_review_pages = row.in_review_page_count
    return DashboardSummary(
        volume_count=row.volume_count,
        issue_count=row.issue_count,
        page_count=total_pages,
        completed_page_count=completed_pages,
        in_review_page_count=in_review_pages,
        unverified_page_count=total_pages - completed_pages - in_review_pages,
        completion_percent=(
            round(completed_pages * 100 / total_pages, 1)
            if total_pages
            else 0.0
        ),
    )
