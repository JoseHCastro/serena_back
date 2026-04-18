"""Biometric analysis ORM models — Emotional snapshots, microexpressions, and analysis jobs."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AnalysisJobStatus(str, enum.Enum):
    """Lifecycle states for a post-session Celery analysis job.

    Attributes:
        PENDING: Job has been queued but not yet started.
        PROCESSING: Worker is actively processing the video.
        COMPLETED: Analysis finished successfully.
        FAILED: Analysis encountered an unrecoverable error.
    """

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class EmotionalSnapshot(Base):
    """A single frame's emotional analysis result during a therapy session.

    Stores confidence scores (0.0–1.0) for each of the 7 basic emotions
    as defined by Paul Ekman: happiness, sadness, anger, fear, disgust,
    surprise, and neutral.

    Attributes:
        id: UUID primary key.
        session_id: The session this snapshot belongs to.
        timestamp_offset: Seconds from session start when this frame was captured.
        happiness: Confidence score for happiness (0.0–1.0).
        sadness: Confidence score for sadness (0.0–1.0).
        anger: Confidence score for anger (0.0–1.0).
        fear: Confidence score for fear (0.0–1.0).
        disgust: Confidence score for disgust (0.0–1.0).
        surprise: Confidence score for surprise (0.0–1.0).
        neutral: Confidence score for neutral expression (0.0–1.0).
        dominant_emotion: The emotion with the highest confidence score.
        confidence: The confidence value of the dominant emotion.
        raw_data: Full JSON payload from the underlying AI model.
        created_at: Record creation timestamp.
        session: Back-reference to the parent Session.
    """

    __tablename__ = "emotional_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    timestamp_offset: Mapped[float] = mapped_column(Float, nullable=False)

    # Ekman's 7 basic emotions
    happiness: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    sadness: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    anger: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    fear: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    disgust: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    surprise: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    neutral: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    dominant_emotion: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    raw_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    session: Mapped["Session"] = relationship(  # noqa: F821
        "Session", back_populates="emotional_snapshots"
    )

    def __repr__(self) -> str:
        return (
            f"<EmotionalSnapshot session={self.session_id!r} "
            f"t={self.timestamp_offset}s dominant={self.dominant_emotion!r}>"
        )


class MicroexpressionEvent(Base):
    """A detected microexpression during a therapy session.

    Microexpressions are fleeting emotional displays (< 500ms) that may
    reveal suppressed emotions. Each event records the emotion, its
    intensity, and how long it lasted.

    Attributes:
        id: UUID primary key.
        session_id: The session during which the event occurred.
        timestamp_offset: Seconds from session start when detected.
        emotion_detected: The emotion identified (e.g., "fear", "disgust").
        intensity: Intensity score 0.0–1.0.
        duration_ms: Approximate display duration in milliseconds.
        frame_reference: Optional identifier linking to a specific video frame.
        created_at: Record creation timestamp.
        session: Back-reference to the parent Session.
    """

    __tablename__ = "microexpression_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    timestamp_offset: Mapped[float] = mapped_column(Float, nullable=False)
    emotion_detected: Mapped[str] = mapped_column(String(50), nullable=False)
    intensity: Mapped[float] = mapped_column(Float, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    frame_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    session: Mapped["Session"] = relationship(  # noqa: F821
        "Session", back_populates="microexpression_events"
    )

    def __repr__(self) -> str:
        return (
            f"<MicroexpressionEvent emotion={self.emotion_detected!r} "
            f"t={self.timestamp_offset}s duration={self.duration_ms}ms>"
        )


class BiometricAnalysisJob(Base):
    """Tracks the state of a Celery post-session video analysis task.

    One job per session. The frontend can poll this to show progress.

    Attributes:
        id: UUID primary key.
        session_id: One-to-one reference to the session being analysed.
        celery_task_id: The Celery task ID for status polling.
        status: Current job lifecycle state (see AnalysisJobStatus).
        result_summary: High-level summary statistics from the analysis.
        error_message: Human-readable error if the job failed.
        created_at: When the job was queued.
        updated_at: Last status update timestamp.
        session: Back-reference to the parent Session.
    """

    __tablename__ = "biometric_analysis_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[AnalysisJobStatus] = mapped_column(
        Enum(AnalysisJobStatus, name="analysis_job_status"),
        default=AnalysisJobStatus.PENDING,
        nullable=False,
    )
    result_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    session: Mapped["Session"] = relationship(  # noqa: F821
        "Session", back_populates="analysis_job"
    )

    def __repr__(self) -> str:
        return f"<BiometricAnalysisJob session={self.session_id!r} status={self.status.value!r}>"
