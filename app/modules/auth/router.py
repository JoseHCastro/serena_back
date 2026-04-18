"""Auth router — login, refresh, and logout endpoints."""

from fastapi import APIRouter, Request

from app.core.dependencies import DbSession
from app.modules.auth.schemas import AccessTokenResponse, LoginRequest, RefreshRequest, TokenResponse
from app.modules.auth.service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse, summary="User login")
async def login(payload: LoginRequest, request: Request, db: DbSession) -> TokenResponse:
    """Authenticate a user and return access + refresh tokens.

    Args:
        payload: Email and password credentials.
        request: FastAPI request (used to extract client IP for audit log).
        db: Database session.

    Returns:
        TokenResponse: JWT access and refresh token pair.
    """
    ip = request.client.host if request.client else None
    return await AuthService(db).login(payload.email, payload.password, ip)


@router.post("/refresh", response_model=AccessTokenResponse, summary="Refresh access token")
async def refresh_token(payload: RefreshRequest, db: DbSession) -> AccessTokenResponse:
    """Issue a new access token using a valid refresh token.

    Args:
        payload: The refresh token string.
        db: Database session.

    Returns:
        AccessTokenResponse: A new short-lived access token.
    """
    return await AuthService(db).refresh(payload.refresh_token)


@router.post("/logout", status_code=204, summary="Logout — revoke refresh token")
async def logout(payload: RefreshRequest, db: DbSession) -> None:
    """Revoke the provided refresh token, invalidating the user's session.

    Args:
        payload: The refresh token to revoke.
        db: Database session.
    """
    await AuthService(db).logout(payload.refresh_token)
