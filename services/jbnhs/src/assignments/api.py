from fastapi import APIRouter, Depends, status
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
from .schemas import PageClaimRead
from .service import (
    PageClaimedError,
    PageClaimRequiredError,
    PageNotFoundError,
    PageStateConflictError,
    claim_page as claim_page_service,
    release_page_claim,
)


router = APIRouter(
    prefix="/api",
    tags=["assignments"],
    responses=API_ERROR_RESPONSES,
)
_claim_roles = Depends(require_role(AccessLevel.QC_USER, AccessLevel.ADMIN))


@router.post(
    "/pages/{page_id}/claim",
    response_model=ApiResponse[PageClaimRead],
)
@handle_api_exceptions(
    {
        PageNotFoundError: ApiExceptionRule(404, lambda error: str(error)),
        PageClaimedError: ApiExceptionRule(409, lambda error: str(error)),
        PageStateConflictError: ApiExceptionRule(409, lambda error: str(error)),
    }
)
async def claim_page(
    page_id: int,
    session: AsyncSession = Depends(get_db_session),
    user: User = _claim_roles,
) -> ApiResponse[PageClaimRead]:
    result = await claim_page_service(session, page_id=page_id, user=user)
    return ApiResponse.success(result)


@router.delete(
    "/pages/{page_id}/claim",
    response_model=ApiResponse[dict[str, str]],
)
@handle_api_exceptions(
    {
        PageNotFoundError: ApiExceptionRule(404, lambda error: str(error)),
        PageClaimRequiredError: ApiExceptionRule(409, lambda error: str(error)),
    }
)
async def release_claim(
    page_id: int,
    session: AsyncSession = Depends(get_db_session),
    user: User = _claim_roles,
) -> ApiResponse[dict[str, str]]:
    await release_page_claim(
        session,
        page_id=page_id,
        user_id=user.id,
        release_any_claim=user.level.strip().casefold() == AccessLevel.ADMIN.value,
    )
    return ApiResponse.success({})
