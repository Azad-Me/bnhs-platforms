from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from .common import DataBaseConnectionPool
from .common.db.dependencies import get_db_session
from .common.db.config import DatabaseSettings
from .jbnhs.src.jbnhs.api import router as jbnhs_router
from .user_management.router import router as user_management_router
from .user_management.security import load_auth_settings


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
    load_auth_settings()
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


app = FastAPI(lifespan=postgres_lifespan)

app.include_router(user_management_router)
app.include_router(jbnhs_router)


__all__ = [
    "app",
    "check_database_connection",
    "get_db_session",
    "load_database_settings",
    "postgres_lifespan",
]
