"""Pydantic schemas for the Alerts module."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.modules.alerts.models import AlertSeverity, AlertType


class AlertResponse(BaseModel):
    """Clinical alert representation returned by the API."""

    id: uuid.UUID
    session_id: uuid.UUID
    patient_id: uuid.UUID
    alert_type: AlertType
    severity: AlertSeverity
    message: str
    is_acknowledged: bool
    acknowledged_at: datetime | None
    acknowledged_by_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AlertCreate(BaseModel):
    """Payload for manually creating a clinical alert (used internally by services)."""

    session_id: uuid.UUID
    patient_id: uuid.UUID
    alert_type: AlertType
    severity: AlertSeverity
    message: str = Field(..., min_length=5, max_length=1000)
    triggered_by_user_id: uuid.UUID | None = None


class AlertAcknowledgeResponse(BaseModel):
    """Response after acknowledging an alert."""

    id: uuid.UUID
    is_acknowledged: bool
    acknowledged_at: datetime
    acknowledged_by_id: uuid.UUID

    model_config = {"from_attributes": True}


class PaginatedAlerts(BaseModel):
    """Paginated list of alerts."""

    total: int
    page: int
    page_size: int
    items: list[AlertResponse]
