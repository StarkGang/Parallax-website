"""Application factory: middleware, routers, lifespan and health checks."""

import mimetypes
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import Headers
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.deps import current_context
from app.api.v1 import (
    admin,
    admin_registration,
    auth,
    me,
    participant,
    public,
    razorpay_checkout,
    registration,
    webhooks,
)
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging, get_logger, request_id_ctx
from app.core.csrf import SAFE_METHODS
from app.core.rate_limit import limiter
from app.db.session import dispose_engine, get_db, session_scope
from app.db.base import Base

logger = get_logger("app")

# When a production build exists, the API serves the SPA itself so the whole
# product runs as one app on one origin (no separate frontend service).
# SPA_DIST lets a container or VPS point at the built files explicitly.
SPA_DIST = Path(
    os.getenv("SPA_DIST") or Path(__file__).resolve().parents[2] / "frontend" / "dist"
)
SPA_INDEX = SPA_DIST / "index.html"
SPA_RESERVED_PREFIXES = {"api", "health", "healthz", "auth", "google", "docs", "openapi.json"}

# Serve non-text assets with the right MIME types when the API hosts the SPA.
for _ext, _type in (
    (".glb", "model/gltf-binary"),
    (".gltf", "model/gltf+json"),
    (".webp", "image/webp"),
    (".woff2", "font/woff2"),
    (".webmanifest", "application/manifest+json"),
):
    mimetypes.add_type(_type, _ext)


def _spa_index() -> Path | None:
    return SPA_INDEX if SPA_INDEX.is_file() else None


class SPAStaticFiles(StaticFiles):
    """Static files for the built SPA, with client-route history fallback.

    Unknown paths without a file extension fall back to index.html so deep
    links work. Unknown asset paths stay 404 on purpose: answering a missing
    .glb/.webp with HTML breaks model and image loaders silently.
    """

    async def get_response(self, path: str, scope) -> Response:
        # StaticFiles normalises to OS separators, so check both slash styles.
        segment = path.replace("\\", "/").split("/", 1)[0].lower()
        if segment in SPA_RESERVED_PREFIXES:
            raise HTTPException(status_code=404, detail="Not found")
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            # StaticFiles raises Starlette's HTTPException, not FastAPI's subclass.
            if exc.status_code != 404:
                raise
            if Path(path).suffix:
                raise
        fallback = await super().get_response("index.html", scope)
        if fallback.status_code != 200:
            raise HTTPException(status_code=404, detail="Not found")
        return fallback


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        supplied_request_id = (request.headers.get("x-request-id") or "").strip()
        request_id = (
            supplied_request_id[:64]
            if supplied_request_id and supplied_request_id.isprintable()
            else uuid.uuid4().hex
        )
        request_id_ctx.set(request_id)
        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=()"
        # A locked-down CSP is correct for JSON API responses, but applying it
        # to the SPA document would block its own scripts and styles.
        # Use setdefault: some routes set their own policy. Document content,
        # for example, must allow framing by this same origin so the admin and
        # participant PDF review views can display it.
        if request.url.path.startswith(("/api", "/health")):
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
            )
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        # Hashed build output can be cached forever; the document must always
        # be revalidated so a new deploy is picked up.
        if request.url.path.startswith("/assets/"):
            response.headers.setdefault(
                "Cache-Control", "public, max-age=31536000, immutable"
            )
        elif request.url.path in ("/", "/index.html"):
            response.headers.setdefault("Cache-Control", "no-cache")
        if request.url.path.startswith("/api/v1") and not request.url.path.startswith(
            "/api/v1/public/"
        ):
            response.headers["Cache-Control"] = "no-store"
        if get_settings().is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


