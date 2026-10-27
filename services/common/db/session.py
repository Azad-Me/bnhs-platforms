from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from .pool import DataBaseConnectionPool


@asynccontextmanager
async def db_session(pool: DataBaseConnectionPool) -> AsyncIterator[AsyncSession]:
    async with pool.session() as session:
        yield session
