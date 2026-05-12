"""Biometric router — real-time WebSocket streaming + REST endpoints."""

import json
import uuid

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from loguru import logger

from app.core.dependencies import CurrentUser, DbSession
from app.modules.biometric.schemas import (
    AnalysisJobResponse,
    ComparativeReport,
    FramePayload,
    MicroexpressionCreate,
    MicroexpressionResponse,
    SnapshotCreate,
    SnapshotResponse,
)
from app.modules.biometric.service import BiometricService

router = APIRouter(prefix="/biometric", tags=["Biometric Analysis"])


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@router.get(
    "/config",
    summary="Get biometric analysis configuration",
)
async def get_biometric_config(_: CurrentUser) -> dict:
    """Return biometric analysis settings like frame sampling interval.

    Returns:
        dict: Settings for the frontend to adjust capturing rates.
    """
    from app.core.config import settings

    return {"frame_sampling_interval": settings.FRAME_SAMPLING_INTERVAL}


# ---------------------------------------------------------------------------
# Real-time REST snapshot submission
# ---------------------------------------------------------------------------


@router.post(
    "/sessions/{session_id}/snapshots",
    response_model=SnapshotResponse,
    status_code=201,
    summary="Submit a real-time emotional snapshot",
)
async def save_snapshot(
    session_id: uuid.UUID,
    payload: SnapshotCreate,
    db: DbSession,
    _: CurrentUser,
) -> SnapshotResponse:
    """Persist a pre-analyzed emotional snapshot for a live session.

    Use this endpoint when the emotion analysis is done client-side or
    by an external service. Use the WebSocket endpoint for frame streaming.

    Args:
        session_id: UUID of the active session.
        payload: Emotion scores and dominant emotion data.
        db: Database session.

    Returns:
        SnapshotResponse: The persisted snapshot with ID and timestamp.
    """
    return await BiometricService(db).save_snapshot(session_id, payload)


@router.get(
    "/sessions/{session_id}/snapshots",
    response_model=list[SnapshotResponse],
    summary="List all snapshots for a session",
)
async def list_snapshots(
    session_id: uuid.UUID, db: DbSession, _: CurrentUser
) -> list[SnapshotResponse]:
    """Return all emotional snapshots for a session in chronological order.

    Args:
        session_id: UUID of the session.
        db: Database session.

    Returns:
        list[SnapshotResponse]: All snapshots ordered by timestamp_offset.
    """
    from app.modules.biometric.repository import EmotionalSnapshotRepository

    snapshots = await EmotionalSnapshotRepository(db).list_by_session(session_id)
    return [SnapshotResponse.model_validate(s) for s in snapshots]


@router.post(
    "/sessions/{session_id}/microexpressions",
    response_model=MicroexpressionResponse,
    status_code=201,
    summary="Log a microexpression event",
)
async def save_microexpression(
    session_id: uuid.UUID,
    payload: MicroexpressionCreate,
    db: DbSession,
    _: CurrentUser,
) -> MicroexpressionResponse:
    """Record a detected microexpression event during a live session.

    Args:
        session_id: UUID of the active session.
        payload: Microexpression event data.
        db: Database session.

    Returns:
        MicroexpressionResponse: The persisted microexpression event.
    """
    return await BiometricService(db).save_microexpression(session_id, payload)


# ---------------------------------------------------------------------------
# Post-session Celery analysis
# ---------------------------------------------------------------------------


@router.post(
    "/sessions/{session_id}/analyze",
    response_model=AnalysisJobResponse,
    status_code=202,
    summary="Queue post-session video analysis",
)
async def trigger_analysis(
    session_id: uuid.UUID, db: DbSession, _: CurrentUser
) -> AnalysisJobResponse:
    """Queue a Celery task to analyze the session video from Cloudinary.

    Returns immediately with a job record. Poll /analysis-job for status.

    Args:
        session_id: UUID of the completed session to analyze.
        db: Database session.

    Returns:
        AnalysisJobResponse: The queued analysis job with PENDING status.
    """
    return await BiometricService(db).trigger_post_session_analysis(session_id)


@router.get(
    "/sessions/{session_id}/analysis-job",
    response_model=AnalysisJobResponse,
    summary="Get analysis job status",
)
async def get_analysis_job(
    session_id: uuid.UUID, db: DbSession, _: CurrentUser
) -> AnalysisJobResponse:
    """Poll the status of the post-session analysis job.

    Args:
        session_id: UUID of the session whose job to check.
        db: Database session.

    Returns:
        AnalysisJobResponse: Current job status, celery_task_id, and results.
    """
    return await BiometricService(db).get_analysis_job(session_id)


@router.delete(
    "/sessions/{session_id}/media",
    status_code=202,
    summary="Cascade delete all session media",
)
async def delete_session_media(
    session_id: uuid.UUID, db: DbSession, _: CurrentUser
) -> dict:
    """Trigger an async task to delete all Cloudinary media for a session.
    
    This includes all frames from snapshots and the original video.

    Args:
        session_id: UUID of the session.
        db: Database session.

    Returns:
        dict: Acknowledgment message.
    """
    return await BiometricService(db).trigger_media_deletion(session_id)


# ---------------------------------------------------------------------------
# Comparative dashboard
# ---------------------------------------------------------------------------


@router.get(
    "/patients/{patient_id}/compare",
    response_model=ComparativeReport,
    summary="Comparative emotional report across sessions",
)
async def compare_sessions(
    patient_id: uuid.UUID,
    db: DbSession,
    _: CurrentUser,
    session_ids: list[uuid.UUID] = Query(..., description="UUIDs of sessions to compare"),
) -> ComparativeReport:
    """Return per-session emotional averages for the comparison dashboard module.

    Args:
        patient_id: UUID of the patient.
        db: Database session.
        session_ids: List of session UUIDs to include in the comparison.

    Returns:
        ComparativeReport: Average emotion data per session, ready for overlay chart.
    """
    return await BiometricService(db).get_comparative_report(patient_id, session_ids)


# ---------------------------------------------------------------------------
# WebSocket — real-time frame streaming
# ---------------------------------------------------------------------------


@router.websocket("/sessions/{session_id}/stream")
async def stream_emotional_analysis(
    websocket: WebSocket,
    session_id: uuid.UUID,
    db: DbSession,
) -> None:
    """WebSocket endpoint for real-time emotional frame analysis.

    Protocol:
        1. Client connects to ws://host/api/v1/biometric/sessions/{id}/stream
        2. Client sends JSON: {"frame_base64": "<base64>", "timestamp_offset": 12.5}
        3. Server analyzes the frame (mock or real AI model)
        4. Server replies with a SnapshotResponse JSON object
        5. If an alert threshold is crossed, server sends an additional alert message

    Args:
        websocket: The WebSocket connection.
        session_id: UUID of the active session being streamed.
        db: Database session.
    """
    await websocket.accept()
    service = BiometricService(db)
    logger.info("WebSocket connected | session={}", session_id)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
                frame_payload = FramePayload(**data)
            except (json.JSONDecodeError, ValueError) as e:
                await websocket.send_json({"error": f"Invalid payload: {e}"})
                continue

            snapshot = await service.analyze_frame(
                session_id=session_id,
                frame_base64=frame_payload.frame_base64,
                timestamp_offset=frame_payload.timestamp_offset,
            )
            await websocket.send_text(snapshot.model_dump_json())

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected | session={}", session_id)
