"""Alerts seeder — creates sample clinical alerts for completed sessions."""

import random

from loguru import logger
from sqlalchemy import select

from app.modules.alerts.models import Alert, AlertSeverity, AlertType
from app.modules.sessions.models import Session, SessionStatus
from app.seeders.base_seeder import BaseSeeder

ALERT_SCENARIOS = [
    {
        "alert_type": AlertType.HIGH_ANXIETY,
        "severity": AlertSeverity.HIGH,
        "message": "Alta ansiedad detectada a los 15 min de sesión. Fear=0.72, Sadness=0.61.",
    },
    {
        "alert_type": AlertType.HIGH_STRESS,
        "severity": AlertSeverity.MEDIUM,
        "message": "Estrés elevado detectado. Anger=0.68, Fear=0.55.",
    },
    {
        "alert_type": AlertType.CRITICAL_EMOTION,
        "severity": AlertSeverity.CRITICAL,
        "message": "Emoción crítica 'SADNESS' detectada con confianza 0.89.",
    },
    {
        "alert_type": AlertType.MICROEXPRESSION_CLUSTER,
        "severity": AlertSeverity.MEDIUM,
        "message": "Cluster de 4 microexpresiones de miedo en ventana de 2 minutos.",
    },
    {
        "alert_type": AlertType.SUDDEN_SHIFT,
        "severity": AlertSeverity.LOW,
        "message": "Cambio emocional abrupto de 'NEUTRAL' a 'ANGER' detectado.",
    },
]


class AlertsSeeder(BaseSeeder):
    """Seeds sample clinical alerts for completed sessions."""

    async def run(self) -> None:
        """Create sample alerts for completed sessions that have none."""
        result = await self._db.execute(
            select(Session).where(Session.status == SessionStatus.COMPLETED)
        )
        sessions = list(result.scalars().all())
        if not sessions:
            logger.warning("No completed sessions found, skipping alerts seeder.")
            return

        existing_count_result = await self._db.execute(
            select(Alert).limit(1)
        )
        if existing_count_result.scalar_one_or_none():
            logger.debug("Alerts already seeded, skipping.")
            return

        alert_objects = []
        for session in sessions:
            # 60% chance each session has 1–2 alerts
            if random.random() < 0.60:
                n_alerts = random.randint(1, 2)
                for scenario in random.sample(ALERT_SCENARIOS, k=min(n_alerts, len(ALERT_SCENARIOS))):
                    alert = Alert(
                        session_id=session.id,
                        patient_id=session.patient_id,
                        alert_type=scenario["alert_type"],
                        severity=scenario["severity"],
                        message=scenario["message"],
                        is_acknowledged=random.choice([True, False]),
                    )
                    alert_objects.append(alert)

        if alert_objects:
            self._db.add_all(alert_objects)
            await self._db.flush()
        logger.info("Seeded {} alerts", len(alert_objects))
