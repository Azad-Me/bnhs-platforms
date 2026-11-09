from __future__ import annotations

import os

from fastapi import APIRouter, Body, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from ....common.cloud import S3Resource
from ....common.constant.access_level_enum import AccessLevel
from ....common.db.dependencies import get_db_session
from ....common.models import User
from ....common.responses import (
    API_ERROR_RESPONSES,
    ApiExceptionRule,
    ApiResponse,
    handle_api_exceptions,
)
from ....user_management.router import require_role
from .schemas import StitchIssueRead, StitchIssueRequest
from .stitch import (
    StitchingError,
    StitchIssueNotFoundError,
    StitchIssueNotReadyError,
    stitch_issue,
)


router = APIRouter(
    prefix="/api",
    tags=["stitching"],
    responses=API_ERROR_RESPONSES,
)


@router.post(
    "/issues/{issue_id}/stitch",
    response_model=ApiResponse[StitchIssueRead],
)
@handle_api_exceptions(
    {
        StitchIssueNotFoundError: ApiExceptionRule(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=lambda error: str(error),
        ),
        StitchIssueNotReadyError: ApiExceptionRule(
            status_code=status.HTTP_409_CONFLICT,
            detail=lambda error: str(error),
        ),
        StitchingError: ApiExceptionRule(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=lambda error: str(error),
            log_message="Issue PDF stitching failed",
        ),
    }
)
async def stitch_issue_pdf(
    issue_id: int,
    request: StitchIssueRequest | None = Body(default=None),
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(
        require_role(AccessLevel.ADMIN, AccessLevel.PUBLISHER)
    ),
) -> ApiResponse[StitchIssueRead]:
    s3_resource = S3Resource()
    try:
        result = await stitch_issue(
            session,
            issue_id=issue_id,
            s3_client=s3_resource.client,
            bucket=os.environ.get("S3_BUCKET", "bnhs-jbnhs-archive"),
            text_mode=(request or StitchIssueRequest()).text_mode,
        )
        return ApiResponse.success(
            StitchIssueRead(
                issue_id=result.issue_id,
                page_count=result.page_count,
                filename=result.filename,
                download_url=result.download_url,
                download_url_expires_in=result.download_url_expires_in,
                text_mode=result.text_mode,
            )
        )
    finally:
        s3_resource.close()
