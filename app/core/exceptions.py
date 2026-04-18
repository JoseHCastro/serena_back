"""
Custom exception classes and FastAPI exception handlers.

Defines a hierarchy of domain exceptions that map cleanly to HTTP status
codes, and registers global handlers so all errors return a consistent
JSON envelope: {"detail": "...", "code": "..."}.
"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from loguru import logger


# ---------------------------------------------------------------------------
# Base domain exception
# ---------------------------------------------------------------------------


class SerenaException(Exception):
    """Base class for all Serena application exceptions.

    Args:
        detail: Human-readable error message for the API consumer.
        code: Machine-readable error code for frontend handling.
        status_code: HTTP status code to return.
    """

    def __init__(
        self,
        detail: str,
        code: str = "SERENA_ERROR",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
    ) -> None:
        self.detail = detail
        self.code = code
        self.status_code = status_code
        super().__init__(detail)


# ---------------------------------------------------------------------------
# 400 Bad Request
# ---------------------------------------------------------------------------


class BadRequestError(SerenaException):
    """Raised when the request payload is invalid or logically inconsistent."""

    def __init__(self, detail: str, code: str = "BAD_REQUEST") -> None:
        super().__init__(detail, code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# 401 Unauthorized
# ---------------------------------------------------------------------------


class UnauthorizedError(SerenaException):
    """Raised when authentication credentials are missing or invalid."""

    def __init__(self, detail: str = "Could not validate credentials.") -> None:
        super().__init__(detail, "UNAUTHORIZED", status.HTTP_401_UNAUTHORIZED)


# ---------------------------------------------------------------------------
# 403 Forbidden
# ---------------------------------------------------------------------------


class ForbiddenError(SerenaException):
    """Raised when the authenticated user lacks permission for the action."""

    def __init__(self, detail: str = "You do not have permission to perform this action.") -> None:
        super().__init__(detail, "FORBIDDEN", status.HTTP_403_FORBIDDEN)


# ---------------------------------------------------------------------------
# 404 Not Found
# ---------------------------------------------------------------------------


class NotFoundError(SerenaException):
    """Raised when a requested resource does not exist."""

    def __init__(self, resource: str = "Resource") -> None:
        super().__init__(f"{resource} not found.", "NOT_FOUND", status.HTTP_404_NOT_FOUND)


# ---------------------------------------------------------------------------
# 409 Conflict
# ---------------------------------------------------------------------------


class ConflictError(SerenaException):
    """Raised when a creation/update violates a uniqueness constraint."""

    def __init__(self, detail: str, code: str = "CONFLICT") -> None:
        super().__init__(detail, code, status.HTTP_409_CONFLICT)


# ---------------------------------------------------------------------------
# Global exception handler registration
# ---------------------------------------------------------------------------


def register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers on the FastAPI application.

    Catches SerenaException subclasses and unhandled exceptions, returning
    a consistent JSON response envelope in both cases.

    Args:
        app: The FastAPI application instance to register handlers on.
    """

    @app.exception_handler(SerenaException)
    async def serena_exception_handler(
        request: Request, exc: SerenaException
    ) -> JSONResponse:
        logger.warning(
            "Domain exception | code={} | path={} | detail={}",
            exc.code,
            request.url.path,
            exc.detail,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "code": exc.code},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception("Unhandled exception on {}", request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "An internal server error occurred.",
                "code": "INTERNAL_ERROR",
            },
        )
