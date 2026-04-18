"""Alerts router — clinical alert management endpoints."""

import uuid

from fastapi import APIRouter, Query

from app.core.dependencies import CurrentUser, DbSession
from app.modules.alerts.models import AlertSeverity
from app.modules.alerts.schemas import AlertAcknowledgeResponse, PaginatedAlerts
from app.modules.alerts.service import AlertService

router = APIRouter(prefix="/alerts", tags=["Alerts"])


@router.get("/", response_model=PaginatedAlerts, summary="List clinical alerts")
async def list_alerts(
    db: DbSession,
    _: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session_id: uuid.UUID | None = Query(None),
    patient_id: uuid.UUID | None = Query(None),
    severity: AlertSeverity | None = Query(None),
    unacknowledged_only: bool = Query(False),
) -> PaginatedAlerts:
    """Return a paginated list of clinical alerts with optional filters."""
    return await AlertService(db).list_alerts(
        page, page_size, session_id, patient_id, severity, unacknowledged_only
    )


@router.post(
    "/{alert_id}/acknowledge",
    response_model=AlertAcknowledgeResponse,
    summary="Acknowledge a clinical alert",
)
async def acknowledge_alert(
    alert_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> AlertAcknowledgeResponse:
    """Mark a clinical alert as reviewed and acknowledged by the therapist."""
    return await AlertService(db).acknowledge_alert(alert_id, current_user)
