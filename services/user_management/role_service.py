from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.models import Role


class RoleNotFoundError(LookupError):
    pass


class RoleService:
    async def list_roles(
        self, session: AsyncSession
    ) -> list[Role]:
        statement = select(Role).order_by(Role.name, Role.key)
        return list((await session.scalars(statement)).all())

    async def get_role(self, session: AsyncSession, role_key: str) -> Role:
        role = await session.get(Role, role_key)
        if role is None:
            raise RoleNotFoundError(role_key)
        return role
