"""Reports router — PDF report download endpoints."""

import uuid

from fastapi import APIRouter
from fastapi.responses import Response

from app.core.dependencies import CurrentUser, DbSession
from app.modules.reports.service import ReportService

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get(
    "/sessions/{session_id}/pdf",
    summary="Download PDF report for a session",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def download_session_report(
    session_id: uuid.UUID, db: DbSession, _: CurrentUser
) -> Response:
    """Generate and download a PDF clinical report for a therapy session.

    The report includes session metadata, therapist notes, emotional analysis
    averages, and a table of all detected microexpressions.

    Args:
        session_id: UUID of the session to report on.
        db: Database session.

    Returns:
        Response: PDF file as an octet-stream download.
    """
    pdf_bytes = await ReportService(db).generate_session_pdf(session_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=session_{session_id}.pdf"
        },
    )


"""Alerts router — clinical alert management endpoints."""

import uuid

from fastapi import APIRouter, Query

from app.core.dependencies import CurrentUser, DbSession
from app.modules.alerts.models import AlertSeverity
from app.modules.alerts.schemas import AlertAcknowledgeResponse, AlertResponse, PaginatedAlerts
from app.modules.alerts.service import AlertService

alerts_router = APIRouter(prefix="/alerts", tags=["Alerts"])


@alerts_router.get("/", response_model=PaginatedAlerts, summary="List clinical alerts")
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
    """Return a paginated list of clinical alerts with optional filters.

    Args:
        db: Database session.
        page: Page number.
        page_size: Records per page.
        session_id: Filter by session.
        patient_id: Filter by patient.
        severity: Filter by severity level.
        unacknowledged_only: If True, return only unacknowledged alerts.

    Returns:
        PaginatedAlerts: Paginated alert list.
    """
    return await AlertService(db).list_alerts(
        page, page_size, session_id, patient_id, severity, unacknowledged_only
    )


@alerts_router.post(
    "/{alert_id}/acknowledge",
    response_model=AlertAcknowledgeResponse,
    summary="Acknowledge a clinical alert",
)
async def acknowledge_alert(
    alert_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> AlertAcknowledgeResponse:
    """Mark a clinical alert as reviewed and acknowledged by the therapist.

    Args:
        alert_id: UUID of the alert to acknowledge.
        db: Database session.
        current_user: The authenticated user acknowledging the alert.

    Returns:
        AlertAcknowledgeResponse: Acknowledgement timestamp and user.
    """
    return await AlertService(db).acknowledge_alert(alert_id, current_user)
