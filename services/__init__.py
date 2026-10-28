from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from sqlalchemy.ext.asyncio import AsyncSession

from common import DataBaseConnectionPool
from common.db.config import DatabaseSettings

app = FastAPI()


def load_database_settings() -> DatabaseSettings:
    """Load database settings from the current process environment."""
    return DatabaseSettings()


async def check_database_connection(
    settings: DatabaseSettings | None = None,
) -> None:
    """Check database credentials and connectivity by executing ``SELECT 1``."""
    async with DataBaseConnectionPool(settings or load_database_settings()) as pool:
        await pool.ping()


@asynccontextmanager
async def postgres_lifespan(app: FastAPI) -> AsyncIterator[None]:
    pool = DataBaseConnectionPool(load_database_settings())
    app.state.db_pool = pool
    try:
        await pool.ping()
        yield
    finally:
        try:
            await pool.close()
        finally:
            if getattr(app.state, "db_pool", None) is pool:
                del app.state.db_pool


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    pool: DataBaseConnectionPool | None = getattr(app.state, "db_pool", None)
    if pool is None:
        raise RuntimeError("The Postgres pool is not initialized; check the app lifespan.")

    async with pool.session() as session:
        yield session


__all__ = [
    "app",
    "check_database_connection",
    "get_db_session",
    "load_database_settings",
    "postgres_lifespan",
]
