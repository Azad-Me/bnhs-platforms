from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ....common.db.dependencies import get_db_session
from ....common.models import Issue, Page, User, Volume
from ....user_management.router import get_current_user
from .schemas import IssueSummary, PageRead, VolumeWithIssues


router = APIRouter(prefix="/api", tags=["JBNHS catalog"])


@router.get("/volumes", response_model=list[VolumeWithIssues])
async def list_volumes_with_issues(
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(get_current_user),
) -> list[VolumeWithIssues]:
    result = await session.execute(
        select(
            Volume.id.label("volume_id"),
            Volume.volume_code,
            Volume.created_at.label("volume_created_at"),
            Issue.id.label("issue_id"),
            Issue.issue_code,
            Issue.issue_s3_key,
            Issue.manifest_s3_key,
            func.count(Page.id).label("page_count"),
        )
        .outerjoin(Issue, Issue.volume_id == Volume.id)
        .outerjoin(Page, Page.issue_id == Issue.id)
        .group_by(
            Volume.id,
            Volume.volume_code,
            Volume.created_at,
            Issue.id,
            Issue.issue_code,
            Issue.issue_s3_key,
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
                issues=[],
            )
            volumes[row.volume_id] = volume
        if row.issue_id is not None:
            volume.issues.append(
                IssueSummary(
                    id=row.issue_id,
                    issue_code=row.issue_code,
                    issue_s3_key=row.issue_s3_key,
                    manifest_s3_key=row.manifest_s3_key,
                    page_count=row.page_count,
                )
            )
    return list(volumes.values())


@router.get(
    "/issues/{issue_id}/pages",
    response_model=list[PageRead],
)
async def list_issue_pages(
    issue_id: int,
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(get_current_user),
) -> list[PageRead]:
    issue_exists = await session.scalar(
        select(Issue.id).where(Issue.id == issue_id)
    )
    if issue_exists is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Issue not found.",
        )

    pages = await session.scalars(
        select(Page)
        .where(Page.issue_id == issue_id)
        .order_by(Page.page_number)
    )
    return [PageRead.model_validate(page) for page in pages]


@router.get(
    "/volumes/{volume_id}/issues",
    response_model=list[IssueSummary],
)
async def list_volume_issues(
    volume_id: int,
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(get_current_user),
) -> list[IssueSummary]:
    volume_exists = await session.scalar(
        select(Volume.id).where(Volume.id == volume_id)
    )
    if volume_exists is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Volume not found.",
        )

    result = await session.execute(
        select(
            Issue.id.label("issue_id"),
            Issue.issue_code,
            Issue.issue_s3_key,
            Issue.manifest_s3_key,
            func.count(Page.id).label("page_count"),
        )
        .outerjoin(Page, Page.issue_id == Issue.id)
        .where(Issue.volume_id == volume_id)
        .group_by(
            Issue.id,
            Issue.issue_code,
            Issue.issue_s3_key,
            Issue.manifest_s3_key,
        )
        .order_by(Issue.issue_code)
    )
    return [
        IssueSummary(
            id=row.issue_id,
            issue_code=row.issue_code,
            issue_s3_key=row.issue_s3_key,
            manifest_s3_key=row.manifest_s3_key,
            page_count=row.page_count,
        )
        for row in result
    ]


@router.get(
    "/volumes/{volume_id}/issues/{issue_id}/pages",
    response_model=list[PageRead],
)
async def list_volume_issue_pages(
    volume_id: int,
    issue_id: int,
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(get_current_user),
) -> list[PageRead]:
    issue_exists = await session.scalar(
        select(Issue.id).where(
            Issue.id == issue_id,
            Issue.volume_id == volume_id,
        )
    )
    if issue_exists is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Issue not found in this volume.",
        )

    pages = await session.scalars(
        select(Page)
        .where(Page.issue_id == issue_id)
        .order_by(Page.page_number)
    )
    return [PageRead.model_validate(page) for page in pages]
