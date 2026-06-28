"""Biometric service — emotional analysis engine (real-time + post-session)."""

import base64
import uuid
from datetime import UTC, datetime

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, NotFoundError
from app.modules.alerts.models import AlertSeverity, AlertType
from app.modules.alerts.repository import AlertRepository
from app.modules.biometric.emotion_engine import EmotionEngine
from app.modules.biometric.models import AnalysisJobStatus
from app.modules.biometric.repository import (
    BiometricJobRepository,
    EmotionalSnapshotRepository,
    MicroexpressionRepository,
)
from app.modules.biometric.schemas import (
    AnalysisJobResponse,
    ComparativeReport,
    MicroexpressionCreate,
    MicroexpressionResponse,
    SessionComparePoint,
    SnapshotCreate,
    SnapshotResponse,
)
from app.modules.sessions.models import Session
from app.modules.sessions.repository import SessionRepository

# ---------------------------------------------------------------------------
# Alert thresholds (can be moved to config/DB settings in the future)
# ---------------------------------------------------------------------------
ANXIETY_THRESHOLD = 0.70   # fear + sadness combined average triggers high_anxiety
STRESS_THRESHOLD = 0.65    # anger + fear combined triggers high_stress
CRITICAL_EMOTION_THRESHOLD = 0.85  # single emotion dominance


def _analyze_frame(frame_base64: str, timestamp_offset: float) -> dict:
    """Analyze a single base64-encoded video frame for facial emotions.

    Uses the EmotionEngine singleton which loads an ONNX model for real
    inference. If no model file is available, it gracefully falls back
    to mock random data for development.

    The engine performs:
        1. Base64 decode → image bytes
        2. Face detection and cropping (MediaPipe)
        3. Emotion classification (ONNX Runtime )
        4. Softmax → probability distribution over 7 emotions

    Args:
        frame_base64: Base64-encoded image frame (JPEG/PNG).
        timestamp_offset: Seconds from session start.

    Returns:
        dict: Emotion scores (happiness, sadness, anger, fear, disgust,
              surprise, neutral) plus dominant_emotion and confidence.
    """
    engine = EmotionEngine.get_instance()
    return engine.analyze_base64(frame_base64)


