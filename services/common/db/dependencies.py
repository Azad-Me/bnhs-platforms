from __future__ import annotations

from typing import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from .pool import DataBaseConnectionPool


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    pool: DataBaseConnectionPool | None = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise RuntimeError("The Postgres pool is not initialized; check the app lifespan.")

    async with pool.session() as session:
        async with session.begin():
            yield session
