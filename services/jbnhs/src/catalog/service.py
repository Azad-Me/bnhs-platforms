from __future__ import annotations

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ....common.constant.qc_state_enum import QCState
from ....common.models import Issue, Page, Volume
from .schemas import (
    IssueSummary,
    PageRead,
    VolumeWithIssues,
)


class CatalogResourceNotFoundError(LookupError):
    pass


async def list_volumes_with_issues(
    session: AsyncSession,
    *,
    hide_completed_volumes: bool = False,
    hide_completed_issues: bool = False,
) -> list[VolumeWithIssues]:
    completed_count = func.coalesce(
        func.sum(
            case((Page.status == QCState.COMPLETED.value, 1), else_=0)
        ),
        0,
    )
    in_review_count = func.coalesce(
        func.sum(
            case((Page.status == QCState.IN_REVIEW.value, 1), else_=0)
        ),
        0,
    )
    result = await session.execute(
        select(
            Volume.id.label("volume_id"),
            Volume.volume_code,
            Volume.created_at.label("volume_created_at"),
            Issue.id.label("issue_id"),
            Issue.issue_code,
            Issue.master_pdf_s3_key,
            Issue.toned_pdf_s3_key,
            Issue.manifest_s3_key,
            func.count(Page.id).label("page_count"),
            completed_count.label("completed_page_count"),
            in_review_count.label("in_review_page_count"),
        )
        .outerjoin(Issue, Issue.volume_id == Volume.id)
        .outerjoin(Page, Page.issue_id == Issue.id)
        .group_by(
            Volume.id,
            Volume.volume_code,
            Volume.created_at,
            Issue.id,
            Issue.issue_code,
            Issue.master_pdf_s3_key,
            Issue.toned_pdf_s3_key,
            Issue.manifest_s3_key,
        )
        .order_by(Volume.volume_code, Issue.issue_code)
    )

    volumes: dict[int, VolumeWithIssues] = {}
    for row in result:
        volume = volumes.get(row.volume_id)
        if volume is None:
            volume = VolumeWithIssues(
                id=row.volume_id,
                volume_code=row.volume_code,
                created_at=row.volume_created_at,
                page_count=0,
                completed_page_count=0,
                in_review_page_count=0,
                unverified_page_count=0,
                completion_percent=0.0,
                issues=[],
            )
            volumes[row.volume_id] = volume
        if row.issue_id is not None:
            issue = _issue_summary(row)
            volume.page_count += issue.page_count
            volume.completed_page_count += issue.completed_page_count
            volume.in_review_page_count += issue.in_review_page_count
            volume.unverified_page_count += issue.unverified_page_count
            if not (
                hide_completed_issues
                and _is_complete(
                    issue.page_count, issue.completed_page_count
                )
            ):
                volume.issues.append(issue)

    for volume in volumes.values():
        volume.completion_percent = _completion_percent(
            volume.page_count, volume.completed_page_count
        )

    return [
        volume
        for volume in volumes.values()
        if not (
            hide_completed_volumes
            and _is_complete(volume.page_count, volume.completed_page_count)
        )
    ]


def _issue_summary(row) -> IssueSummary:
    page_count = row.page_count
    completed_page_count = row.completed_page_count
    in_review_page_count = row.in_review_page_count
    return IssueSummary(
        id=row.issue_id,
        issue_code=row.issue_code,
        master_pdf_s3_key=row.master_pdf_s3_key,
        toned_pdf_s3_key=row.toned_pdf_s3_key,
        manifest_s3_key=row.manifest_s3_key,
        page_count=page_count,
        completed_page_count=completed_page_count,
        in_review_page_count=in_review_page_count,
        unverified_page_count=(
            page_count - completed_page_count - in_review_page_count
        ),
        completion_percent=_completion_percent(
            page_count, completed_page_count
        ),
    )


def _is_complete(page_count: int, completed_page_count: int) -> bool:
    return page_count > 0 and page_count == completed_page_count


def _completion_percent(page_count: int, completed_page_count: int) -> float:
    if page_count == 0:
        return 0.0
    return round(completed_page_count * 100 / page_count, 1)


async def list_issue_pages(
    session: AsyncSession,
    issue_id: int,
) -> list[PageRead]:
    issue_exists = await session.scalar(
        select(Issue.id).where(Issue.id == issue_id)
    )
    if issue_exists is None:
        raise CatalogResourceNotFoundError("Issue not found.")
    return await _list_pages(session, issue_id)


async def list_volume_issues(
    session: AsyncSession,
    volume_id: int,
) -> list[IssueSummary]:
    volume_exists = await session.scalar(
        select(Volume.id).where(Volume.id == volume_id)
    )
    if volume_exists is None:
        raise CatalogResourceNotFoundError("Volume not found.")

    result = await session.execute(
        select(
            Issue.id.label("issue_id"),
            Issue.issue_code,
            Issue.master_pdf_s3_key,
            Issue.toned_pdf_s3_key,
            Issue.manifest_s3_key,
            func.count(Page.id).label("page_count"),
            func.coalesce(
                func.sum(
                    case(
                        (Page.status == QCState.COMPLETED.value, 1),
                        else_=0,
                    )
                ),
                0,
            ).label("completed_page_count"),
            func.coalesce(
                func.sum(
                    case(
                        (Page.status == QCState.IN_REVIEW.value, 1),
                        else_=0,
                    )
                ),
                0,
            ).label("in_review_page_count"),
        )
        .outerjoin(Page, Page.issue_id == Issue.id)
        .where(Issue.volume_id == volume_id)
        .group_by(
            Issue.id,
            Issue.issue_code,
            Issue.master_pdf_s3_key,
            Issue.toned_pdf_s3_key,
            Issue.manifest_s3_key,
        )
        .order_by(Issue.issue_code)
    )
    return [_issue_summary(row) for row in result]


async def list_volume_issue_pages(
    session: AsyncSession,
    volume_id: int,
    issue_id: int,
) -> list[PageRead]:
    issue_exists = await session.scalar(
        select(Issue.id).where(
            Issue.id == issue_id,
            Issue.volume_id == volume_id,
        )
    )
    if issue_exists is None:
        raise CatalogResourceNotFoundError(
            "Issue not found in this volume."
        )
    return await _list_pages(session, issue_id)


async def _list_pages(
    session: AsyncSession,
    issue_id: int,
) -> list[PageRead]:
    pages = await session.scalars(
        select(Page)
        .where(Page.issue_id == issue_id)
        .order_by(Page.page_number)
    )
    return [PageRead.model_validate(page) for page in pages]
