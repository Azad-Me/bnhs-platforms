from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ....common.db.dependencies import get_db_session
from ....common.responses import (
    API_ERROR_RESPONSES,
    ApiExceptionRule,
    ApiResponse,
    handle_api_exceptions,
)
from ....user_management.router import get_current_user
from .schemas import IssueSummary, PageRead, VolumeWithIssues
from .service import (
    CatalogResourceNotFoundError,
    list_issue_pages as get_issue_pages,
    list_volume_issue_pages as get_volume_issue_pages,
    list_volume_issues as get_volume_issues,
    list_volumes_with_issues as get_volumes_with_issues,
)


router = APIRouter(
    prefix="/api",
    tags=["JBNHS catalog"],
    responses=API_ERROR_RESPONSES,
    dependencies=[Depends(get_current_user)],
)


@router.get("/volumes", response_model=ApiResponse[list[VolumeWithIssues]])
async def list_volumes_with_issues(
    session: AsyncSession = Depends(get_db_session),
    hide_completed_volumes: bool = Query(default=False),
    hide_completed_issues: bool = Query(default=False),
) -> ApiResponse[list[VolumeWithIssues]]:
    volumes = await get_volumes_with_issues(
        session,
        hide_completed_volumes=hide_completed_volumes,
        hide_completed_issues=hide_completed_issues,
    )
    return ApiResponse.success(volumes)


@router.get(
    "/issues/{issue_id}/pages",
    response_model=ApiResponse[list[PageRead]],
)
@handle_api_exceptions(
    {
        CatalogResourceNotFoundError: ApiExceptionRule(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=lambda error: str(error),
        )
    }
)
async def list_issue_pages(
    issue_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[PageRead]]:
    pages = await get_issue_pages(session, issue_id)
    return ApiResponse.success(pages)


@router.get(
    "/volumes/{volume_id}/issues",
    response_model=ApiResponse[list[IssueSummary]],
)
@handle_api_exceptions(
    {
        CatalogResourceNotFoundError: ApiExceptionRule(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=lambda error: str(error),
        )
    }
)
async def list_volume_issues(
    volume_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[IssueSummary]]:
    issues = await get_volume_issues(session, volume_id)
    return ApiResponse.success(issues)


@router.get(
    "/volumes/{volume_id}/issues/{issue_id}/pages",
    response_model=ApiResponse[list[PageRead]],
)
@handle_api_exceptions(
    {
        CatalogResourceNotFoundError: ApiExceptionRule(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=lambda error: str(error),
        )
    }
)
async def list_volume_issue_pages(
    volume_id: int,
    issue_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[PageRead]]:
    pages = await get_volume_issue_pages(
        session,
        volume_id,
        issue_id,
    )
    return ApiResponse.success(pages)
