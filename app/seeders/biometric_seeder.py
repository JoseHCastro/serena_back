"""Biometric seeder — creates emotional snapshots and microexpressions for completed sessions."""

import random

from loguru import logger
from sqlalchemy import select

from app.modules.biometric.models import EmotionalSnapshot, MicroexpressionEvent
from app.modules.sessions.models import Session, SessionStatus
from app.seeders.base_seeder import BaseSeeder

EMOTIONS = ["happiness", "sadness", "anger", "fear", "disgust", "surprise", "neutral"]
SNAPSHOTS_PER_SESSION = 20  # One snapshot every ~3 minutes for a 60-min session


def _random_emotions() -> dict:
    """Generate normalized random emotion scores summing to ~1.0."""
    scores = [random.random() for _ in EMOTIONS]
    total = sum(scores)
    normalized = [round(s / total, 4) for s in scores]
    dominant_idx = normalized.index(max(normalized))
    return {
        "happiness": normalized[0],
        "sadness": normalized[1],
        "anger": normalized[2],
        "fear": normalized[3],
        "disgust": normalized[4],
        "surprise": normalized[5],
        "neutral": normalized[6],
        "dominant_emotion": EMOTIONS[dominant_idx],
        "confidence": normalized[dominant_idx],
    }


class BiometricSeeder(BaseSeeder):
    """Seeds emotional snapshots and microexpression events for completed sessions."""

    async def run(self) -> None:
        """Create biometric data for all completed sessions that have no snapshots yet."""
        result = await self._db.execute(
            select(Session).where(Session.status == SessionStatus.COMPLETED)
        )
        sessions = list(result.scalars().all())
        if not sessions:
            logger.warning("No completed sessions found, skipping biometric seeder.")
            return

        snapshot_objects = []
        micro_objects = []

        for session in sessions:
            existing = await self._db.execute(
                select(EmotionalSnapshot).where(
                    EmotionalSnapshot.session_id == session.id
                ).limit(1)
            )
            if existing.scalar_one_or_none():
                continue

            duration = 3600.0  # Default 60 min
            if session.started_at and session.ended_at:
                duration = (session.ended_at - session.started_at).total_seconds()

            interval = duration / SNAPSHOTS_PER_SESSION

            for i in range(SNAPSHOTS_PER_SESSION):
                timestamp = round(i * interval, 1)
                emotions = _random_emotions()
                snapshot_objects.append(
                    EmotionalSnapshot(
                        session_id=session.id,
                        timestamp_offset=timestamp,
                        **emotions,
                    )
                )

                # ~30% chance of a microexpression at this timestamp
                if random.random() < 0.30:
                    micro_objects.append(
                        MicroexpressionEvent(
                            session_id=session.id,
                            timestamp_offset=timestamp + random.uniform(0.1, 0.9),
                            emotion_detected=random.choice(EMOTIONS[:6]),
                            intensity=round(random.uniform(0.4, 1.0), 3),
                            duration_ms=random.randint(50, 499),
                        )
                    )

        if snapshot_objects:
            self._db.add_all(snapshot_objects)
            await self._db.flush()

        if micro_objects:
            self._db.add_all(micro_objects)
            await self._db.flush()

        logger.info(
            "Seeded {} snapshots and {} microexpressions",
            len(snapshot_objects),
            len(micro_objects),
        )
