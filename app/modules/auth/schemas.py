"""Pydantic schemas for the Auth module — tokens and login."""

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    """Credentials payload for the login endpoint."""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Response returned after a successful login or token refresh."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """Payload for requesting a new access token using a refresh token."""

    refresh_token: str


class AccessTokenResponse(BaseModel):
    """Response containing only a new access token (used on refresh)."""

    access_token: str
    token_type: str = "bearer"