class BiometricService:
    """Business logic for emotional analysis (real-time and post-session).

    Args:
        db: The active AsyncSession injected via FastAPI dependency.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._session_repo = SessionRepository(db)
        self._snapshot_repo = EmotionalSnapshotRepository(db)
        self._micro_repo = MicroexpressionRepository(db)
        self._job_repo = BiometricJobRepository(db)
        self._alert_repo = AlertRepository(db)

    async def _get_active_session(self, session_id: uuid.UUID) -> Session:
        """Fetch a session and validate it is in ACTIVE state.

        Args:
            session_id: UUID of the session.

        Returns:
            Session: The active session ORM instance.

        Raises:
            NotFoundError: If the session does not exist.
            BadRequestError: If the session is not active.
        """
        from app.modules.sessions.models import SessionStatus

        session = await self._session_repo.get_by_id(session_id)
        if not session:
            raise NotFoundError("Session")
        if session.status != SessionStatus.ACTIVE:
            raise BadRequestError("Biometric data can only be submitted for active sessions.")
        return session

    async def save_snapshot(
        self, session_id: uuid.UUID, payload: SnapshotCreate
    ) -> SnapshotResponse:
        """Persist a real-time emotional snapshot and check alert thresholds.

        Args:
            session_id: UUID of the active session.
            payload: Validated SnapshotCreate schema.

        Returns:
            SnapshotResponse: The persisted snapshot.
        """
        session = await self._get_active_session(session_id)
        snapshot = await self._snapshot_repo.create(
            session_id=session_id, **payload.model_dump()
        )
        await self._check_and_create_alerts(session, payload)
        return SnapshotResponse.model_validate(snapshot)

    async def analyze_frame(
        self, session_id: uuid.UUID, frame_base64: str, timestamp_offset: float
    ) -> SnapshotResponse:
        """Analyze a single base64-encoded frame and persist the result.

        This method is called from the WebSocket endpoint to process frames
        in real time. Replace _analyze_frame_mock with a real AI model.

        Args:
            session_id: UUID of the active session.
            frame_base64: Base64-encoded image frame.
            timestamp_offset: Seconds from session start.

        Returns:
            SnapshotResponse: The analysis result persisted as a snapshot.
        """
        session = await self._get_active_session(session_id)
        analysis = _analyze_frame(frame_base64, timestamp_offset)
        snapshot_data = SnapshotCreate(timestamp_offset=timestamp_offset, **analysis)
        snapshot = await self._snapshot_repo.create(
            session_id=session_id, **snapshot_data.model_dump()
        )
        
        # Dispatch background task to upload the frame to Cloudinary
        from app.modules.biometric.tasks import upload_frame_background
        upload_frame_background.delay(str(session_id), frame_base64, str(snapshot.id))
        
        await self._check_and_create_alerts(session, snapshot_data)
        return SnapshotResponse.model_validate(snapshot)

    async def save_microexpression(
        self, session_id: uuid.UUID, payload: MicroexpressionCreate
    ) -> MicroexpressionResponse:
        """Persist a detected microexpression event.

        Args:
            session_id: UUID of the active session.
            payload: Validated MicroexpressionCreate schema.

        Returns:
            MicroexpressionResponse: The persisted microexpression event.
        """
        await self._get_active_session(session_id)
        event = await self._micro_repo.create(
            session_id=session_id, **payload.model_dump()
        )
        return MicroexpressionResponse.model_validate(event)

    async def trigger_post_session_analysis(
        self, session_id: uuid.UUID
    ) -> AnalysisJobResponse:
        """Queue a Celery task for post-session video analysis.

        Creates or reuses a BiometricAnalysisJob record and enqueues the
        Celery task that will download the video from Cloudinary and process it.

        Args:
            session_id: UUID of the completed session to analyze.

        Returns:
            AnalysisJobResponse: The queued job record.

        Raises:
            NotFoundError: If the session does not exist.
            BadRequestError: If the session has no video URL.
        """
        from app.modules.biometric.tasks import analyze_session_video

        session = await self._session_repo.get_by_id(session_id)
        if not session:
            raise NotFoundError("Session")
        if not session.video_url:
            raise BadRequestError("Session has no video URL to analyze.")

        job = await self._job_repo.get_by_session(session_id)
        if not job:
            job = await self._job_repo.create(session_id)

        celery_task = analyze_session_video.delay(
            str(session_id), session.video_url
        )
        job = await self._job_repo.update_status(
            job,
            status=AnalysisJobStatus.PENDING,
            celery_task_id=celery_task.id,
        )
        await self._db.refresh(job)
        return AnalysisJobResponse.model_validate(job)

    async def get_analysis_job(self, session_id: uuid.UUID) -> AnalysisJobResponse:
        """Retrieve the analysis job status for a session.

        Args:
            session_id: UUID of the session.

        Returns:
            AnalysisJobResponse: The current job status.

        Raises:
            NotFoundError: If no job exists for this session.
        """
        job = await self._job_repo.get_by_session(session_id)
        if not job:
            raise NotFoundError("BiometricAnalysisJob")
        return AnalysisJobResponse.model_validate(job)

    async def get_patient_evolution(self, patient_id: uuid.UUID) -> ComparativeReport:
        """Return per-session averaged emotion data for all analysed completed sessions.

        Sessions with no biometric snapshots are excluded. Results are ordered
        chronologically (oldest first) so the frontend can render a time-series.

        Args:
            patient_id: UUID of the patient.

        Returns:
            ComparativeReport: One SessionComparePoint per analysed session.
        """
        from app.modules.sessions.models import SessionStatus

        sessions, _ = await self._session_repo.list_paginated(
            page=1,
            page_size=1000,
            patient_id=patient_id,
            status=SessionStatus.COMPLETED,
        )
        # list_paginated returns DESC; reverse for chronological ASC
        sessions = list(reversed(sessions))

        points = []
        for session in sessions:
            averages = await self._snapshot_repo.get_session_averages(session.id)
            if averages["snapshot_count"] == 0:
                continue
            points.append(
                SessionComparePoint(
                    session_id=session.id,
                    scheduled_at=session.scheduled_at,
                    avg_happiness=averages["avg_happiness"],
                    avg_sadness=averages["avg_sadness"],
                    avg_anger=averages["avg_anger"],
                    avg_fear=averages["avg_fear"],
                    avg_disgust=averages["avg_disgust"],
                    avg_surprise=averages["avg_surprise"],
                    avg_neutral=averages["avg_neutral"],
                    dominant_overall=averages["dominant_overall"],
                    snapshot_count=averages["snapshot_count"],
                )
            )
        return ComparativeReport(patient_id=patient_id, sessions=points)

    async def get_comparative_report(
        self, patient_id: uuid.UUID, session_ids: list[uuid.UUID]
    ) -> ComparativeReport:
        """Build a comparative emotional report across multiple sessions.

        Args:
            patient_id: UUID of the patient.
            session_ids: List of session UUIDs to include in the comparison.

        Returns:
            ComparativeReport: Per-session averaged emotion data.
        """
        points = []
        for sid in session_ids:
            session = await self._session_repo.get_by_id(sid)
            if not session:
                continue
            averages = await self._snapshot_repo.get_session_averages(sid)
            points.append(
                SessionComparePoint(
                    session_id=sid,
                    scheduled_at=session.scheduled_at,
                    avg_happiness=averages["avg_happiness"],
                    avg_sadness=averages["avg_sadness"],
                    avg_anger=averages["avg_anger"],
                    avg_fear=averages["avg_fear"],
                    avg_disgust=averages["avg_disgust"],
                    avg_surprise=averages["avg_surprise"],
                    avg_neutral=averages["avg_neutral"],
                    dominant_overall=averages["dominant_overall"],
                    snapshot_count=averages["snapshot_count"],
                )
            )
        return ComparativeReport(patient_id=patient_id, sessions=points)

    async def trigger_media_deletion(self, session_id: uuid.UUID) -> dict:
        """Queue a Celery task to cascade delete all media for a session.

        Args:
            session_id: UUID of the session.

        Returns:
            dict: Status message.
            
        Raises:
            NotFoundError: If the session does not exist.
        """
        from app.modules.biometric.tasks import delete_session_media_background
        
        session = await self._session_repo.get_by_id(session_id)
        if not session:
            raise NotFoundError("Session")
            
        delete_session_media_background.delay(str(session_id))
        return {"message": "Media deletion queued in background."}

    async def _check_and_create_alerts(
        self, session: Session, snapshot: SnapshotCreate
    ) -> None:
        """Evaluate alert thresholds and create alerts when crossed.

        Args:
            session: The active Session ORM instance.
            snapshot: The emotional snapshot data to evaluate.
        """
        anxiety_score = snapshot.fear + snapshot.sadness
        stress_score = snapshot.anger + snapshot.fear

        if anxiety_score >= ANXIETY_THRESHOLD:
            await self._alert_repo.create(
                session_id=session.id,
                patient_id=session.patient_id,
                alert_type=AlertType.HIGH_ANXIETY,
                severity=AlertSeverity.HIGH if anxiety_score >= 1.2 else AlertSeverity.MEDIUM,
                message=(
                    f"High anxiety detected at t={snapshot.timestamp_offset:.1f}s. "
                    f"Fear={snapshot.fear:.2f}, Sadness={snapshot.sadness:.2f}."
                ),
            )

        if stress_score >= STRESS_THRESHOLD:
            await self._alert_repo.create(
                session_id=session.id,
                patient_id=session.patient_id,
                alert_type=AlertType.HIGH_STRESS,
                severity=AlertSeverity.HIGH if stress_score >= 1.1 else AlertSeverity.MEDIUM,
                message=(
                    f"High stress detected at t={snapshot.timestamp_offset:.1f}s. "
                    f"Anger={snapshot.anger:.2f}, Fear={snapshot.fear:.2f}."
                ),
            )

        if snapshot.confidence >= CRITICAL_EMOTION_THRESHOLD:
            await self._alert_repo.create(
                session_id=session.id,
                patient_id=session.patient_id,
                alert_type=AlertType.CRITICAL_EMOTION,
                severity=AlertSeverity.CRITICAL,
                message=(
                    f"Critical emotion '{snapshot.dominant_emotion}' detected "
                    f"at confidence {snapshot.confidence:.2f}."
                ),
            )
