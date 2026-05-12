"""Pydantic schemas for the Sessions module."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.modules.patients.schemas import PatientSummary
from app.modules.sessions.models import SessionStatus
from app.modules.users.schemas import UserSummary


class SessionCreate(BaseModel):
    """Payload for scheduling a new therapy session."""

    patient_id: uuid.UUID
    scheduled_at: datetime
    notes: str | None = None


class SessionUpdate(BaseModel):
    """Partial update payload for session notes and scheduling."""

    scheduled_at: datetime | None = None
    notes: str | None = None


class SessionResponse(BaseModel):
    """Full session record returned by the API."""

    id: uuid.UUID
    patient_id: uuid.UUID
    therapist_id: uuid.UUID
    scheduled_at: datetime
    started_at: datetime | None
    ended_at: datetime | None
    status: SessionStatus
    video_url: str | None
    video_public_id: str | None
    notes: str | None
    patient: PatientSummary
    therapist: UserSummary
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SessionSummary(BaseModel):
    """Compact session representation for embedded use."""

    id: uuid.UUID
    scheduled_at: datetime
    status: SessionStatus

    model_config = {"from_attributes": True}


class PaginatedSessions(BaseModel):
    """Paginated list of sessions."""

    total: int
    page: int
    page_size: int
    items: list[SessionResponse]


class EmotionalTimelinePoint(BaseModel):
    """A single point on the emotional timeline chart.

    Used for the dashboard visualization endpoint.
    """

    timestamp_offset: float = Field(..., description="Seconds from session start")
    happiness: float
    sadness: float
    anger: float
    fear: float
    disgust: float
    surprise: float
    neutral: float
    dominant_emotion: str
    confidence: float
    raw_data: dict | None = None


class EmotionalTimeline(BaseModel):
    """Full emotional timeline for a session, ready for chart rendering."""

    session_id: uuid.UUID
    total_snapshots: int
    duration_seconds: float | None
    points: list[EmotionalTimelinePoint]
