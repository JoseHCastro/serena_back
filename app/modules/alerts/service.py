"""Alerts service — clinical alert management business logic."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.modules.alerts.repository import AlertRepository
from app.modules.alerts.schemas import (
    AlertAcknowledgeResponse,
    AlertCreate,
    AlertResponse,
    PaginatedAlerts,
)
from app.modules.alerts.models import AlertSeverity
from app.modules.users.models import User


class AlertService:
    """Business logic for clinical alert management.

    Args:
        db: The active AsyncSession injected via FastAPI dependency.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._repo = AlertRepository(db)

    async def list_alerts(
        self,
        page: int,
        page_size: int,
        session_id: uuid.UUID | None,
        patient_id: uuid.UUID | None,
        severity: AlertSeverity | None,
        unacknowledged_only: bool,
    ) -> PaginatedAlerts:
        """Return a paginated, filterable list of clinical alerts.

        Args:
            page: 1-indexed page number.
            page_size: Records per page.
            session_id: Optional session filter.
            patient_id: Optional patient filter.
            severity: Optional severity filter.
            unacknowledged_only: If True, return only unacknowledged alerts.

        Returns:
            PaginatedAlerts: Paginated result with metadata.
        """
        alerts, total = await self._repo.list_paginated(
            page=page,
            page_size=page_size,
            session_id=session_id,
            patient_id=patient_id,
            severity=severity,
            unacknowledged_only=unacknowledged_only,
        )
        return PaginatedAlerts(
            total=total,
            page=page,
            page_size=page_size,
            items=[AlertResponse.model_validate(a) for a in alerts],
        )

    async def acknowledge_alert(
        self, alert_id: uuid.UUID, current_user: User
    ) -> AlertAcknowledgeResponse:
        """Mark an alert as acknowledged by the current user.

        Args:
            alert_id: UUID of the alert to acknowledge.
            current_user: The authenticated user performing the acknowledgement.

        Returns:
            AlertAcknowledgeResponse: The updated acknowledgement data.

        Raises:
            NotFoundError: If the alert does not exist.
        """
        alert = await self._repo.get_by_id(alert_id)
        if not alert:
            raise NotFoundError("Alert")
        updated = await self._repo.acknowledge(alert, user_id=current_user.id)
        return AlertAcknowledgeResponse.model_validate(updated)
