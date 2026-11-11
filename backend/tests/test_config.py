"""Tests for config loading, Postgres/Supabase URL normalization and storage selection."""

import pytest
from app.core.config import Settings, get_settings


def test_config_env_and_defaults():
    settings = get_settings()
    assert settings.app_env == "test"
    assert settings.is_test is True
    assert settings.mfa_enforced is False
    assert settings.allow_direct_login is True
    assert settings.dev_auth_enabled is True


def test_database_url_normalization():
    # 1. Supabase / Postgres URLs with postgres://
    s1 = Settings(
        database_url="postgres://postgres:secret@db.abc.supabase.co:5432/postgres",
        server_secret_key="0" * 32,
    )
    assert s1.database_url_effective == "postgresql+asyncpg://postgres:secret@db.abc.supabase.co:5432/postgres"

    # 2. Supabase / Postgres URLs with postgresql://
    s2 = Settings(
        database_url="postgresql://postgres:secret@db.abc.supabase.co:6543/postgres",
        server_secret_key="0" * 32,
    )
    assert s2.database_url_effective == "postgresql+asyncpg://postgres:secret@db.abc.supabase.co:6543/postgres"

    # 3. Already asyncpg
    s3 = Settings(
        database_url="postgresql+asyncpg://postgres:secret@db.abc.supabase.co:5432/postgres",
        server_secret_key="0" * 32,
    )
    assert s3.database_url_effective == "postgresql+asyncpg://postgres:secret@db.abc.supabase.co:5432/postgres"

    # 4. SQLite remains intact
    s4 = Settings(
        database_url="sqlite+aiosqlite:///./var/test.db",
        server_secret_key="0" * 32,
    )
    assert s4.database_url_effective == "sqlite+aiosqlite:///./var/test.db"


def test_storage_backend_selection(monkeypatch):
    # Storage selection must not depend on whatever credentials happen to be in
    # the developer's shell or .env file, so the test builds isolated Settings.
    for name in (
        "SUPABASE_URL",
        "SUPABASE_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "STORAGE_BACKEND",
        "S3_ENDPOINT_URL",
        "S3_ACCESS_KEY_ID",
        "S3_SECRET_ACCESS_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    def isolated(**overrides) -> Settings:
        return Settings(_env_file=None, server_secret_key="0" * 32, **overrides)

    # 1. Force local
    s_local = isolated(storage_backend="local")
    assert s_local.effective_storage_backend == "local"

    # 2. Force supabase
    s_supa = isolated(
        storage_backend="supabase",
        supabase_url="https://xyz.supabase.co",
        supabase_key="secret",
    )
    assert s_supa.effective_storage_backend == "supabase"

    # 3. Auto fallback to local when not configured
    s_auto_empty = isolated(storage_backend="auto")
    assert s_auto_empty.effective_storage_backend == "local"

    # 4. Auto detects supabase when credentials provided
    s_auto_supa = isolated(
        storage_backend="auto",
        supabase_url="https://xyz.supabase.co",
        supabase_key="anon_or_service_key",
    )
    assert s_auto_supa.effective_storage_backend == "supabase"


def test_server_secret_key_handling():
    # 1. In dev/test, auto-generates 32+ bytes if empty
    s_dev = Settings(app_env="test", server_secret_key="")
    assert len(s_dev.server_secret_key) >= 32

    # 2. In production, raises ValueError if empty
    with pytest.raises(ValueError, match="SERVER_SECRET_KEY"):
        Settings(
            app_env="production",
            server_secret_key="",
            cookie_secure=True,
            frontend_origin="https://example.com",
            allowed_hosts="example.com",
        )

    # 3. In production, raises ValueError if placeholder string is used
    with pytest.raises(ValueError, match="SERVER_SECRET_KEY"):
        Settings(
            app_env="production",
            server_secret_key="dev-only-change-me-please-32-bytes-minimum-secret",
            cookie_secure=True,
            frontend_origin="https://example.com",
            allowed_hosts="example.com",
        )

