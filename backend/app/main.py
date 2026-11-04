"""Application factory: middleware, routers, lifespan and health checks."""

import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.deps import current_context
from app.api.v1 import admin, auth, me, participant, public, webhooks
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging, get_logger, request_id_ctx
from app.core.csrf import SAFE_METHODS
from app.db.session import dispose_engine, get_db, session_scope
from app.db.base import Base

logger = get_logger("app")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        request_id_ctx.set(request_id)
        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        )
        if request.url.path.startswith("/api/v1") and not request.url.path.startswith(
            "/api/v1/public/"
        ):
            response.headers["Cache-Control"] = "no-store"
        if get_settings().is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


class BodyLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        length = request.headers.get("content-length")
        if length and length.isdigit():
            if int(length) > get_settings().max_request_body_bytes:
                return JSONResponse(
                    {"error": {"code": "PAYLOAD_TOO_LARGE", "message": "Request body is too large."}},
                    status_code=413,
                )
        return await call_next(request)


class OriginCheckMiddleware(BaseHTTPMiddleware):
    """CSRF layer 2: mutations must come from the exact SPA origin. Webhooks are exempt."""

    async def dispatch(self, request: Request, call_next):
        if request.method not in SAFE_METHODS and not request.url.path.startswith(
            "/api/v1/webhooks/"
        ):
            origin = request.headers.get("origin")
            settings = get_settings()
            if origin:
                origin_clean = origin.rstrip("/")
                is_allowed = (
                    origin_clean in settings.allowed_origins
                    or origin_clean.endswith(".vercel.app")
                )
                if not is_allowed and settings.is_development:
                    if (
                        origin_clean.startswith("http://localhost:")
                        or origin_clean.startswith("http://127.0.0.1:")
                        or origin_clean.startswith("https://localhost:")
                        or origin_clean.startswith("https://127.0.0.1:")
                    ):
                        is_allowed = True

                if not is_allowed:
                    return JSONResponse(
                        {
                            "error": {
                                "code": "ORIGIN_REJECTED",
                                "message": "Cross-origin request rejected.",
                                "requestId": request_id_ctx.get(),
                            }
                        },
                        status_code=403,
                    )
        return await call_next(request)


async def _bootstrap_local_dev() -> None:
    settings = get_settings()
    from app.db.session import get_engine
    from app.seed import seed_if_empty

    if settings.auto_create_tables:
        try:
            async with get_engine().begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        except Exception as exc:
            logger.warning("schema_init_failed", error=str(exc))

    if settings.seed_demo_data or settings.is_development:
        try:
            async with session_scope() as db:
                await seed_if_empty(db)
        except Exception as exc:  # seeding must never stop the API from booting
            logger.warning("seed_failed", error=type(exc).__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(debug=settings.app_debug, json_logs=not settings.is_development)
    await _bootstrap_local_dev()
    logger.info("api_started", env=settings.app_env, payments=settings.payments_enabled)
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(debug=settings.app_debug, json_logs=not settings.is_development)
    app = FastAPI(
        title="Parallax Convention API",
        version="2.0.0",
        docs_url="/api/docs" if not settings.is_production else None,
        openapi_url="/api/openapi.json" if not settings.is_production else None,
        redoc_url=None,
        lifespan=lifespan,
    )

    if settings.is_development:
        app.add_middleware(
            CORSMiddleware,
            allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:[0-9]+)?$",
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
            allow_headers=["Content-Type", "X-CSRF-Token", "Idempotency-Key", "X-Request-ID"],
            expose_headers=["X-Request-ID", "Retry-After"],
            max_age=600,
        )
    else:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.allowed_origins,
            allow_origin_regex=r"^https://([a-zA-Z0-9-]+\.)*vercel\.app$",
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
            allow_headers=["Content-Type", "X-CSRF-Token", "Idempotency-Key", "X-Request-ID"],
            expose_headers=["X-Request-ID", "Retry-After"],
            max_age=600,
        )
    if settings.host_list and "*" not in settings.host_list:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.host_list)
    app.add_middleware(BodyLimitMiddleware)
    app.add_middleware(OriginCheckMiddleware)
    app.add_middleware(RequestContextMiddleware)

    register_error_handlers(app)

    app.include_router(public.router, prefix="/api/v1")
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(me.router, prefix="/api/v1")
    app.include_router(participant.router, prefix="/api/v1")
    app.include_router(admin.router, prefix="/api/v1")
    app.include_router(webhooks.router, prefix="/api/v1")

    # Top-level callback aliases for Google OAuth redirect URIs (/google/callback, /auth/, /auth)
    @app.get("/auth/", include_in_schema=False)
    @app.get("/auth", include_in_schema=False)
    @app.get("/google/callback", include_in_schema=False)
    async def top_level_google_callback(
        request: Request,
        code: str | None = None,
        state: str | None = None,
        error: str | None = None,
        db: AsyncSession = Depends(get_db),
    ):
        code = code or request.query_params.get("code")
        state = state or request.query_params.get("state")
        error = error or request.query_params.get("error")
        return await auth.google_callback(
            request=request, code=code, state=state, error=error, db=db
        )

    @app.get("/health/live", tags=["health"])
    @app.get("/healthz", include_in_schema=False)
    async def live() -> dict:
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    async def ready() -> JSONResponse:
        try:
            async with session_scope() as db:
                await db.execute(text("SELECT 1"))
        except Exception:
            return JSONResponse({"status": "unavailable"}, status_code=503)
        return JSONResponse({"status": "ok"})

    @app.get("/", include_in_schema=False)
    async def root() -> dict:
        return {"service": "parallax-api", "version": "2.0.0"}

    return app


app = create_app()
