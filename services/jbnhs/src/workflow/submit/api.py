from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from .....common.constant.access_level_enum import AccessLevel
from .....common.db.dependencies import get_db_session
from .....common.models import User
from .....common.responses import (
    API_ERROR_RESPONSES,
    ApiExceptionRule,
    ApiResponse,
    handle_api_exceptions,
)
from .....user_management.router import get_current_user, require_role
from .schemas import PageReviewActionRead
from .service import (
    PageNotFoundError,
    WorkflowAccessDeniedError,
    WorkflowClaimRequiredError,
    WorkflowDraftRequiredError,
    WorkflowStateConflictError,
    submit_page_for_review,
)


router = APIRouter(
    prefix="/api",
    tags=["page workflow"],
    responses=API_ERROR_RESPONSES,
    dependencies=[
        Depends(
            require_role(
                AccessLevel.QC_USER, AccessLevel.PUBLISHER, AccessLevel.ADMIN
            )
        )
    ],
)


@router.post(
    "/pages/{page_id}/submit_for_review",
    response_model=ApiResponse[PageReviewActionRead],
)
@handle_api_exceptions(
    {
        PageNotFoundError: ApiExceptionRule(404, lambda error: str(error)),
        WorkflowAccessDeniedError: ApiExceptionRule(403, lambda error: str(error)),
        WorkflowClaimRequiredError: ApiExceptionRule(409, lambda error: str(error)),
        WorkflowDraftRequiredError: ApiExceptionRule(409, lambda error: str(error)),
        WorkflowStateConflictError: ApiExceptionRule(409, lambda error: str(error)),
    }
)
async def submit_review(
    page_id: int,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> ApiResponse[PageReviewActionRead]:
    result = await submit_page_for_review(session, page_id=page_id, user=user)
    return ApiResponse.success(result)
