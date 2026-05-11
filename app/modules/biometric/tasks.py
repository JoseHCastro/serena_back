"""Celery tasks for post-session biometric video analysis."""

import asyncio
import uuid

import cv2
import httpx
import numpy as np
from loguru import logger

from app.workers.celery_app import celery_app


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def analyze_session_video(self, session_id_str: str, video_url: str) -> dict:
    """Celery task: download and analyze a session video from Cloudinary.

    This task runs in the Celery worker process (not the FastAPI event loop).
    It creates its own sync database session, downloads the video, extracts
    frames at regular intervals, runs emotion detection on each frame,
    persists EmotionalSnapshot records, and updates the job status.

    Args:
        session_id_str: String representation of the session UUID.
        video_url: Cloudinary secure URL of the session video.

    Returns:
        dict: Summary of the analysis (emotion averages, total frames).
    """
    session_id = uuid.UUID(session_id_str)
    logger.info("Starting post-session analysis | session={}", session_id)

    async def _run() -> dict:
        import tempfile
        from pathlib import Path

        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        from app.core.config import settings
        from app.modules.biometric.emotion_engine import EmotionEngine
        from app.modules.biometric.models import AnalysisJobStatus
        from app.modules.biometric.repository import (
            BiometricJobRepository,
            EmotionalSnapshotRepository,
        )

        engine_db = create_async_engine(settings.DATABASE_URL, echo=False)
        factory = async_sessionmaker(engine_db, class_=AsyncSession, expire_on_commit=False)

        async with factory() as db:
            job_repo = BiometricJobRepository(db)
            snapshot_repo = EmotionalSnapshotRepository(db)
            from app.modules.media.service import MediaService
            from fastapi import UploadFile
            import io

            media_service = MediaService()
            job = await job_repo.get_by_session(session_id)
            if not job:
                logger.error("No analysis job found for session {}", session_id)
                return {}

            await job_repo.update_status(job, status=AnalysisJobStatus.PROCESSING)
            await db.commit()

            try:
                # ── Download video from Cloudinary ──────────────
                logger.info("Downloading video | url={}", video_url[:80])
                async with httpx.AsyncClient(timeout=120.0) as client:
                    resp = await client.get(video_url)
                    resp.raise_for_status()
                    video_bytes = resp.content

                # Write to temp file for OpenCV
                tmp_dir = Path(tempfile.mkdtemp())
                tmp_video = tmp_dir / "session_video.mp4"
                tmp_video.write_bytes(video_bytes)

                # ── Extract frames and analyze ──────────────────
                emotion_engine = EmotionEngine.get_instance()
                cap = cv2.VideoCapture(str(tmp_video))

                if not cap.isOpened():
                    raise RuntimeError(f"Failed to open video: {tmp_video}")

                fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                duration = total_frames / fps

                # Sample 1 frame every 2 seconds
                sample_interval = 2.0
                frame_indices = [
                    int(t * fps) for t in np.arange(0, duration, sample_interval)
                ]

                logger.info(
                    "Video: {:.1f}s, {:.0f} fps, {} total frames, sampling {} frames",
                    duration, fps, total_frames, len(frame_indices),
                )

                snapshots = []
                for i, frame_idx in enumerate(frame_indices):
                    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                    ret, frame = cap.read()
                    if not ret:
                        continue

                    timestamp_offset = frame_idx / fps

                    # Analyze emotion from the BGR frame
                    analysis = emotion_engine.analyze_numpy(frame)

                    # --- Cloudinary Upload ---
                    # Convert BGR to JPEG bytes
                    _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    frame_io = io.BytesIO(buffer)
                    
                    # Mocking an UploadFile for the MediaService
                    class MockUploadFile:
                        def __init__(self, content):
                            self.content = content
                        async def read(self):
                            return self.content

                    upload_result = await media_service.upload_image(
                        MockUploadFile(frame_io.getvalue()),
                        folder=f"serena/sessions/{session_id}/frames"
                    )

                    snapshots.append({
                        "session_id": session_id,
                        "timestamp_offset": round(timestamp_offset, 2),
                        "happiness": analysis["happiness"],
                        "sadness": analysis["sadness"],
                        "anger": analysis["anger"],
                        "fear": analysis["fear"],
                        "disgust": analysis["disgust"],
                        "surprise": analysis["surprise"],
                        "neutral": analysis["neutral"],
                        "dominant_emotion": analysis["dominant_emotion"],
                        "confidence": analysis["confidence"],
                        "raw_data": {"frame_url": upload_result.secure_url}
                    })

                    if (i + 1) % 5 == 0:
                        logger.info("Processed {}/{} frames...", i + 1, len(frame_indices))

                cap.release()

                # Clean up temp file
                tmp_video.unlink(missing_ok=True)
                tmp_dir.rmdir()

                # ── Persist results ─────────────────────────────
                if snapshots:
                    await snapshot_repo.bulk_create(snapshots)

                averages = await snapshot_repo.get_session_averages(session_id)
                result_summary = {
                    **averages,
                    "video_url": video_url,
                    "frames_analyzed": len(snapshots),
                    "video_duration_seconds": round(duration, 1),
                }

                await job_repo.update_status(
                    job,
                    status=AnalysisJobStatus.COMPLETED,
                    result_summary=result_summary,
                )
                await db.commit()
                logger.info(
                    "Post-session analysis complete | session={} frames={}",
                    session_id, len(snapshots),
                )
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
                await engine_db.dispose()

    return asyncio.run(_run())
