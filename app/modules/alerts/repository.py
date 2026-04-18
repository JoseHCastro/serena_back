"""Alerts repository — data access layer."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.alerts.models import Alert, AlertSeverity, AlertType


class AlertRepository:
    """Data access object for Alert entities."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_id(self, alert_id: uuid.UUID) -> Alert | None:
        """Fetch an alert by primary key."""
        result = await self._db.execute(select(Alert).where(Alert.id == alert_id))
        return result.scalar_one_or_none()

    async def list_paginated(
        self,
        page: int = 1,
        page_size: int = 20,
        session_id: uuid.UUID | None = None,
        patient_id: uuid.UUID | None = None,
        severity: AlertSeverity | None = None,
        unacknowledged_only: bool = False,
    ) -> tuple[list[Alert], int]:
        """Return a paginated, filterable list of alerts ordered by creation date.

        Args:
            page: 1-indexed page number.
            page_size: Records per page.
            session_id: Filter alerts by session.
            patient_id: Filter alerts by patient.
            severity: Filter by severity level.
            unacknowledged_only: If True, return only unacknowledged alerts.

        Returns:
            tuple[list[Alert], int]: Page of alerts and total matching count.
        """
        query = select(Alert)
        if session_id:
            query = query.where(Alert.session_id == session_id)
        if patient_id:
            query = query.where(Alert.patient_id == patient_id)
        if severity:
            query = query.where(Alert.severity == severity)
        if unacknowledged_only:
            query = query.where(Alert.is_acknowledged.is_(False))
        query = query.order_by(Alert.created_at.desc())

        count_result = await self._db.execute(
            select(func.count()).select_from(query.subquery())
        )
        total = count_result.scalar_one()

        offset = (page - 1) * page_size
        result = await self._db.execute(query.offset(offset).limit(page_size))
        return list(result.scalars().all()), total

    async def create(
        self,
        session_id: uuid.UUID,
        patient_id: uuid.UUID,
        alert_type: AlertType,
        severity: AlertSeverity,
        message: str,
        triggered_by_user_id: uuid.UUID | None = None,
    ) -> Alert:
        """Persist a new Alert.

        Args:
            session_id: The session during which the alert was triggered.
            patient_id: The patient this alert concerns.
            alert_type: Category of the alert.
            severity: Urgency level.
            message: Human-readable alert description.
            triggered_by_user_id: Optional user who triggered it.

        Returns:
            Alert: The newly created and flushed Alert instance.
        """
        alert = Alert(
            session_id=session_id,
            patient_id=patient_id,
            alert_type=alert_type,
            severity=severity,
            message=message,
            triggered_by_user_id=triggered_by_user_id,
        )
        self._db.add(alert)
        await self._db.flush()
        return alert

    async def acknowledge(self, alert: Alert, user_id: uuid.UUID) -> Alert:
        """Mark an alert as acknowledged by a specific user.

        Args:
            alert: The Alert ORM instance to acknowledge.
            user_id: The UUID of the user performing the acknowledgement.

        Returns:
            Alert: The updated and flushed Alert instance.
        """
        alert.is_acknowledged = True
        alert.acknowledged_at = datetime.now(UTC)
        alert.acknowledged_by_id = user_id
        await self._db.flush()
        return alert
