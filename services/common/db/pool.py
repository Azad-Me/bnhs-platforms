from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from .config import DatabaseSettings


class DataBaseConnectionPool:
    """Thin wrapper around the SQLAlchemy async Postgres pool."""

    def __init__(self, settings: DatabaseSettings | None = None):
        self.settings = settings or DatabaseSettings()
        self.engine: AsyncEngine = create_async_engine(
            self.settings.async_url,
            pool_pre_ping=True,
            echo=self.settings.echo,
            future=True,
            pool_size=self.settings.max_size,
            max_overflow=self.settings.max_overflow,
            pool_timeout=self.settings.pool_timeout,
        )
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

    async def ping(self) -> None:
        async with self.engine.begin() as conn:
            await conn.execute(text("SELECT 1"))

    async def close(self) -> None:
        await self.engine.dispose()

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session:
            yield session

    async def __aenter__(self) -> DataBaseConnectionPool:
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        await self.close()
