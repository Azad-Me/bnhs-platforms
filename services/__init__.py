from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.common import DataBaseConnectionPool
from services.common.db.dependencies import get_db_session
from services.common.db.config import DatabaseSettings
from services.common import params
from services.common.responses import register_api_exception_handlers
from services.jbnhs import router as jbnhs_router
from services.user_management import router as user_management_router
from services.user_management.security import load_auth_settings


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


_cors_origins = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:5500",
    "http://127.0.0.1:5500",
]
if "*" in _cors_origins:
    raise ValueError("CORS_ALLOWED_ORIGINS must not contain a wildcard origin.")

app = FastAPI(lifespan=postgres_lifespan)
register_api_exception_handlers(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(user_management_router)
app.include_router(jbnhs_router)


__all__ = [
    "app",
    "check_database_connection",
    "get_db_session",
    "load_database_settings",
    "postgres_lifespan",
]
