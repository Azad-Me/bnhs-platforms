from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from sqlalchemy.ext.asyncio import AsyncSession

from common import DataBaseConnectionPool

app = FastAPI()

@asynccontextmanager
async def postgres_lifespan(app: FastAPI) -> AsyncIterator[None]:
    pool = DataBaseConnectionPool()
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

