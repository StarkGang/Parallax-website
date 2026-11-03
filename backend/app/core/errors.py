"""Stable error codes and handlers. Every error keeps the same envelope."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger, request_id_ctx

logger = get_logger("errors")


class AppError(Exception):
    status_code: int = 400
    code: str = "BAD_REQUEST"

    def __init__(
        self,
        message: str = "Request could not be processed.",
        *,
        details: Any = None,
        code: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code


class NotFound(AppError):
    status_code = 404
    code = "NOT_FOUND"


class Unauthenticated(AppError):
    status_code = 401
    code = "UNAUTHENTICATED"


class Forbidden(AppError):
    status_code = 403
    code = "FORBIDDEN"


class Conflict(AppError):
    status_code = 409
    code = "CONFLICT"


class ValidationFailed(AppError):
    status_code = 422
    code = "VALIDATION_FAILED"


class StepUpRequired(AppError):
    status_code = 403
    code = "STEP_UP_REQUIRED"


class RateLimited(AppError):
    status_code = 429
    code = "RATE_LIMITED"


def payload(code: str, message: str, details: Any = None) -> dict[str, Any]:
    body = {
        "error": {
            "code": code,
            "message": message,
            "requestId": request_id_ctx.get(),
        }
    }
    if details is not None:
        body["error"]["details"] = details
    return body


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        headers = {}
        if exc.status_code == 429:
            headers["Retry-After"] = "60"
        return JSONResponse(
            status_code=exc.status_code,
            content=payload(exc.code, exc.message, exc.details),
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {
                "field": ".".join(str(p) for p in err.get("loc", ()) if p not in ("body", "query")),
                "message": err.get("msg", "invalid"),
                "type": err.get("type", "value_error"),
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=payload("VALIDATION_FAILED", "Some fields are invalid.", details),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        codes = {
            401: "UNAUTHENTICATED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
        }
        return JSONResponse(
            status_code=exc.status_code,
            content=payload(codes.get(exc.status_code, "HTTP_ERROR"), str(exc.detail)),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_error", path=request.url.path, error=type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content=payload("INTERNAL_ERROR", "Something went wrong. Please try again."),
        )

