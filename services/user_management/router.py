from __future__ import annotations

from collections.abc import Awaitable, Callable

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.constant.access_level_enum import AccessLevel
from ..common.db.dependencies import get_db_session
from ..common.models import User
from ..common.responses import (
    API_ERROR_RESPONSES,
    ApiExceptionRule,
)
from .security import decode_access_token
from .auth.service import AuthenticationService

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
    user_management_service: AuthenticationService = Depends(AuthenticationService),
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


from .auth.api import router as authentication_router
from .admin.api import router as administration_router

router.include_router(authentication_router)
router.include_router(administration_router)
