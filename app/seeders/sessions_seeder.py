"""Sessions seeder — creates realistic therapy sessions for seeded patients."""

import random
from datetime import UTC, datetime, timedelta

from loguru import logger
from sqlalchemy import func, select

from app.modules.patients.models import Patient
from app.modules.sessions.models import Session, SessionStatus
from app.seeders.base_seeder import BaseSeeder

SESSIONS_PER_PATIENT = 3
STATUSES = [SessionStatus.COMPLETED, SessionStatus.COMPLETED, SessionStatus.SCHEDULED]

SAMPLE_NOTES = [
    "El paciente mostró mejoría notable en el manejo de la ansiedad. Se reforzaron técnicas de respiración.",
    "Sesión enfocada en el procesamiento del duelo. Se identificaron patrones de pensamiento negativos.",
    "Trabajo en técnicas de mindfulness. El paciente reportó reducción del estrés durante la semana.",
    "Se exploraron situaciones desencadenantes de ataques de pánico. Buen nivel de introspección.",
    "El paciente expresó avances en la relación familiar. Se asignaron actividades de autorregulación.",
    None,
]


class SessionsSeeder(BaseSeeder):
    """Seeds realistic therapy sessions for all existing patients.

    Creates sessions with varied statuses, past and future scheduling,
    and realistic clinical notes.
    """

    async def run(self) -> None:
        """Create sample sessions if the table is empty."""
        existing_result = await self._db.execute(
            select(func.count()).select_from(Session)
        )
        if existing_result.scalar_one() > 0:
            logger.debug("Sessions already seeded, skipping.")
            return

        patients_result = await self._db.execute(select(Patient))
        patients = list(patients_result.scalars().all())
        if not patients:
            logger.warning("No patients found, skipping sessions seeder.")
            return

        now = datetime.now(UTC)
        session_objects = []

        for patient in patients:
            for i in range(SESSIONS_PER_PATIENT):
                days_ago = random.randint(5, 90) - (i * 30)
                scheduled_at = now - timedelta(days=days_ago)
                status = random.choice(STATUSES)

                started_at = None
                ended_at = None
                if status == SessionStatus.COMPLETED:
                    started_at = scheduled_at + timedelta(minutes=5)
                    session_duration = random.randint(45, 90)
                    ended_at = started_at + timedelta(minutes=session_duration)

                session = Session(
                    patient_id=patient.id,
                    therapist_id=patient.therapist_id,
                    scheduled_at=scheduled_at,
                    started_at=started_at,
                    ended_at=ended_at,
                    status=status,
                    notes=random.choice(SAMPLE_NOTES) if status == SessionStatus.COMPLETED else None,
                    video_url=f"https://res.cloudinary.com/demo/video/upload/sample_session_{i}.mp4" if status == SessionStatus.COMPLETED else None,
                    video_public_id=f"serena/sessions/sample_session_{patient.id}_{i}" if status == SessionStatus.COMPLETED else None,
                )
                session_objects.append(session)

        self._db.add_all(session_objects)
        await self._db.flush()
        logger.info("Seeded {} sessions", len(session_objects))
