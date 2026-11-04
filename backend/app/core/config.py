"""Typed application settings.

Every value here has smart defaults. Production-first by default;
a single DEBUG_MODE=true environment variable enables dev mode.
"""

import os
import secrets
import tempfile
import urllib.parse
from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


def _sanitize_database_url(url: str | None) -> str:
    """Sanitize database URL:
    1. Fix unencoded special characters like '@' in password (e.g. postgres:pass@123@host:port).
    2. Convert direct Supabase URL (db.<ref>.supabase.co which is IPv6-only) to pooler URL
       (aws-0-<region>.pooler.supabase.com) because serverless functions (Vercel/Lambda) are IPv4-only.
    """
    if not url or "://" not in url:
        return url or ""

    scheme, rest = url.split("://", 1)

    query_part = ""
    if "?" in rest:
        rest, query_part = rest.split("?", 1)
        query_part = "?" + query_part

    path_part = ""
    if "/" in rest:
        rest, path_part = rest.split("/", 1)
        path_part = "/" + path_part

    if "@" in rest:
        last_at = rest.rfind("@")
        user_info = rest[:last_at]
        host_port = rest[last_at + 1 :]

        if ":" in user_info:
            user, password = user_info.split(":", 1)
            password_unquoted = urllib.parse.unquote(password)
            password_encoded = urllib.parse.quote(password_unquoted, safe="")
            user_info = f"{user}:{password_encoded}"

        # If direct Supabase host db.<ref>.supabase.co is provided in serverless (Vercel/Lambda):
        # Direct Supabase connections only resolve to IPv6, which fails in IPv4 serverless (Vercel/AWS Lambda).
        # Automatically redirect to the Supabase pooler host which has IPv4 support.
        is_serverless = bool(os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME") or os.getenv("SUPABASE_FORCE_POOLER"))
        if is_serverless and ".supabase.co" in host_port and host_port.startswith("db."):
            host_only = host_port.split(":")[0]
            port_only = host_port.split(":")[1] if ":" in host_port else "5432"
            ref = host_only[3:].split(".supabase.co")[0]
            region = os.getenv("SUPABASE_REGION", "ap-southeast-1")
            user_prefix = user_info.split(":", 1)[0]
            pass_suffix = user_info.split(":", 1)[1] if ":" in user_info else ""
            pooler_user = f"postgres.{ref}" if not user_prefix.startswith(f"postgres.{ref}") else user_prefix
            user_info = f"{pooler_user}:{pass_suffix}" if pass_suffix else pooler_user
            host_port = f"aws-0-{region}.pooler.supabase.com:{port_only}"

        rest = f"{user_info}@{host_port}"

    return f"{scheme}://{rest}{path_part}{query_part}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(BACKEND_DIR / ".env"), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Master switch: False = production mode (default), True = dev mode
    debug_mode: bool = False
    debug: bool = False
    app_debug: bool = False
    app_env: str = "production"

    # Simplified admin configuration (alias: ADMIN_EMAIL)
    admin_email: str | None = None
    bootstrap_owner_email: str | None = None

    # Network & URLs (zero-config, auto-detects Vercel / localhost)
    app_base_url: str = ""
    frontend_origin: str = ""
    allowed_hosts: str = "*,localhost,127.0.0.1,*.vercel.app,testserver"
    trusted_proxy_ips: str = "127.0.0.1,::1"

    # Database
    database_url: str = "sqlite+aiosqlite:///./var/parallax.db"
    supabase_db_url: str | None = None
    database_migration_url: str | None = None
    db_pool_size: int = 10
    db_statement_timeout_ms: int = 5000
    db_ssl: bool = False
    auto_create_tables: bool = True

    # Sessions / cookies (30-day persistent sessions)
    session_cookie_name: str = "px_session"
    session_idle_ttl_participant_min: int = 43200
    session_absolute_ttl_participant_min: int = 43200
    session_idle_ttl_staff_min: int = 43200
    session_absolute_ttl_staff_min: int = 43200
    cookie_secure: bool = True
    cookie_samesite: str = "lax"
    server_secret_key: str = Field(default="", description="Base secret key for HMAC and sessions")
    server_secret_key_previous: str | None = None
    totp_encryption_key: str | None = None

    # Auth & login switches
    mfa_enforced: bool = False
    allow_direct_login: bool = True
    dev_auth_enabled: bool = True
    dev_admin_email: str = "owner@parallax.local"
    dev_participant_email: str = "participant@parallax.local"

    # Google OAuth (optional)
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str = ""

    # Payments (Razorpay, optional)
    payments_enabled: bool = False
    razorpay_key_id: str | None = None
    razorpay_key_secret: str | None = None
    razorpay_webhook_secret: str | None = None

    # Storage (Supabase or S3, optional)
    supabase_url: str | None = None
    supabase_key: str | None = None
    supabase_service_role_key: str | None = None
    supabase_storage_bucket: str = "parallax"
    storage_backend: str = "auto"
    s3_endpoint_url: str | None = None
    s3_bucket_private: str = "parallax-private"
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    signed_url_ttl_seconds: int = 120

    # Email (optional)
    email_enabled: bool = False
    email_provider_api_key: str | None = None
    email_from: str | None = None

    # Limits
    max_request_body_bytes: int = 1_048_576
    max_upload_bytes_document: int = 3_145_728
    max_upload_bytes_icon_svg: int = 65_536
    max_upload_bytes_icon_png: int = 262_144

    # Bootstrap & monitoring
    sentry_dsn: str | None = None
    seed_demo_data: bool = True

    @model_validator(mode="after")
    def _validate(self) -> "Settings":
        # Check single DEBUG_MODE switch
        is_debug_explicit = bool(
            self.debug_mode
            or self.debug
            or os.getenv("DEBUG_MODE", "").lower() in {"1", "true", "yes"}
            or os.getenv("DEBUG", "").lower() in {"1", "true", "yes"}
        )

        if is_debug_explicit:
            self.app_env = "development"
            self.app_debug = True
            self.cookie_secure = False
        elif self.app_env in {"development", "dev"}:
            self.app_debug = True
            self.cookie_secure = False
        elif self.app_env == "test":
            self.cookie_secure = False
        else:
            self.app_env = "production"
            self.app_debug = False
            self.cookie_secure = True

        # Resolve admin_email alias
        if self.admin_email and not self.bootstrap_owner_email:
            self.bootstrap_owner_email = self.admin_email

        # Resolve FRONTEND_ORIGIN with zero-config smart defaults
        vercel_url = os.getenv("VERCEL_URL") or os.getenv("VERCEL_BRANCH_URL")
        if not self.frontend_origin or self.frontend_origin == "http://localhost:5173":
            if os.getenv("VERCEL"):
                self.frontend_origin = "https://parallax-iste.vercel.app"
            elif vercel_url:
                self.frontend_origin = f"https://{vercel_url}"
            elif self.is_development:
                self.frontend_origin = "http://localhost:5173"
            else:
                self.frontend_origin = "https://parallax-iste.vercel.app"
        elif not self.is_development and self.frontend_origin.startswith("http://localhost") and (vercel_url or os.getenv("VERCEL")):
            self.frontend_origin = "https://parallax-iste.vercel.app"
        elif not self.is_development and self.frontend_origin.startswith("http://") and not self.frontend_origin.startswith("http://localhost"):
            self.frontend_origin = "https://" + self.frontend_origin[len("http://") :]
        self.frontend_origin = self.frontend_origin.rstrip("/")

        if not self.app_base_url:
            self.app_base_url = self.frontend_origin

        if not self.allowed_hosts or self.allowed_hosts.strip() == "*":
            self.allowed_hosts = "*,localhost,127.0.0.1,*.vercel.app,testserver"

        # Resolve SERVER_SECRET_KEY (persists across restarts to prevent session invalidation)
        if not self.server_secret_key:
            if self.app_env in {"development", "test"}:
                key_file = Path("var/.server_secret_key")
                try:
                    if key_file.exists():
                        self.server_secret_key = key_file.read_text("utf-8").strip()
                    else:
                        key_file.parent.mkdir(parents=True, exist_ok=True)
                        new_k = secrets.token_hex(32)
                        key_file.write_text(new_k, "utf-8")
                        self.server_secret_key = new_k
                except Exception:
                    self.server_secret_key = secrets.token_hex(32)
            else:
                raise ValueError("SERVER_SECRET_KEY must be set in the environment or .env")

        if len(self.server_secret_key.encode()) < 32:
            raise ValueError("SERVER_SECRET_KEY must be at least 32 bytes")

        if self.app_env not in {"development", "test"}:
            weak_samples = ("change-me", "changeme", "placeholder", "dev-only")
            if any(sample in self.server_secret_key.lower() for sample in weak_samples):
                raise ValueError("SERVER_SECRET_KEY cannot be a placeholder or example value outside development")

        if os.getenv("VERCEL") and (
            self.database_url.startswith("sqlite+aiosqlite:///./var/")
            or self.database_url.startswith("sqlite+aiosqlite://var/")
            or self.database_url == "sqlite+aiosqlite:///./var/parallax.db"
        ):
            self.database_url = f"sqlite+aiosqlite:///{tempfile.gettempdir()}/parallax.db"

        # Google OAuth Redirect URI - matches authorized URIs in Google Cloud Console:
        # https://parallax-iste.vercel.app/google/callback
        if not self.google_redirect_uri:
            if os.getenv("VERCEL") or not self.is_development:
                self.google_redirect_uri = "https://parallax-iste.vercel.app/google/callback"
            elif self.frontend_origin:
                self.google_redirect_uri = f"{self.frontend_origin}/google/callback"
        elif ".vercel.app" in self.google_redirect_uri and not self.google_redirect_uri.startswith("https://parallax-iste.vercel.app"):
            self.google_redirect_uri = "https://parallax-iste.vercel.app/google/callback"

        if self.supabase_db_url and (
            "var/parallax.db" in self.database_url or not self.database_url
        ):
            self.database_url = self.supabase_db_url

        self.database_url = _sanitize_database_url(self.database_url)
        if self.database_migration_url:
            self.database_migration_url = _sanitize_database_url(self.database_migration_url)

        if self.database_url.startswith("postgresql://"):
            self.database_url = "postgresql+asyncpg://" + self.database_url[len("postgresql://") :]
        elif self.database_url.startswith("postgres://"):
            self.database_url = "postgresql+asyncpg://" + self.database_url[len("postgres://") :]

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
        return self.session_cookie_name or "px_session"

    @property
    def oauth_cookie(self) -> str:
        return "px_oauth"

    @property
    def cookie_secure_effective(self) -> bool:
        return self.cookie_secure or not self.is_development

    @property
    def host_list(self) -> list[str]:
        hosts = [h.strip() for h in self.allowed_hosts.split(",") if h.strip()]
        for default_host in ("*.vercel.app", "testserver"):
            if default_host not in hosts:
                hosts.append(default_host)
        vercel_url = os.getenv("VERCEL_URL")
        if vercel_url and vercel_url not in hosts:
            hosts.append(vercel_url)
        return hosts

    @property
    def trusted_proxies(self) -> list[str]:
        return [h.strip() for h in self.trusted_proxy_ips.split(",") if h.strip()]

    @property
    def google_configured(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def dev_login_available(self) -> bool:
        return self.allow_direct_login or (self.is_development and self.dev_auth_enabled)

    @property
    def allowed_origins(self) -> list[str]:
        origins = ["https://parallax-iste.vercel.app"]
        if self.frontend_origin and self.frontend_origin not in origins:
            origins.append(self.frontend_origin)
        vercel_url = os.getenv("VERCEL_URL")
        if vercel_url:
            origins.append(f"https://{vercel_url}")
        branch_url = os.getenv("VERCEL_BRANCH_URL")
        if branch_url and f"https://{branch_url}" not in origins:
            origins.append(f"https://{branch_url}")
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
    try:
        return url.split("://", 1)[1].split("@", 1)[0].split(":")[0]
    except IndexError:
        return ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
