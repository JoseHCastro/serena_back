"""Pydantic schemas for the Biometric analysis module."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.modules.biometric.models import AnalysisJobStatus


# ---------------------------------------------------------------------------
# Emotional Snapshot schemas
# ---------------------------------------------------------------------------


class SnapshotCreate(BaseModel):
    """Payload for submitting a real-time emotional analysis frame.

    The timestamp_offset is relative to the session start, in seconds.
    All emotion scores must sum to approximately 1.0.
    """

    timestamp_offset: float = Field(..., ge=0, description="Seconds from session start")
    happiness: float = Field(..., ge=0.0, le=1.0)
    sadness: float = Field(..., ge=0.0, le=1.0)
    anger: float = Field(..., ge=0.0, le=1.0)
    fear: float = Field(..., ge=0.0, le=1.0)
    disgust: float = Field(..., ge=0.0, le=1.0)
    surprise: float = Field(..., ge=0.0, le=1.0)
    neutral: float = Field(..., ge=0.0, le=1.0)
    dominant_emotion: str = Field(..., max_length=50)
    confidence: float = Field(..., ge=0.0, le=1.0)
    raw_data: dict | None = None


class SnapshotResponse(SnapshotCreate):
    """Emotional snapshot representation returned by the API."""

    id: uuid.UUID
    session_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Microexpression schemas
# ---------------------------------------------------------------------------


class MicroexpressionCreate(BaseModel):
    """Payload for recording a detected microexpression event."""

    timestamp_offset: float = Field(..., ge=0)
    emotion_detected: str = Field(..., max_length=50)
    intensity: float = Field(..., ge=0.0, le=1.0)
    duration_ms: int = Field(..., gt=0, le=500, description="Microexpressions are < 500ms")
    frame_reference: str | None = None


class MicroexpressionResponse(MicroexpressionCreate):
    """Microexpression event representation returned by the API."""

    id: uuid.UUID
    session_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Analysis Job schemas
# ---------------------------------------------------------------------------


class AnalysisJobResponse(BaseModel):
    """Status of a post-session Celery analysis job."""

    id: uuid.UUID
    session_id: uuid.UUID
    celery_task_id: str | None
    status: AnalysisJobStatus
    result_summary: dict | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# WebSocket frame payload
# ---------------------------------------------------------------------------


class FramePayload(BaseModel):
    """Payload sent by the client over WebSocket for real-time analysis.

    The client encodes a video frame as base64 and sends this JSON message.
    The server decodes the frame, runs the emotion detector, and broadcasts
    a SnapshotResponse back.
    """

    frame_base64: str = Field(..., description="Base64-encoded JPEG/PNG image frame")
    timestamp_offset: float = Field(..., ge=0, description="Seconds from session start")


# ---------------------------------------------------------------------------
# Comparative dashboard schemas
# ---------------------------------------------------------------------------


class SessionComparePoint(BaseModel):
    """Aggregated statistics for one session, used in the comparison module."""

    session_id: uuid.UUID
    scheduled_at: datetime
    avg_happiness: float
    avg_sadness: float
    avg_anger: float
    avg_fear: float
    avg_disgust: float
    avg_surprise: float
    avg_neutral: float
    dominant_overall: str
    snapshot_count: int


class ComparativeReport(BaseModel):
    """Multi-session comparative data for dashboard visualization."""

    patient_id: uuid.UUID
    sessions: list[SessionComparePoint]
