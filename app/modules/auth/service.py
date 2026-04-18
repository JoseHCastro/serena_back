"""Auth service — login, token refresh, and logout business logic."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import UnauthorizedError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    verify_password,
)
from app.modules.auth.repository import AuditLogRepository, RefreshTokenRepository
from app.modules.auth.schemas import AccessTokenResponse, TokenResponse
from app.modules.users.models import User
from app.modules.users.repository import UserRepository


class AuthService:
    """Business logic for authentication flows.

    Args:
        db: The active AsyncSession injected via FastAPI dependency.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._user_repo = UserRepository(db)
        self._token_repo = RefreshTokenRepository(db)
        self._audit_repo = AuditLogRepository(db)

    async def login(
        self, email: str, password: str, ip_address: str | None = None
    ) -> TokenResponse:
        """Authenticate a user and issue access + refresh tokens.

        Args:
            email: The user's email address.
            password: The plain-text password to verify.
            ip_address: Client IP for audit logging.

        Returns:
            TokenResponse: Access and refresh tokens.

        Raises:
            UnauthorizedError: If credentials are invalid or account is inactive.
        """
        user = await self._user_repo.get_by_email(email)
        if not user or not verify_password(password, user.hashed_password):
            await self._audit_repo.log(
                action="auth.login.failed",
                payload={"email": email},
                ip_address=ip_address,
            )
            raise UnauthorizedError("Invalid email or password.")
        if not user.is_active:
            raise UnauthorizedError("Account is deactivated.")

        access_token = create_access_token(
            subject=str(user.id),
            extra_claims={"role": user.role.name, "email": user.email},
        )
        refresh_token = create_refresh_token(subject=str(user.id))

        expires_at = datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        await self._token_repo.create(
            user_id=user.id, raw_token=refresh_token, expires_at=expires_at
        )
        await self._user_repo.update_last_login(user)
        await self._audit_repo.log(
            action="auth.login.success",
            user_id=user.id,
            entity_type="User",
            entity_id=str(user.id),
            ip_address=ip_address,
        )
        return TokenResponse(access_token=access_token, refresh_token=refresh_token)

    async def refresh(self, raw_refresh_token: str) -> AccessTokenResponse:
        """Issue a new access token from a valid refresh token.

        Implements token rotation: the old refresh token is revoked and
        a new one is issued alongside the new access token.

        Args:
            raw_refresh_token: The raw refresh token string from the client.

        Returns:
            AccessTokenResponse: A new access token.

        Raises:
            UnauthorizedError: If the refresh token is invalid or expired.
        """
        token_record = await self._token_repo.get_valid_by_raw(raw_refresh_token)
        if not token_record:
            raise UnauthorizedError("Refresh token is invalid or expired.")

        user = await self._user_repo.get_by_id(token_record.user_id)
        if not user or not user.is_active:
            raise UnauthorizedError("User account is inactive.")

        await self._token_repo.revoke(token_record)

        new_access_token = create_access_token(
            subject=str(user.id),
            extra_claims={"role": user.role.name, "email": user.email},
        )
        return AccessTokenResponse(access_token=new_access_token)

    async def logout(self, raw_refresh_token: str) -> None:
        """Revoke the supplied refresh token, effectively logging the user out.

        Args:
            raw_refresh_token: The refresh token to invalidate.

        Raises:
            UnauthorizedError: If the token is not found or already revoked.
        """
        token_record = await self._token_repo.get_valid_by_raw(raw_refresh_token)
        if not token_record:
            raise UnauthorizedError("Refresh token is invalid or already revoked.")
        await self._token_repo.revoke(token_record)
