from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ....common.cloud import S3Resource
from ....common.constant.access_level_enum import AccessLevel
from ....common.constant.qc_state_enum import QCState
from ....common.db.dependencies import get_db_session
from ....common.models import User
from ....common.responses import (
    API_ERROR_RESPONSES,
    ApiExceptionRule,
    ApiResponse,
    handle_api_exceptions,
)
from ....user_management.router import get_current_user, require_role
from .schemas import (
    PageRevisionRead,
    QCPageRead,
    RevisionComparisonRead,
    RevisionDocumentRead,
    RevisionHistoryItem,
    SaveRevisionRequest,
)
from .history import (
    RevisionAccessDeniedError,
    RevisionConflictError as HistoryRevisionConflictError,
    RevisionNotFoundError,
    compare_page_revisions,
    list_page_revisions,
    read_page_revision,
)
from .service import (
    PageAssetFormatError,
    PageAssetUnavailableError,
    PageNotFoundError,
    RevisionClaimRequiredError,
    RevisionConflictError,
    RevisionDocumentError,
    RevisionNotEditableError,
    get_qc_page,
    save_page_revision,
)


router = APIRouter(prefix="/api", tags=["qc"], responses=API_ERROR_RESPONSES)
_revision_roles = Depends(require_role(AccessLevel.QC_USER,AccessLevel.PUBLISHER,AccessLevel.ADMIN))
_history_roles = Depends(
    require_role(
        AccessLevel.QC_USER,
        AccessLevel.ADMIN,
        AccessLevel.PUBLISHER,
    )
)


@router.get(
    "/pages/{page_id}",
    response_model=ApiResponse[QCPageRead],
)
@handle_api_exceptions(
    {
        PageNotFoundError: ApiExceptionRule(404, lambda error: str(error)),
        PageAssetUnavailableError: ApiExceptionRule(
            502, lambda error: str(error)
        ),
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
                    detail=(
                        "QC users cannot open pages in review or completed states."
                    ),
                )
        return ApiResponse.success(page)
    finally:
        s3_resource.close()


@router.post(
    "/pages/{page_id}/revisions",
    response_model=ApiResponse[PageRevisionRead],
    status_code=status.HTTP_201_CREATED,
)
@handle_api_exceptions(
    {
        PageNotFoundError: ApiExceptionRule(404, lambda error: str(error)),
        PageAssetUnavailableError: ApiExceptionRule(
            502, lambda error: str(error)
        ),
        PageAssetFormatError: ApiExceptionRule(502, lambda error: str(error)),
        RevisionClaimRequiredError: ApiExceptionRule(
            409, lambda error: str(error)
        ),
        RevisionConflictError: ApiExceptionRule(
            409, lambda error: str(error)
        ),
        RevisionNotEditableError: ApiExceptionRule(
            409, lambda error: str(error)
        ),
        RevisionDocumentError: ApiExceptionRule(
            422, lambda error: str(error)
        ),
    }
)
async def create_page_revision(
    page_id: int,
    request: SaveRevisionRequest,
    session: AsyncSession = Depends(get_db_session),
    user: User = _revision_roles,
) -> ApiResponse[PageRevisionRead]:
    s3_resource = S3Resource()
    try:
        result = await save_page_revision(
            session,
            page_id=page_id,
            user=user,
            base_revision_id=request.base_revision_id,
            submitted_document=request.document,
            s3_client=s3_resource.client,
            bucket=os.environ.get("S3_BUCKET", "bnhs-jbnhs-archive"),
        )
        return ApiResponse.success(result)
    finally:
        s3_resource.close()


@router.get(
    "/pages/{page_id}/revisions",
    response_model=ApiResponse[list[RevisionHistoryItem]],
)
@handle_api_exceptions(
    {
        PageNotFoundError: ApiExceptionRule(404, lambda error: str(error)),
        RevisionAccessDeniedError: ApiExceptionRule(
            403, lambda error: str(error)
        ),
        HistoryRevisionConflictError: ApiExceptionRule(
            409, lambda error: str(error)
        ),
    }
)
async def read_page_revision_history(
    page_id: int,
    session: AsyncSession = Depends(get_db_session),
    user: User = _history_roles,
) -> ApiResponse[list[RevisionHistoryItem]]:
    revisions = await list_page_revisions(
        session,
        page_id=page_id,
        user=user,
    )
    return ApiResponse.success(revisions)


@router.get(
    "/pages/{page_id}/revisions/{revision_id}",
    response_model=ApiResponse[RevisionDocumentRead],
)
@handle_api_exceptions(
    {
        PageNotFoundError: ApiExceptionRule(404, lambda error: str(error)),
        RevisionNotFoundError: ApiExceptionRule(404, lambda error: str(error)),
        RevisionAccessDeniedError: ApiExceptionRule(
            403, lambda error: str(error)
        ),
        HistoryRevisionConflictError: ApiExceptionRule(
            409, lambda error: str(error)
        ),
        PageAssetUnavailableError: ApiExceptionRule(
            502, lambda error: str(error)
        ),
        PageAssetFormatError: ApiExceptionRule(502, lambda error: str(error)),
    }
)
async def read_page_revision_content(
    page_id: int,
    revision_id: int,
    session: AsyncSession = Depends(get_db_session),
    user: User = _history_roles,
) -> ApiResponse[RevisionDocumentRead]:
    s3_resource = S3Resource()
    try:
        result = await read_page_revision(
            session,
            page_id=page_id,
            revision_id=revision_id,
            user=user,
            s3_client=s3_resource.client,
            bucket=os.environ.get("S3_BUCKET", "bnhs-jbnhs-archive"),
        )
        return ApiResponse.success(result)
    finally:
        s3_resource.close()


@router.get(
    "/pages/{page_id}/revisions/{revision_id}/compare",
    response_model=ApiResponse[RevisionComparisonRead],
)
@handle_api_exceptions(
    {
        PageNotFoundError: ApiExceptionRule(404, lambda error: str(error)),
        RevisionNotFoundError: ApiExceptionRule(404, lambda error: str(error)),
        RevisionAccessDeniedError: ApiExceptionRule(
            403, lambda error: str(error)
        ),
        HistoryRevisionConflictError: ApiExceptionRule(
            409, lambda error: str(error)
        ),
        PageAssetUnavailableError: ApiExceptionRule(
            502, lambda error: str(error)
        ),
        PageAssetFormatError: ApiExceptionRule(502, lambda error: str(error)),
    }
)
async def compare_page_revision(
    page_id: int,
    revision_id: int,
    against_revision_id: int | None = Query(default=None, ge=1),
    session: AsyncSession = Depends(get_db_session),
    user: User = _history_roles,
) -> ApiResponse[RevisionComparisonRead]:
    s3_resource = S3Resource()
    try:
        result = await compare_page_revisions(
            session,
            page_id=page_id,
            revision_id=revision_id,
            against_revision_id=against_revision_id,
            user=user,
            s3_client=s3_resource.client,
            bucket=os.environ.get("S3_BUCKET", "bnhs-jbnhs-archive"),
        )
        return ApiResponse.success(result)
    finally:
        s3_resource.close()
