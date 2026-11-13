from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...common.db.dependencies import get_db_session
from ...common.responses import (
    API_ERROR_RESPONSES,
    ApiExceptionRule,
    ApiResponse,
    handle_api_exceptions,
)
from ..admin.schemas import RoleRead, UserCreate, UserRead, UserUpdate
from ..admin.service import (
    LastActiveAdminError,
    UserEmailConflictError,
    UserManagementService,
    UserNotFoundError,
)
from ..admin.role_service import RoleNotFoundError, RoleService
from ..router import require_admin


router = APIRouter(
    prefix="/api",
    tags=["user management"],
    responses=API_ERROR_RESPONSES,
    dependencies=[Depends(require_admin)],
)


@router.get("/roles", response_model=ApiResponse[list[RoleRead]])
async def list_roles(
    session: AsyncSession = Depends(get_db_session),
    role_service: RoleService = Depends(RoleService),
) -> ApiResponse[list[RoleRead]]:
    roles = await role_service.list_roles(session)
    return ApiResponse.success([RoleRead.model_validate(role) for role in roles])


@router.get("/users", response_model=ApiResponse[list[UserRead]])
async def list_users(
    include_inactive: bool = False,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_db_session),
    user_management_service: UserManagementService = Depends(UserManagementService),
) -> ApiResponse[list[UserRead]]:
    users = await user_management_service.list_users(
        session, include_inactive=include_inactive, offset=offset, limit=limit
    )
    return ApiResponse.success([UserRead.model_validate(user) for user in users])


@router.post(
    "/users",
    response_model=ApiResponse[UserRead],
    status_code=status.HTTP_201_CREATED,
)
@handle_api_exceptions(
    {
        UserEmailConflictError: ApiExceptionRule(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists.",
        ),
        RoleNotFoundError: ApiExceptionRule(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Role is not available.",
        ),
    }
)
async def create_user(
    payload: UserCreate,
    session: AsyncSession = Depends(get_db_session),
    user_management_service: UserManagementService = Depends(UserManagementService),
) -> ApiResponse[UserRead]:
    user = await user_management_service.create_user(session, payload)
    return ApiResponse.success(UserRead.model_validate(user))


@router.get("/users/{user_id}", response_model=ApiResponse[UserRead])
@handle_api_exceptions(
    {
        UserNotFoundError: ApiExceptionRule(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found."
        )
    }
)
async def read_user(
    user_id: int,
    session: AsyncSession = Depends(get_db_session),
    user_management_service: UserManagementService = Depends(UserManagementService),
) -> ApiResponse[UserRead]:
    user = await user_management_service.get_user(session, user_id)
    return ApiResponse.success(UserRead.model_validate(user))


@router.patch("/users/{user_id}", response_model=ApiResponse[UserRead])
@handle_api_exceptions(
    {
        UserNotFoundError: ApiExceptionRule(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found."
        ),
        UserEmailConflictError: ApiExceptionRule(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists.",
        ),
        LastActiveAdminError: ApiExceptionRule(
            status_code=status.HTTP_409_CONFLICT, detail=lambda error: str(error)
        ),
        RoleNotFoundError: ApiExceptionRule(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Role is not available.",
        ),
    }
)
async def update_user(
    user_id: int,
    payload: UserUpdate,
    session: AsyncSession = Depends(get_db_session),
    user_management_service: UserManagementService = Depends(UserManagementService),
) -> ApiResponse[UserRead]:
    user = await user_management_service.update_user(session, user_id, payload)
    return ApiResponse.success(UserRead.model_validate(user))


@router.delete("/users/{user_id}", response_model=ApiResponse[dict[str, str]])
@handle_api_exceptions(
    {
        UserNotFoundError: ApiExceptionRule(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found."
        ),
        LastActiveAdminError: ApiExceptionRule(
            status_code=status.HTTP_409_CONFLICT, detail=lambda error: str(error)
        ),
    }
)
async def deactivate_user(
    user_id: int,
    session: AsyncSession = Depends(get_db_session),
    user_management_service: UserManagementService = Depends(UserManagementService),
) -> ApiResponse[dict[str, str]]:
    await user_management_service.deactivate_user(session, user_id)
    return ApiResponse.success({})
