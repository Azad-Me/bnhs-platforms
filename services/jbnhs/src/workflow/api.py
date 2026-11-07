from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

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
from .schemas import PageReviewActionRead, ReviewDecisionRequest
from .service import (
    PageNotFoundError,
    WorkflowAccessDeniedError,
    WorkflowClaimRequiredError,
    WorkflowDraftRequiredError,
    WorkflowStateConflictError,
    decide_page_review,
    submit_page_for_review,
)


router = APIRouter(
    prefix="/api",
    tags=["page workflow"],
    responses=API_ERROR_RESPONSES,
)
_submit_roles = Depends(require_role(AccessLevel.QC_USER))
_review_roles = Depends(
    require_role(AccessLevel.ADMIN, AccessLevel.PUBLISHER)
)


@router.post(
    "/pages/{page_id}/submit-review",
    response_model=ApiResponse[PageReviewActionRead],
)
@handle_api_exceptions(
    {
        PageNotFoundError: ApiExceptionRule(404, lambda error: str(error)),
        WorkflowAccessDeniedError: ApiExceptionRule(
            403, lambda error: str(error)
        ),
        WorkflowClaimRequiredError: ApiExceptionRule(
            409, lambda error: str(error)
        ),
        WorkflowDraftRequiredError: ApiExceptionRule(
            409, lambda error: str(error)
        ),
        WorkflowStateConflictError: ApiExceptionRule(
            409, lambda error: str(error)
        ),
    }
)
async def submit_review(
    page_id: int,
    session: AsyncSession = Depends(get_db_session),
    user: User = _submit_roles,
) -> ApiResponse[PageReviewActionRead]:
    result = await submit_page_for_review(
        session,
        page_id=page_id,
        user=user,
    )
    return ApiResponse.success(result)


@router.post(
    "/pages/{page_id}/review",
    response_model=ApiResponse[PageReviewActionRead],
)
@handle_api_exceptions(
    {
        PageNotFoundError: ApiExceptionRule(404, lambda error: str(error)),
        WorkflowAccessDeniedError: ApiExceptionRule(
            403, lambda error: str(error)
        ),
        WorkflowStateConflictError: ApiExceptionRule(
            409, lambda error: str(error)
        ),
    }
)
async def review_page(
    page_id: int,
    request: ReviewDecisionRequest,
    session: AsyncSession = Depends(get_db_session),
    user: User = _review_roles,
) -> ApiResponse[PageReviewActionRead]:
    result = await decide_page_review(
        session,
        page_id=page_id,
        user=user,
        decision=request.decision,
        note=request.note,
    )
    return ApiResponse.success(result)
