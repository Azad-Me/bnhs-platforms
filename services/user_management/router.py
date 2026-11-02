from __future__ import annotations

import logging

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.db.dependencies import get_db_session
from ..common.models import User
from .schemas import (
    GoogleSignInRequest,
    TokenResponse,
    UserCreate,
    UserRead,
    UserUpdate,
)
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
    user_management_service,
)


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["user management"])
_bearer_scheme = HTTPBearer(auto_error=False)


def _authentication_required() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication is required.",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    session: AsyncSession = Depends(get_db_session),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _authentication_required()
    try:
        user_id = decode_access_token(credentials.credentials)
    except jwt.InvalidTokenError as error:
        raise _authentication_required() from error

    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise _authentication_required()
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.level.strip().casefold() != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access is required.",
        )
    return user


@router.post("/auth/login", response_model=TokenResponse)
async def login(
    payload: GoogleSignInRequest,
    session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    try:
        identity = await verify_google_credential(payload.credential)
    except InvalidGoogleCredential as error:
        logger.warning("Google sign-in rejected: invalid credential")
        raise _authentication_required() from error
    try:
        user = await user_management_service.authenticate_google_identity(
            session, identity
        )
    except (UserNotFoundError, GoogleIdentityConflictError) as error:
        logger.warning(
            "Google sign-in rejected: account is not provisioned or is already linked"
        )
        raise _authentication_required() from error
    
    access_token, expires_in = create_access_token(user.id)
    logger.info("Google sign-in succeeded for user_id=%s", user.id)
    return TokenResponse(access_token=access_token, expires_in=expires_in)


@router.get("/auth/me", response_model=UserRead)
async def read_current_user(
    user: User = Depends(get_current_user),
) -> User:
    return user


@router.get("/users", response_model=list[UserRead])
async def list_users(
    include_inactive: bool = False,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_admin),
) -> list[User]:
    return await user_management_service.list_users(
        session,
        include_inactive=include_inactive,
        offset=offset,
        limit=limit,
    )


@router.post(
    "/users",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_user(
    payload: UserCreate,
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_admin),
) -> User:
    try:
        return await user_management_service.create_user(session, payload)
    except UserEmailConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists.",
        ) from error


@router.get("/users/{user_id}", response_model=UserRead)
async def read_user(
    user_id: int,
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_admin),
) -> User:
    try:
        return await user_management_service.get_user(session, user_id)
    except UserNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        ) from error


@router.patch("/users/{user_id}", response_model=UserRead)
async def update_user(
    user_id: int,
    payload: UserUpdate,
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_admin),
) -> User:
    try:
        return await user_management_service.update_user(session, user_id, payload)
    except UserNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        ) from error
    except UserEmailConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists.",
        ) from error
    except LastActiveAdminError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_user(
    user_id: int,
    session: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_admin),
) -> None:
    try:
        await user_management_service.deactivate_user(session, user_id)
    except UserNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        ) from error
    except LastActiveAdminError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
