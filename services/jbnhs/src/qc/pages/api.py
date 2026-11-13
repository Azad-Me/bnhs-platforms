from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from .....common.cloud import S3Resource
from .....common.constant.access_level_enum import AccessLevel
from .....common.constant.qc_state_enum import QCState
from .....common.db.dependencies import get_db_session
from .....common.models import User
from .....common.responses import API_ERROR_RESPONSES, ApiExceptionRule, ApiResponse, handle_api_exceptions
from .....user_management.router import get_current_user
from .schemas import QCPageRead
from .service import PageAssetFormatError, PageAssetUnavailableError, PageNotFoundError, get_qc_page


router = APIRouter(
    prefix="/api",
    tags=["qc"],
    responses=API_ERROR_RESPONSES,
    dependencies=[Depends(get_current_user)],
)


@router.get("/pages/{page_id}", response_model=ApiResponse[QCPageRead])
@handle_api_exceptions(
    {
        PageNotFoundError: ApiExceptionRule(404, lambda error: str(error)),
        PageAssetUnavailableError: ApiExceptionRule(502, lambda error: str(error)),
        PageAssetFormatError: ApiExceptionRule(502, lambda error: str(error)),
    }
)
async def read_qc_page(
    page_id: int,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> ApiResponse[QCPageRead]:
    s3_resource = S3Resource()
    try:
        page = await get_qc_page(
            session,
            page_id=page_id,
            user_id=user.id,
            revision_owner_id=(
                user.id
                if user.level.strip().casefold() == AccessLevel.QC_USER.value
                else None
            ),
            s3_client=s3_resource.client,
            bucket=os.environ.get("S3_BUCKET", "bnhs-jbnhs-archive"),
        )
        if user.level.strip().casefold() == AccessLevel.QC_USER.value:
            if page.claim.is_claimed and not page.claim.claimed_by_me:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Page is actively claimed by another user.",
                )
            if page.status in {QCState.IN_REVIEW, QCState.COMPLETED}:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="QC users cannot open pages in review or completed states.",
                )
        return ApiResponse.success(page)
    finally:
        s3_resource.close()
