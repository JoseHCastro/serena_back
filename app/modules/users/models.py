"""Users and Roles ORM models."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Role(Base):
    """Represents an access control role (e.g., admin, therapist, receptionist).

    Attributes:
        id: UUID primary key.
        name: Unique, machine-readable role identifier.
        description: Human-readable description of the role's purpose.
        created_at: Timestamp when the role was created.
        users: Back-reference to all users assigned this role.
    """

    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    users: Mapped[list["User"]] = relationship("User", back_populates="role")

    def __repr__(self) -> str:
        return f"<Role name={self.name!r}>"


class User(Base):
    """Represents an authenticated system user (therapist, admin, receptionist).

    Attributes:
        id: UUID primary key.
        email: Unique login email address.
        hashed_password: bcrypt-hashed password; never store plain text.
        full_name: Display name for the user.
        role_id: Foreign key to the Role table.
        is_active: Soft-disable flag; inactive users cannot log in.
        last_login: Timestamp of most recent successful authentication.
        created_at: Record creation timestamp.
        updated_at: Last modification timestamp (auto-updated).
        deleted_at: Soft-delete timestamp; NULL means the record is active.
        role: Eagerly-loadable Role relationship.
        patients: Patients assigned to this therapist.
        sessions: Sessions conducted by this therapist.
        refresh_tokens: Active refresh token records for this user.
        audit_logs: Audit log entries authored by this user.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    role: Mapped["Role"] = relationship("Role", back_populates="users", lazy="joined")
    patients: Mapped[list["Patient"]] = relationship(  # noqa: F821
        "Patient", back_populates="therapist", foreign_keys="Patient.therapist_id"
    )
    sessions: Mapped[list["Session"]] = relationship(  # noqa: F821
        "Session", back_populates="therapist", foreign_keys="Session.therapist_id"
    )
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(  # noqa: F821
        "RefreshToken", back_populates="user"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(  # noqa: F821
        "AuditLog", back_populates="user", foreign_keys="AuditLog.user_id"
    )

    def __repr__(self) -> str:
        return f"<User email={self.email!r} role={self.role.name!r}>"
