"""Biometric repository — emotional snapshots, microexpressions, and analysis jobs."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.biometric.models import (
    AnalysisJobStatus,
    BiometricAnalysisJob,
    EmotionalSnapshot,
    MicroexpressionEvent,
)


class EmotionalSnapshotRepository:
    """Data access object for EmotionalSnapshot entities."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(self, **kwargs) -> EmotionalSnapshot:
        """Persist a new EmotionalSnapshot."""
        snapshot = EmotionalSnapshot(**kwargs)
        self._db.add(snapshot)
        await self._db.flush()
        return snapshot

    async def list_by_session(self, session_id: uuid.UUID) -> list[EmotionalSnapshot]:
        """Retrieve all snapshots for a session ordered by timestamp_offset."""
        result = await self._db.execute(
            select(EmotionalSnapshot)
            .where(EmotionalSnapshot.session_id == session_id)
            .order_by(EmotionalSnapshot.timestamp_offset)
        )
        return list(result.scalars().all())

    async def get_session_averages(self, session_id: uuid.UUID) -> dict:
        """Compute average emotion scores for a session (used in compare module)."""
        result = await self._db.execute(
            select(
                func.avg(EmotionalSnapshot.happiness).label("avg_happiness"),
                func.avg(EmotionalSnapshot.sadness).label("avg_sadness"),
                func.avg(EmotionalSnapshot.anger).label("avg_anger"),
                func.avg(EmotionalSnapshot.fear).label("avg_fear"),
                func.avg(EmotionalSnapshot.disgust).label("avg_disgust"),
                func.avg(EmotionalSnapshot.surprise).label("avg_surprise"),
                func.avg(EmotionalSnapshot.neutral).label("avg_neutral"),
                func.count().label("count"),
            ).where(EmotionalSnapshot.session_id == session_id)
        )
        row = result.one()
        averages = {
            "avg_happiness": round(row.avg_happiness or 0, 4),
            "avg_sadness": round(row.avg_sadness or 0, 4),
            "avg_anger": round(row.avg_anger or 0, 4),
            "avg_fear": round(row.avg_fear or 0, 4),
            "avg_disgust": round(row.avg_disgust or 0, 4),
            "avg_surprise": round(row.avg_surprise or 0, 4),
            "avg_neutral": round(row.avg_neutral or 0, 4),
            "snapshot_count": row.count,
        }
        emotion_avgs = {k.replace("avg_", ""): v for k, v in averages.items() if k.startswith("avg_")}
        averages["dominant_overall"] = max(emotion_avgs, key=emotion_avgs.get)
        return averages

    async def bulk_create(self, snapshots: list[dict]) -> list[EmotionalSnapshot]:
        """Persist multiple snapshots in one flush (used by Celery post-session task)."""
        objects = [EmotionalSnapshot(**s) for s in snapshots]
        self._db.add_all(objects)
        await self._db.flush()
        return objects


class MicroexpressionRepository:
    """Data access object for MicroexpressionEvent entities."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(self, **kwargs) -> MicroexpressionEvent:
        """Persist a new MicroexpressionEvent."""
        event = MicroexpressionEvent(**kwargs)
        self._db.add(event)
        await self._db.flush()
        return event

    async def list_by_session(self, session_id: uuid.UUID) -> list[MicroexpressionEvent]:
        """Retrieve all microexpression events for a session."""
        result = await self._db.execute(
            select(MicroexpressionEvent)
            .where(MicroexpressionEvent.session_id == session_id)
            .order_by(MicroexpressionEvent.timestamp_offset)
        )
        return list(result.scalars().all())


class BiometricJobRepository:
    """Data access object for BiometricAnalysisJob entities."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_session(self, session_id: uuid.UUID) -> BiometricAnalysisJob | None:
        """Fetch the analysis job linked to a session."""
        result = await self._db.execute(
            select(BiometricAnalysisJob).where(
                BiometricAnalysisJob.session_id == session_id
            )
        )
        return result.scalar_one_or_none()

    async def create(self, session_id: uuid.UUID) -> BiometricAnalysisJob:
        """Create a new PENDING analysis job."""
        job = BiometricAnalysisJob(session_id=session_id, status=AnalysisJobStatus.PENDING)
        self._db.add(job)
        await self._db.flush()
        return job

    async def update_status(
        self,
        job: BiometricAnalysisJob,
        status: AnalysisJobStatus,
        celery_task_id: str | None = None,
        result_summary: dict | None = None,
        error_message: str | None = None,
    ) -> BiometricAnalysisJob:
        """Update the status and optional metadata of an analysis job."""
        job.status = status
        if celery_task_id is not None:
            job.celery_task_id = celery_task_id
        if result_summary is not None:
            job.result_summary = result_summary
        if error_message is not None:
            job.error_message = error_message
        await self._db.flush()
        return job
