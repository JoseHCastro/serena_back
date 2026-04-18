"""Auth repository — RefreshToken and AuditLog data access layer."""

import hashlib
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import AuditLog, RefreshToken


def _hash_token(raw_token: str) -> str:
    """Compute a SHA-256 hash of a raw token string for safe storage.

    Args:
        raw_token: The plain-text JWT refresh token.

    Returns:
        str: Hexadecimal SHA-256 digest.
    """
    return hashlib.sha256(raw_token.encode()).hexdigest()


class RefreshTokenRepository:
    """Data access object for RefreshToken entities.

    Args:
        db: The active AsyncSession injected via FastAPI dependency.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(
        self, user_id: uuid.UUID, raw_token: str, expires_at: datetime
    ) -> RefreshToken:
        """Persist a new hashed refresh token.

        Args:
            user_id: The owning user's UUID.
            raw_token: The plain-text refresh token (will be hashed before storage).
            expires_at: Absolute expiry datetime.

        Returns:
            RefreshToken: The newly created and flushed RefreshToken.
        """
        token = RefreshToken(
            user_id=user_id,
            token_hash=_hash_token(raw_token),
            expires_at=expires_at,
        )
        self._db.add(token)
        await self._db.flush()
        return token

    async def get_valid_by_raw(self, raw_token: str) -> RefreshToken | None:
        """Look up a valid (non-revoked, non-expired) refresh token by its raw value.

        Args:
            raw_token: The plain-text token to look up.

        Returns:
            RefreshToken | None: A valid RefreshToken, or None.
        """
        token_hash = _hash_token(raw_token)
        result = await self._db.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > datetime.now(UTC),
            )
        )
        return result.scalar_one_or_none()

    async def revoke(self, token: RefreshToken) -> None:
        """Mark a refresh token as revoked.

        Args:
            token: The RefreshToken ORM instance to revoke.
        """
        token.revoked_at = datetime.now(UTC)
        await self._db.flush()

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> int:
        """Revoke all active refresh tokens for a user (used on password change/logout-all).

        Args:
            user_id: The user whose tokens should all be revoked.

        Returns:
            int: Number of tokens revoked.
        """
        result = await self._db.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
            )
        )
        tokens = result.scalars().all()
        now = datetime.now(UTC)
        for token in tokens:
            token.revoked_at = now
        await self._db.flush()
        return len(tokens)


class AuditLogRepository:
    """Data access object for AuditLog entities (append-only).

    Args:
        db: The active AsyncSession injected via FastAPI dependency.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def log(
        self,
        action: str,
        user_id: uuid.UUID | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        payload: dict | None = None,
        ip_address: str | None = None,
    ) -> AuditLog:
        """Create an immutable audit log entry.

        Args:
            action: Short verb describing the action (e.g., "user.login").
            user_id: UUID of the acting user (None for system actions).
            entity_type: Type of affected resource (e.g., "Patient").
            entity_id: String representation of the affected resource's ID.
            payload: Arbitrary JSON metadata about the event.
            ip_address: Client IP address.

        Returns:
            AuditLog: The newly created log entry (flushed but not committed).
        """
        entry = AuditLog(
            action=action,
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload,
            ip_address=ip_address,
        )
        self._db.add(entry)
        await self._db.flush()
        return entry
