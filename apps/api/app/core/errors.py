from __future__ import annotations

from typing import Any

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.logging import get_logger, request_id_var

logger = get_logger(__name__)


class AppError(Exception):
    """Domain error with a stable machine-readable code."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


class NotFoundError(AppError):
    def __init__(self, resource: str, identifier: str) -> None:
        super().__init__(
            f"{resource}_not_found",
            f"{resource} '{identifier}' was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class UnsupportedFormatError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(
            "unsupported_format",
            message,
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        )


class UploadTooLargeError(AppError):
    def __init__(self, limit_bytes: int) -> None:
        super().__init__(
            "upload_too_large",
            f"Upload exceeds the {limit_bytes // (1024 * 1024)} MB limit.",
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )


class HostileLatexError(AppError):
    def __init__(self, findings: list[str]) -> None:
        super().__init__(
            "hostile_latex",
            "The uploaded LaTeX file contains constructs that are unsafe to compile.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details={"findings": findings},
        )


def _error_body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    request_id = request_id_var.get()
    if request_id:
        body["error"]["request_id"] = request_id
    return body


async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(exc.code, exc.message, exc.details),
    )


async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=_error_body(
            "validation_error",
            "Request validation failed.",
            [
                {"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]}
                for error in exc.errors()
            ],
        ),
    )


async def unexpected_error_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_error_body("internal_error", "An unexpected error occurred."),
    )
