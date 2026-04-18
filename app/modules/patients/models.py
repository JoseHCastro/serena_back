"""Patient ORM model — Digital Clinical Record."""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Patient(Base):
    """Represents a psychotherapy patient's clinical record (expediente clínico).

    Supports soft-delete: when deleted_at is set, the patient is considered
    inactive and should be excluded from standard queries.

    Attributes:
        id: UUID primary key.
        code: Human-readable unique identifier (e.g., "PAC-0001").
        first_name: Patient's first name(s).
        last_name: Patient's last name(s).
        birth_date: Date of birth for age calculation.
        gender: Gender identity string (open-ended for inclusivity).
        phone: Primary contact phone number.
        email: Optional email address for notifications.
        address: Full mailing address.
        emergency_contact_name: Name of the emergency contact person.
        emergency_contact_phone: Phone number of the emergency contact.
        medical_notes: Free-text clinical notes visible only to therapists.
        therapist_id: The therapist (User) responsible for this patient.
        is_active: Whether the patient currently has an active therapeutic process.
        created_at: Record creation timestamp.
        updated_at: Last modification timestamp.
        deleted_at: Soft-delete timestamp; NULL means record is active.
        therapist: The assigned therapist User object.
        sessions: All therapy sessions linked to this patient.
        alerts: All clinical alerts generated for this patient.
    """

    __tablename__ = "patients"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    code: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False, index=True
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(50), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    emergency_contact_name: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )
    emergency_contact_phone: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )
    medical_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    therapist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
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
    therapist: Mapped["User"] = relationship(  # noqa: F821
        "User", back_populates="patients", foreign_keys=[therapist_id], lazy="joined"
    )
    sessions: Mapped[list["Session"]] = relationship(  # noqa: F821
        "Session", back_populates="patient"
    )
    alerts: Mapped[list["Alert"]] = relationship(  # noqa: F821
        "Alert", back_populates="patient"
    )

    @property
    def full_name(self) -> str:
        """Return the patient's full display name."""
        return f"{self.first_name} {self.last_name}"

    def __repr__(self) -> str:
        return f"<Patient code={self.code!r} name={self.full_name!r}>"
