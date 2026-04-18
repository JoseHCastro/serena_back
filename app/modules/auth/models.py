"""Auth ORM models: RefreshToken and AuditLog."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class RefreshToken(Base):
    """Stores hashed refresh tokens for token rotation and revocation.

    Instead of storing the raw token (which would be a security risk),
    we store a SHA-256 hash of the token value. This allows us to look
    up and invalidate tokens without exposing the raw secret.

    Attributes:
        id: UUID primary key.
        user_id: The owner of this token.
        token_hash: SHA-256 hash of the raw refresh token string.
        expires_at: Absolute expiry timestamp.
        revoked_at: Set when the token is explicitly revoked (logout/rotation).
        created_at: Record creation timestamp.
        user: Back-reference to the owning User.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="refresh_tokens")  # noqa: F821

    @property
    def is_valid(self) -> bool:
        """Return True if the token has not been revoked and has not expired."""
        from datetime import UTC
        return self.revoked_at is None and self.expires_at > datetime.now(UTC)

    def __repr__(self) -> str:
        return f"<RefreshToken user_id={self.user_id!r} valid={self.is_valid}>"


class AuditLog(Base):
    """Immutable audit trail of sensitive actions performed by users.

    Every destructive or sensitive operation (login, delete, role change, etc.)
    should create an AuditLog entry. Records are never updated or deleted.

    Attributes:
        id: UUID primary key.
        user_id: The user who performed the action (nullable for system actions).
        action: Short verb describing the action (e.g., "user.login", "patient.delete").
        entity_type: The type of resource affected (e.g., "Patient", "Session").
        entity_id: The UUID of the affected resource (as string for flexibility).
        payload: Arbitrary JSON metadata about the event.
        ip_address: Client IP address at the time of the action.
        created_at: Immutable timestamp of when the action occurred.
        user: The user who triggered this log entry.
    """

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    # Relationships
    user: Mapped["User | None"] = relationship(  # noqa: F821
        "User", back_populates="audit_logs", foreign_keys=[user_id]
    )

    def __repr__(self) -> str:
        return f"<AuditLog action={self.action!r} entity={self.entity_type}/{self.entity_id}>"
