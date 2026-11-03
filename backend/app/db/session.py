"""Async engine and session factory. Postgres/Supabase in staging/production; SQLite for local dev/testing."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

_engine: AsyncEngine | None = None
_factory: async_sessionmaker[AsyncSession] | None = None


def _create_engine() -> AsyncEngine:
    settings = get_settings()
    url = settings.database_url
    kwargs: dict = {"pool_pre_ping": True, "future": True}
    if url.startswith("sqlite"):
        db_path = url.split("///", 1)[-1]
        if db_path and db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        # Postgres (including Supabase direct and pooled connections)
        server_settings = {
            "statement_timeout": str(settings.db_statement_timeout_ms),
            "application_name": "parallax-api",
        }
        connect_args: dict = {"server_settings": server_settings}
        # Supabase and cloud Postgres enforce SSL
        if "supabase.co" in url or "pooler.supabase.com" in url or settings.db_ssl:
            connect_args["ssl"] = "require"
        # Supabase transaction pooler (port 6543 / PgBouncer) requires disabling statement caching
        if ":6543" in url:
            connect_args["prepared_statement_cache_size"] = 0
            connect_args["statement_cache_size"] = 0

        kwargs.update(
            pool_size=settings.db_pool_size,
            max_overflow=max(2, settings.db_pool_size // 2),
            connect_args=connect_args,
        )
    return create_async_engine(url, **kwargs)


def set_engine(engine: AsyncEngine | None) -> None:
    global _engine, _factory
    _engine = engine
    _factory = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession) if _engine else None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = _create_engine()
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _factory
    if _factory is None:
        _factory = async_sessionmaker(get_engine(), expire_on_commit=False, class_=AsyncSession)
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
    global _engine, _factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _factory = None
