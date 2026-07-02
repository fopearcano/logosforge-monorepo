"""Structured API errors and exception handlers.

Routes raise :class:`ApiError` (or the convenience :func:`not_found`) and the
handlers translate it into a stable JSON envelope::

    {"error": {"code": "not_found", "message": "Scene 5 not found"}}
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    """An error with an HTTP status, a machine code and a human message."""

    def __init__(self, status_code: int, message: str, code: str = "error") -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.code = code


def not_found(message: str) -> ApiError:
    return ApiError(404, message, code="not_found")


def bad_request(message: str) -> ApiError:
    return ApiError(400, message, code="bad_request")


def forbidden(message: str) -> ApiError:
    return ApiError(403, message, code="forbidden")


def not_implemented(message: str) -> ApiError:
    return ApiError(501, message, code="not_implemented")


def _envelope(code: str, message: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _handle_api_error(_: Request, exc: ApiError) -> JSONResponse:
        return _envelope(exc.code, exc.message, exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return _envelope("validation_error", str(exc.errors()), 422)
