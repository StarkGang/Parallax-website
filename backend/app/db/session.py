"""Async engine and session factory. Postgres/Supabase in staging/production; SQLite for local dev/testing."""

import asyncio
import os
import ssl
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

_engine: AsyncEngine | None = None
_engine_loop: asyncio.AbstractEventLoop | None = None
_factory: async_sessionmaker[AsyncSession] | None = None


def _create_engine() -> AsyncEngine:
    settings = get_settings()
    url = settings.database_url
    is_serverless = bool(os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"))
    kwargs: dict = {"future": True}

    if url.startswith("sqlite"):
        db_path = url.split("///", 1)[-1]
        if db_path and db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        kwargs["pool_pre_ping"] = True
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        # Postgres (including Supabase direct and pooled connections)
        server_settings = {
            "statement_timeout": str(settings.db_statement_timeout_ms),
            "application_name": "parallax-api",
        }
        connect_args: dict = {
            "server_settings": server_settings,
            "command_timeout": max(5.0, settings.db_statement_timeout_ms / 1000.0),
        }

        # Supabase and cloud Postgres SSL
        if "supabase.co" in url or "pooler.supabase.com" in url or settings.db_ssl or "sslmode=" in url or "ssl=" in url:
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
            connect_args["ssl"] = ssl_ctx

        # Disable prepared statement caching on Supabase PgBouncer/Supavisor or in serverless lambdas
        if ":6543" in url or ":5432" in url or is_serverless or "supabase" in url:
            connect_args["prepared_statement_cache_size"] = 0
            connect_args["statement_cache_size"] = 0

        # Strip any query parameters like ?sslmode=require from the URL so SQLAlchemy doesn't conflict with connect_args
        clean_url = url.split("?")[0]

        # In serverless (Vercel / Lambda), use NullPool to avoid frozen socket / loop conflicts
        if is_serverless:
            kwargs["poolclass"] = NullPool
        else:
            kwargs["pool_pre_ping"] = True
            kwargs.update(
                pool_size=settings.db_pool_size,
                max_overflow=max(2, settings.db_pool_size // 2),
            )
        kwargs["connect_args"] = connect_args

    return create_async_engine(clean_url if "clean_url" in locals() else url, **kwargs)


def set_engine(engine: AsyncEngine | None) -> None:
    global _engine, _factory, _engine_loop
    _engine = engine
    _engine_loop = None
    _factory = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession) if _engine else None


def get_engine() -> AsyncEngine:
    global _engine, _factory, _engine_loop
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    is_serverless = bool(os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"))
    if _engine is None or (is_serverless and current_loop is not None and _engine_loop != current_loop):
        _engine = _create_engine()
        _engine_loop = current_loop
        _factory = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _factory
    get_engine()
    return _factory


async def get_db() -> AsyncIterator[AsyncSession]:
    async with get_session_factory()() as session:
        try:
            yield session
        finally:
            await session.close()


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    async with get_session_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    global _engine, _factory, _engine_loop
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _engine_loop = None
    _factory = None
