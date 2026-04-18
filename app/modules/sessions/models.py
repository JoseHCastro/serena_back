"""Session ORM model — Therapy session history and video linkage."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class SessionStatus(str, enum.Enum):
    """Lifecycle states of a therapy session.

    Attributes:
        SCHEDULED: Session has been booked but not yet started.
        ACTIVE: Session is currently in progress (recording may be running).
        COMPLETED: Session finished normally.
        CANCELLED: Session was cancelled before it started.
    """

    SCHEDULED = "scheduled"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Session(Base):
    """Represents a single therapy session between a therapist and a patient.

    Links scheduling data, session notes, Cloudinary video reference, and
    biometric analysis results. Videos are stored on Cloudinary; only the
    URL and public_id are persisted here.

    Attributes:
        id: UUID primary key.
        patient_id: The patient this session belongs to.
        therapist_id: The therapist who conducted the session.
        scheduled_at: The planned start datetime.
        started_at: When the session actually began (set on start action).
        ended_at: When the session actually ended (set on end action).
        status: Current lifecycle state (see SessionStatus).
        video_url: Cloudinary secure URL of the session recording.
        video_public_id: Cloudinary asset public ID for deletion/management.
        notes: Therapist's post-session clinical notes.
        created_at: Record creation timestamp.
        updated_at: Last modification timestamp.
        patient: The patient this session belongs to.
        therapist: The therapist who conducted the session.
        emotional_snapshots: All biometric analysis frames for this session.
        microexpression_events: Detected microexpression events in this session.
        analysis_job: The post-session Celery analysis job record.
        alerts: All clinical alerts raised during this session.
    """

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    therapist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus, name="session_status"),
        default=SessionStatus.SCHEDULED,
        nullable=False,
    )
    video_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    video_public_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    patient: Mapped["Patient"] = relationship(  # noqa: F821
        "Patient", back_populates="sessions", lazy="joined"
    )
    therapist: Mapped["User"] = relationship(  # noqa: F821
        "User", back_populates="sessions", foreign_keys=[therapist_id], lazy="joined"
    )
    emotional_snapshots: Mapped[list["EmotionalSnapshot"]] = relationship(  # noqa: F821
        "EmotionalSnapshot", back_populates="session", cascade="all, delete-orphan"
    )
    microexpression_events: Mapped[list["MicroexpressionEvent"]] = relationship(  # noqa: F821
        "MicroexpressionEvent", back_populates="session", cascade="all, delete-orphan"
    )
    analysis_job: Mapped["BiometricAnalysisJob | None"] = relationship(  # noqa: F821
        "BiometricAnalysisJob", back_populates="session", uselist=False
    )
    alerts: Mapped[list["Alert"]] = relationship(  # noqa: F821
        "Alert", back_populates="session"
    )

    def __repr__(self) -> str:
        return f"<Session id={self.id!r} status={self.status.value!r}>"
