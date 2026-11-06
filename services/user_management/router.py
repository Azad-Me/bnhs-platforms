from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.constant.access_level_enum import AccessLevel
from ..common.db.dependencies import get_db_session
from ..common.models import User
from ..common.responses import (
    API_ERROR_RESPONSES,
    ApiExceptionRule,
    ApiResponse,
    handle_api_exceptions,
)
from .schemas import (
    GoogleSignInRequest,
    TokenResponse,
    UserCreate,
    UserRead,
    UserUpdate,
)
from .role_schemas import RoleRead
from .role_service import RoleNotFoundError, RoleService
from .security import (
    InvalidGoogleCredential,
    create_access_token,
    decode_access_token,
    verify_google_credential,
)
from .service import (
    GoogleIdentityConflictError,
    LastActiveAdminError,
    UserEmailConflictError,
    UserNotFoundError,
    UserManagementService,
)


logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api",
    tags=["user management"],
    responses=API_ERROR_RESPONSES,
)
_bearer_scheme = HTTPBearer(auto_error=False)
_LOGIN_ERROR_RULE = ApiExceptionRule(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Authentication is required.",
    log_message="Google sign-in rejected",
)


def _authentication_required() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication is required.",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    session: AsyncSession = Depends(get_db_session),
    user_management_service = UserManagementService(),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _authentication_required()
    try:
        user_id = decode_access_token(credentials.credentials)
    except jwt.InvalidTokenError as error:
        raise _authentication_required() from error

    user = await user_management_service.get_active_user(session, user_id)
    if user is None:
        raise _authentication_required()
    return user


def require_role(*levels: AccessLevel) -> Callable[..., Awaitable[User]]:
    allowed_levels = {level.value for level in levels}

    async def dependency(
        user: User = Depends(get_current_user),
    ) -> User:
        return _require_user_role(user, allowed_levels)

    return dependency


def _require_user_role(user: User, allowed_levels: set[str]) -> User:
    if user.level.strip().casefold() not in allowed_levels:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This role is not permitted to perform this action.",
        )
    return user


async def require_admin(
    user: User = Depends(get_current_user),
) -> User:
    return _require_user_role(user, {AccessLevel.ADMIN.value})


@router.post(
    "/auth/login",
    response_model=ApiResponse[TokenResponse],
)
@handle_api_exceptions(
    {
        InvalidGoogleCredential: _LOGIN_ERROR_RULE,
        UserNotFoundError: _LOGIN_ERROR_RULE,
        GoogleIdentityConflictError: _LOGIN_ERROR_RULE,
    }
)
async def login(
    payload: GoogleSignInRequest,
    session: AsyncSession = Depends(get_db_session),
    user_management_service = UserManagementService(),
) -> ApiResponse[TokenResponse]:
    identity = await verify_google_credential(payload.credential)
    user = await user_management_service.authenticate_google_identity(
        session, identity
    )

    access_token, expires_in = create_access_token(user.id)
    logger.info("Google sign-in succeeded for user_id=%s", user.id)
    return ApiResponse.success(
        TokenResponse(access_token=access_token, expires_in=expires_in)
    )


@router.get("/auth/me", response_model=ApiResponse[UserRead])
async def read_current_user(
    user: User = Depends(get_current_user),
) -> ApiResponse[UserRead]:
    return ApiResponse.success(UserRead.model_validate(user))


@router.get("/roles", response_model=ApiResponse[list[RoleRead]])
async def list_roles(
    session: AsyncSession = Depends(get_db_session),
    role_service: RoleService = Depends(RoleService),
    _: User = Depends(require_admin),
) -> ApiResponse[list[RoleRead]]:
    roles = await role_service.list_roles(session)
    return ApiResponse.success(
        [RoleRead.model_validate(role) for role in roles]
    )


@router.get("/users", response_model=ApiResponse[list[UserRead]])
async def list_users(
    include_inactive: bool = False,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_db_session),
    user_management_service = UserManagementService(),
    _: User = Depends(require_admin),
) -> ApiResponse[list[UserRead]]:
    users = await user_management_service.list_users(
        session,
        include_inactive=include_inactive,
        offset=offset,
        limit=limit,
    )
    return ApiResponse.success(
        [UserRead.model_validate(user) for user in users]
    )


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
    user_management_service = UserManagementService(),
    _: User = Depends(require_admin),
) -> ApiResponse[UserRead]:
    user = await user_management_service.create_user(session, payload)
    return ApiResponse.success(UserRead.model_validate(user))


@router.get("/users/{user_id}", response_model=ApiResponse[UserRead])
@handle_api_exceptions(
    {
        UserNotFoundError: ApiExceptionRule(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )
    }
)
async def read_user(
    user_id: int,
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_admin),
    user_management_service = UserManagementService(),
) -> ApiResponse[UserRead]:
    user = await user_management_service.get_user(session, user_id)
    return ApiResponse.success(UserRead.model_validate(user))


@router.patch(
    "/users/{user_id}",
    response_model=ApiResponse[UserRead],
)
@handle_api_exceptions(
    {
        UserNotFoundError: ApiExceptionRule(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        ),
        UserEmailConflictError: ApiExceptionRule(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists.",
        ),
        LastActiveAdminError: ApiExceptionRule(
            status_code=status.HTTP_409_CONFLICT,
            detail=lambda error: str(error),
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
    user_management_service = UserManagementService(),
    _: User = Depends(require_admin),
) -> ApiResponse[UserRead]:
    user = await user_management_service.update_user(session, user_id, payload)
    return ApiResponse.success(UserRead.model_validate(user))


@router.delete(
    "/users/{user_id}",
    response_model=ApiResponse[dict[str, str]],
)
@handle_api_exceptions(
    {
        UserNotFoundError: ApiExceptionRule(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        ),
        LastActiveAdminError: ApiExceptionRule(
            status_code=status.HTTP_409_CONFLICT,
            detail=lambda error: str(error),
        ),
    }
)
async def deactivate_user(
    user_id: int,
    session: AsyncSession = Depends(get_db_session),
    user_management_service = UserManagementService(),
    _: User = Depends(require_admin),
) -> ApiResponse[dict[str, str]]:
    await user_management_service.deactivate_user(session, user_id)
    return ApiResponse.success({})
