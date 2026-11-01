from __future__ import annotations

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.models import User
from .schemas import UserCreate, UserUpdate
from .security import GoogleIdentity


class UserNotFoundError(LookupError):
    pass


class UserEmailConflictError(ValueError):
    pass


class LastActiveAdminError(ValueError):
    pass


class GoogleIdentityConflictError(ValueError):
    pass


def _is_email_unique_violation(error: IntegrityError) -> bool:
    original = error.orig
    diagnostic = getattr(original, "diag", None)
    constraint_name = getattr(diagnostic, "constraint_name", None) or getattr(
        original, "constraint_name", None
    )
    return constraint_name == "users_email_key"


def _is_admin(user: User) -> bool:
    return user.level.strip().casefold() == "admin"


class UserManagementService:
    async def list_users(
        self,
        session: AsyncSession,
        *,
        include_inactive: bool,
        offset: int,
        limit: int,
    ) -> list[User]:
        statement = select(User).order_by(User.id).offset(offset).limit(limit)
        if not include_inactive:
            statement = statement.where(User.is_active.is_(True))
        return list((await session.scalars(statement)).all())

    async def get_user(self, session: AsyncSession, user_id: int) -> User:
        user = await session.get(User, user_id)
        if user is None:
            raise UserNotFoundError(user_id)
        return user

    async def create_user(
        self, session: AsyncSession, payload: UserCreate
    ) -> User:
        user = User(
            name=payload.name,
            email=str(payload.email),
            level=payload.level,
        )
        try:
            existing = await session.scalar(
                select(User.id).where(
                    func.lower(User.email) == str(payload.email).lower()
                )
            )
            if existing is not None:
                raise UserEmailConflictError(str(payload.email))
            session.add(user)
            await session.flush()
        except IntegrityError as error:
            if _is_email_unique_violation(error):
                raise UserEmailConflictError(str(payload.email)) from error
            raise
        return user

    async def authenticate_google_identity(
        self, session: AsyncSession, identity: GoogleIdentity
    ) -> User:
        user = await session.scalar(
            select(User)
            .where(User.google_sub == identity.subject)
            .with_for_update()
        )
        if user is None:
            user = await session.scalar(
                select(User)
                .where(func.lower(User.email) == identity.email)
                .with_for_update()
            )
            if user is None or (
                user.google_sub is not None
                and user.google_sub != identity.subject
            ):
                raise UserNotFoundError(identity.email)
            if not user.is_active:
                raise UserNotFoundError(identity.email)

            user.google_sub = identity.subject
            try:
                await session.flush()
            except IntegrityError as error:
                original = error.orig
                diagnostic = getattr(original, "diag", None)
                constraint_name = getattr(
                    diagnostic, "constraint_name", None
                ) or getattr(original, "constraint_name", None)
                if constraint_name == "users_google_sub_key":
                    raise GoogleIdentityConflictError(
                        "This Google account is already linked."
                    ) from error
                raise
        elif not user.is_active:
            raise UserNotFoundError(identity.email)
        return user

    async def update_user(
        self,
        session: AsyncSession,
        user_id: int,
        payload: UserUpdate,
    ) -> User:
        changes = payload.model_dump(exclude_unset=True)
        if "is_active" in changes or "level" in changes:
            await self._lock_admin_changes(session)
        try:
            user = await self._locked_user(session, user_id)
            new_email = changes.get("email")
            if new_email is not None:
                duplicate = await session.scalar(
                    select(User.id).where(
                        func.lower(User.email) == new_email.lower(),
                        User.id != user_id,
                    )
                )
                if duplicate is not None:
                    raise UserEmailConflictError(new_email)

            if user.is_active and _is_admin(user) and (
                changes.get("is_active") is False
                or (
                    changes.get("level") is not None
                    and changes["level"].casefold() != "admin"
                )
            ):
                await self._ensure_another_active_admin(session)

            for field, value in changes.items():
                setattr(user, field, value)
            await session.flush()
        except IntegrityError as error:
            if _is_email_unique_violation(error):
                raise UserEmailConflictError(str(payload.email)) from error
            raise
        return user

    async def deactivate_user(self, session: AsyncSession, user_id: int) -> None:
        await self._lock_admin_changes(session)
        user = await self._locked_user(session, user_id)
        if user.is_active:
            if _is_admin(user):
                await self._ensure_another_active_admin(session)
            user.is_active = False
            await session.flush()

    async def bootstrap_admin(
        self,
        session: AsyncSession,
        *,
        name: str,
        email: str,
    ) -> User:
        await self._lock_admin_changes(session)
        existing_admin = await session.scalar(
            select(User.id)
            .where(func.lower(func.trim(User.level)) == "admin")
            .limit(1)
        )
        if existing_admin is not None:
            raise ValueError(
                "An administrator already exists; bootstrap is one-time only."
            )
        existing_email = await session.scalar(
            select(User.id).where(func.lower(User.email) == email.lower())
        )
        if existing_email is not None:
            raise UserEmailConflictError(email)

        user = User(
            name=name,
            email=email,
            level="admin",
        )
        session.add(user)
        try:
            await session.flush()
        except IntegrityError as error:
            if _is_email_unique_violation(error):
                raise UserEmailConflictError(email) from error
            raise
        return user

    async def _locked_user(self, session: AsyncSession, user_id: int) -> User:
        user = await session.scalar(
            select(User)
            .where(User.id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if user is None:
            raise UserNotFoundError(user_id)
        return user

    async def _ensure_another_active_admin(self, session: AsyncSession) -> None:
        active_admins = await session.scalars(
            select(User)
            .where(
                User.is_active.is_(True),
                func.lower(func.trim(User.level)) == "admin",
            )
            .with_for_update()
        )
        if len(active_admins.all()) <= 1:
            raise LastActiveAdminError(
                "The last active administrator cannot be deactivated or demoted."
            )

    async def _lock_admin_changes(self, session: AsyncSession) -> None:
        await session.execute(text("SELECT pg_advisory_xact_lock(827364921)"))


user_management_service = UserManagementService()
