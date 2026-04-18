"""Celery tasks for post-session biometric video analysis."""

import asyncio
import uuid

from loguru import logger

from app.workers.celery_app import celery_app


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def analyze_session_video(self, session_id_str: str, video_url: str) -> dict:
    """Celery task: download and analyze a session video from Cloudinary.

    This task runs in the Celery worker process (not the FastAPI event loop).
    It creates its own sync database session, processes the video frame by
    frame, persists EmotionalSnapshot records, and updates the job status.

    Replace the mock frame generation with a real model (e.g., DeepFace):
        from deepface import DeepFace
        result = DeepFace.analyze(frame, actions=["emotion"])

    Args:
        session_id_str: String representation of the session UUID.
        video_url: Cloudinary secure URL of the session video.

    Returns:
        dict: Summary of the analysis (emotion averages, total frames).
    """
    session_id = uuid.UUID(session_id_str)
    logger.info("Starting post-session analysis | session={}", session_id)

    async def _run() -> dict:
        import random

        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

        from app.core.config import settings
        from app.modules.biometric.models import AnalysisJobStatus
        from app.modules.biometric.repository import (
            BiometricJobRepository,
            EmotionalSnapshotRepository,
        )

        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with factory() as db:
            job_repo = BiometricJobRepository(db)
            snapshot_repo = EmotionalSnapshotRepository(db)

            job = await job_repo.get_by_session(session_id)
            if not job:
                logger.error("No analysis job found for session {}", session_id)
                return {}

            await job_repo.update_status(job, status=AnalysisJobStatus.PROCESSING)
            await db.commit()

            try:
                # --- Mock: simulate 30 frames at 2-second intervals ---
                emotions = ["happiness", "sadness", "anger", "fear", "disgust", "surprise", "neutral"]
                snapshots = []
                for i in range(30):
                    scores = [random.random() for _ in emotions]
                    total = sum(scores)
                    normalized = [round(s / total, 4) for s in scores]
                    dominant_idx = normalized.index(max(normalized))
                    snapshots.append({
                        "session_id": session_id,
                        "timestamp_offset": float(i * 2),
                        "happiness": normalized[0],
                        "sadness": normalized[1],
                        "anger": normalized[2],
                        "fear": normalized[3],
                        "disgust": normalized[4],
                        "surprise": normalized[5],
                        "neutral": normalized[6],
                        "dominant_emotion": emotions[dominant_idx],
                        "confidence": normalized[dominant_idx],
                    })

                await snapshot_repo.bulk_create(snapshots)
                averages = await snapshot_repo.get_session_averages(session_id)
                result_summary = {**averages, "video_url": video_url, "frames_analyzed": len(snapshots)}

                await job_repo.update_status(
                    job,
                    status=AnalysisJobStatus.COMPLETED,
                    result_summary=result_summary,
                )
                await db.commit()
                logger.info("Post-session analysis complete | session={}", session_id)
                return result_summary

            except Exception as exc:
                await job_repo.update_status(
                    job,
                    status=AnalysisJobStatus.FAILED,
                    error_message=str(exc),
                )
                await db.commit()
                logger.exception("Post-session analysis failed | session={}", session_id)
                raise self.retry(exc=exc)
            finally:
                await engine.dispose()

    return asyncio.run(_run())
