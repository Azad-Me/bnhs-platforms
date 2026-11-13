"""Authentication service operations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...common.models import User

from ..security import (
    InvalidGoogleCredential,
    create_access_token,
    decode_access_token,
    verify_google_credential,
)
from ..service import (
    GoogleIdentityConflictError,
    UserManagementService,
    UserNotFoundError,
)

from ..security import GoogleIdentity


class AuthenticationService:
    async def get_active_user(
        self, session: AsyncSession, user_id: int
    ) -> User | None:
        user = await session.get(User, user_id)
        if user is None or not user.is_active:
            return None
        return user

    async def authenticate_google_identity(
        self, session: AsyncSession, identity: GoogleIdentity
    ) -> User:
        user = await session.scalar(
            select(User).where(User.email == identity.email).with_for_update()
        )
        if user is None or not user.is_active:
            raise UserNotFoundError(identity.email)
        return user

__all__ = [
    "GoogleIdentityConflictError",
    "AuthenticationService",
    "InvalidGoogleCredential",
    "UserManagementService",
    "UserNotFoundError",
    "create_access_token",
    "decode_access_token",
    "verify_google_credential",
]