class BodyLimitMiddleware:
    """Reject oversized bodies, including chunked requests without a length."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)

        settings = get_settings()
        length = Headers(scope=scope).get("content-length")
        path = scope.get("path", "")
        # JSON gets the tight global limit. Multipart document/asset routes
        # get the document ceiling plus multipart overhead, otherwise a
        # valid 2-5 MB ID card is rejected before the route can validate it.
        upload_paths = (
            "/registration/documents/",
            "/verification",
            "/admin/banner-upload",
            "/admin/icons",
        )
        # Largest legitimate upload is the admin banner (10 MB); document and
        # photo routes cap themselves far lower. Do not buffer more than that
        # plus multipart overhead, so a streamed request cannot pin memory.
        upload_limit = max(10 * 1024 * 1024, settings.max_upload_bytes_document) + 1_048_576
        limit = upload_limit if any(p in path for p in upload_paths) else settings.max_request_body_bytes
        if length and length.isdigit() and int(length) > limit:
            response = JSONResponse(
                {"error": {"code": "PAYLOAD_TOO_LARGE", "message": "Request body is too large."}},
                status_code=413,
            )
            return await response(scope, receive, send)

        # Chunked requests have no Content-Length, so read the body with a cap
        # and replay it to the app. Without this, a streamed request could
        # buffer without limit and exhaust memory.
        if not (length and length.isdigit()):
            chunks: list[bytes] = []
            total = 0
            while True:
                message = await receive()
                if message.get("type") == "http.disconnect":
                    return
                if message.get("type") != "http.request":
                    continue
                chunk = message.get("body", b"")
                total += len(chunk)
                if total > limit:
                    response = JSONResponse(
                        {"error": {"code": "PAYLOAD_TOO_LARGE", "message": "Request body is too large."}},
                        status_code=413,
                    )
                    return await response(scope, receive, send)
                chunks.append(chunk)
                if not message.get("more_body", False):
                    break
            body = b"".join(chunks)
            replayed = False

            async def replay():
                nonlocal replayed
                if not replayed:
                    replayed = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return {"type": "http.disconnect"}

            return await self.app(scope, replay, send)

        return await self.app(scope, receive, send)


class OriginCheckMiddleware(BaseHTTPMiddleware):
    """CSRF layer 2: mutations must come from the exact SPA origin. Webhooks are exempt."""

    async def dispatch(self, request: Request, call_next):
        if request.method not in SAFE_METHODS and not (
            request.url.path.startswith("/api/v1/webhooks/")
            or request.url.path.endswith("/create-order")
            or request.url.path.endswith("/verify-payment")
        ):
            origin = request.headers.get("origin")
            settings = get_settings()
            if origin:
                origin_clean = origin.rstrip("/")
                # Localhost origins are a development convenience only; a
                # production deployment must not treat them as trusted.
                dev_origin = (not settings.is_production) and (
                    origin_clean.startswith("http://localhost:")
                    or origin_clean.startswith("http://127.0.0.1:")
                    or origin_clean.startswith("https://localhost:")
                    or origin_clean.startswith("https://127.0.0.1:")
                )
                is_allowed = origin_clean in settings.allowed_origins or dev_origin

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
            allow_headers=[
                "Authorization",
                "Content-Type",
                "X-CSRF-Token",
                "Idempotency-Key",
                "X-Request-ID",
            ],
            expose_headers=["X-Request-ID", "Retry-After"],
            max_age=600,
        )
    else:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.allowed_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
            allow_headers=[
                "Authorization",
                "Content-Type",
                "X-CSRF-Token",
                "Idempotency-Key",
                "X-Request-ID",
            ],
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
    app.include_router(registration.router, prefix="/api/v1")
    app.include_router(admin.router, prefix="/api/v1")
    app.include_router(admin_registration.router, prefix="/api/v1")
    app.include_router(webhooks.router, prefix="/api/v1")
    app.include_router(razorpay_checkout.router, prefix="/api")
    app.include_router(razorpay_checkout.router, prefix="/api/v1")

    # Top-level callback aliases for Google OAuth redirect URIs (/google/callback, /auth/, /auth)
    @app.get(
        "/auth/",
        include_in_schema=False,
        dependencies=[Depends(limiter("auth_callback", 20, 600))],
    )
    @app.get(
        "/auth",
        include_in_schema=False,
        dependencies=[Depends(limiter("auth_callback", 20, 600))],
    )
    @app.get(
        "/google/callback",
        include_in_schema=False,
        dependencies=[Depends(limiter("auth_callback", 20, 600))],
    )
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

    # Mounted last so API, health, docs and auth routes always win.
    if _spa_index() is not None:
        app.mount("/", SPAStaticFiles(directory=SPA_DIST, html=True), name="spa")
    else:

        @app.get("/", include_in_schema=False)
        async def root() -> dict:
            return {"service": "parallax-api", "version": "2.0.0"}

    return app


app = create_app()
