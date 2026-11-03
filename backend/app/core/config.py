"""Typed application settings.

Every value here is infrastructure or a secret. Prices, caps and event rules live
in the database (edition_policies) and are edited in the admin panel, never here.
"""

import secrets
from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(BACKEND_DIR / ".env"), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # runtime
    app_env: str = "development"
    app_debug: bool = False
    app_base_url: str = "http://localhost:8000"
    frontend_origin: str = "http://localhost:5173"
    allowed_hosts: str = "localhost,127.0.0.1"
    trusted_proxy_ips: str = "127.0.0.1,::1"

    # database
    database_url: str = "sqlite+aiosqlite:///./var/parallax.db"
    supabase_db_url: str | None = None
    database_migration_url: str | None = None
    db_pool_size: int = 10
    db_statement_timeout_ms: int = 5000
    db_ssl: bool = False
    auto_create_tables: bool = True

    # sessions / cookies
    session_cookie_name: str = "px_session"
    session_idle_ttl_participant_min: int = 10080
    session_absolute_ttl_participant_min: int = 43200
    session_idle_ttl_staff_min: int = 30
    session_absolute_ttl_staff_min: int = 480
    cookie_secure: bool = False
    cookie_samesite: str = "lax"
    server_secret_key: str = Field(default="", description="Base secret key for HMAC, sessions, and encryption, loaded from SERVER_SECRET_KEY")
    server_secret_key_previous: str | None = None
    totp_encryption_key: str | None = None

    # simplified auth & mfa switch
    mfa_enforced: bool = False
    allow_direct_login: bool = True

    # google
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str = "http://localhost:8000/api/v1/auth/google/callback"

    # local development sign-in
    dev_auth_enabled: bool = True
    dev_admin_email: str = "owner@parallax.local"
    dev_participant_email: str = "participant@parallax.local"

    # payments
    payments_enabled: bool = False
    razorpay_key_id: str | None = None
    razorpay_key_secret: str | None = None
    razorpay_webhook_secret: str | None = None

    # supabase (storage & api)
    supabase_url: str | None = None
    supabase_key: str | None = None
    supabase_service_role_key: str | None = None
    supabase_storage_bucket: str = "parallax"

    # storage
    storage_backend: str = "auto"  # auto | supabase | s3 | local
    s3_endpoint_url: str | None = None
    s3_bucket_private: str = "parallax-private"
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    signed_url_ttl_seconds: int = 120

    # email
    email_enabled: bool = False
    email_provider_api_key: str | None = None
    email_from: str | None = None

    # limits
    max_request_body_bytes: int = 1_048_576
    max_upload_bytes_document: int = 3_145_728
    max_upload_bytes_icon_svg: int = 65_536
    max_upload_bytes_icon_png: int = 262_144

    # bootstrap / monitoring
    bootstrap_owner_email: str | None = None
    sentry_dsn: str | None = None
    seed_demo_data: bool = True

    @model_validator(mode="after")
    def _validate(self) -> "Settings":
        if self.app_env not in {"development", "staging", "production", "test"}:
            raise ValueError("APP_ENV must be development, staging, production or test")
        self.frontend_origin = self.frontend_origin.rstrip("/")

        # Resolve SERVER_SECRET_KEY from environment or .env
        if not self.server_secret_key:
            if self.app_env in {"development", "test"}:
                self.server_secret_key = secrets.token_hex(32)
            else:
                raise ValueError("SERVER_SECRET_KEY must be set in the environment or .env")

        if len(self.server_secret_key.encode()) < 32:
            raise ValueError("SERVER_SECRET_KEY must be at least 32 bytes")

        if self.app_env not in {"development", "test"}:
            weak_samples = ("change-me", "changeme", "placeholder", "dev-only")
            if any(sample in self.server_secret_key.lower() for sample in weak_samples):
                raise ValueError("SERVER_SECRET_KEY cannot be a placeholder or example value outside development")

        # Supabase DB URL handling: prefer supabase_db_url if provided and database_url is the default sqlite
        if self.supabase_db_url and (
            self.database_url == "sqlite+aiosqlite:///./var/parallax.db" or not self.database_url
        ):
            self.database_url = self.supabase_db_url

        # Normalize postgres protocol for SQLAlchemy asyncpg
        if self.database_url.startswith("postgresql://"):
            self.database_url = "postgresql+asyncpg://" + self.database_url[len("postgresql://") :]
        elif self.database_url.startswith("postgres://"):
            self.database_url = "postgresql+asyncpg://" + self.database_url[len("postgres://") :]

        if self.app_env not in {"development", "test"}:
            if self.app_debug:
                raise ValueError("APP_DEBUG must be false outside development")
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be true outside development")
            if not self.frontend_origin.startswith("https://"):
                raise ValueError("FRONTEND_ORIGIN must be https outside development")
            deadline = self.allowed_hosts.strip()
            if not deadline or deadline == "*":
                raise ValueError("ALLOWED_HOSTS must be an explicit allow-list")

        if self.payments_enabled:
            missing = [
                name
                for name, value in {
                    "RAZORPAY_KEY_ID": self.razorpay_key_id,
                    "RAZORPAY_KEY_SECRET": self.razorpay_key_secret,
                    "RAZORPAY_WEBHOOK_SECRET": self.razorpay_webhook_secret,
                }.items()
                if not value
            ]
            if missing:
                raise ValueError(f"PAYMENTS_ENABLED requires {', '.join(missing)}")
            key_id = self.razorpay_key_id or ""
            if self.app_env == "production" and key_id.startswith("rzp_test_"):
                raise ValueError("Razorpay test key used in production")
            if self.app_env == "staging" and key_id.startswith("rzp_live_"):
                raise ValueError("Razorpay live key used in staging")

        if self.app_env == "production" and self.database_migration_url:
            if _role(self.database_url) == _role(self.database_migration_url):
                raise ValueError("Runtime and migration database roles must differ in production")
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        return self.app_env in {"development", "test"}

    @property
    def is_test(self) -> bool:
        return self.app_env == "test"

    @property
    def session_cookie(self) -> str:
        # __Host- forbids a Domain attribute and forces Secure + Path=/.
        return self.session_cookie_name if self.is_development else "__Host-px_session"

    @property
    def oauth_cookie(self) -> str:
        return "px_oauth" if self.is_development else "__Host-px_oauth"

    @property
    def cookie_secure_effective(self) -> bool:
        return self.cookie_secure or not self.is_development

    @property
    def host_list(self) -> list[str]:
        return [h.strip() for h in self.allowed_hosts.split(",") if h.strip()]

    @property
    def trusted_proxies(self) -> list[str]:
        return [h.strip() for h in self.trusted_proxy_ips.split(",") if h.strip()]

    @property
    def google_configured(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def dev_login_available(self) -> bool:
        return self.is_development and self.dev_auth_enabled

    @property
    def allowed_origins(self) -> list[str]:
        origins = [self.frontend_origin]
        if self.is_development:
            dev_variants = [
                "http://localhost:5173",
                "http://127.0.0.1:5173",
                "http://localhost:3000",
                "http://127.0.0.1:3000",
                "http://localhost:8000",
                "http://127.0.0.1:8000",
            ]
            for v in dev_variants:
                if v not in origins:
                    origins.append(v)
        return origins

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and (self.supabase_service_role_key or self.supabase_key))

    @property
    def supabase_storage_configured(self) -> bool:
        return self.supabase_configured

    @property
    def storage_configured(self) -> bool:
        return bool(
            self.s3_endpoint_url and self.s3_access_key_id and self.s3_secret_access_key
        )



    @property
    def database_url_effective(self) -> str:
        return self.database_url

    @property
    def effective_storage_backend(self) -> str:
        if self.storage_backend in ("local", "supabase", "s3"):
            return self.storage_backend
        if self.supabase_storage_configured:
            return "supabase"
        if self.storage_configured:
            return "s3"
        return "local"


def _role(url: str) -> str:
    # postgresql+asyncpg://user:pass@host/db -> user
    try:
        return url.split("://", 1)[1].split("@", 1)[0].split(":")[0]
    except IndexError:
        return ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
