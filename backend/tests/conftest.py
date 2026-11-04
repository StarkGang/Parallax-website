"""Pytest configuration: SQLite database and LocalStorage fixtures for offline testing."""

import os
import sys
import uuid
from pathlib import Path
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Ensure backend directory is in sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Set test environment variables before importing app modules
os.environ["APP_ENV"] = "test"
# The checked-in backend/.env enables debug mode, which forces the development
# environment and makes the suite assert the wrong runtime profile.
os.environ["DEBUG_MODE"] = "false"
os.environ["DEBUG"] = "false"
os.environ["APP_DEBUG"] = "false"
os.environ["FRONTEND_ORIGIN"] = "http://localhost:5173"
os.environ["STORAGE_BACKEND"] = "local"
os.environ["MFA_ENFORCED"] = "false"
os.environ["ALLOW_DIRECT_LOGIN"] = "true"
os.environ["DEV_AUTH_ENABLED"] = "true"
os.environ["PAYMENTS_ENABLED"] = "false"
os.environ["SEED_DEMO_DATA"] = "true"
os.environ["COOKIE_SECURE"] = "false"
os.environ["SERVER_SECRET_KEY"] = "test-secret-key-that-is-at-least-32-bytes-long"
os.environ["BOOTSTRAP_OWNER_EMAIL"] = "owner@parallax.local"
os.environ["DEV_ADMIN_EMAIL"] = "owner@parallax.local"
os.environ["DEV_PARTICIPANT_EMAIL"] = "participant@parallax.local"

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import set_engine, dispose_engine, get_db
from app.main import create_app
from app.seed import seed_if_empty


@pytest_asyncio.fixture(scope="session")
async def test_engine(tmp_path_factory):
    """Session-scoped SQLite database file."""
    db_dir = tmp_path_factory.mktemp("db")
    db_file = db_dir / "test.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    os.environ["DATABASE_URL"] = db_url

    storage_dir = tmp_path_factory.mktemp("storage")
    os.environ["LOCAL_STORAGE_DIR"] = str(storage_dir)

    get_settings.cache_clear()
    engine = create_async_engine(db_url, echo=False)
    set_engine(engine)

    # Create all 35 tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed initial test data
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as db:
        await seed_if_empty(db)

    yield engine

    await dispose_engine()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide a database session for a test."""
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(test_engine) -> AsyncGenerator[AsyncClient, None]:
    """Unauthenticated HTTP test client."""
    app = create_app()
    transport = ASGITransport(app=app)
    # Unsafe methods require an Origin matching FRONTEND_ORIGIN, exactly like a browser.
    async with AsyncClient(
        transport=transport,
        base_url="http://localhost:8000",
        headers={"Origin": "http://localhost:5173"},
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def participant_client(client: AsyncClient, db_session: AsyncSession) -> AsyncClient:
    """Authenticated client for a normal participant."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "participant@parallax.local", "role": "participant"},
    )
    assert resp.status_code == 200, resp.text
    return client


@pytest_asyncio.fixture
async def admin_client(client: AsyncClient, db_session: AsyncSession) -> AsyncClient:
    """Authenticated client for super_admin."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@parallax.local", "role": "admin"},
    )
    assert resp.status_code == 200, resp.text
    return client
