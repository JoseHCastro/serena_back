"""Sessions router — session lifecycle and dashboard endpoints."""

import uuid

from fastapi import APIRouter, Body, Query

from app.core.dependencies import CurrentUser, DbSession
from app.modules.sessions.models import SessionStatus
from app.modules.sessions.schemas import (
    EmotionalTimeline,
    PaginatedSessions,
    SessionCreate,
    SessionResponse,
    SessionUpdate,
)
from app.modules.sessions.service import SessionService

router = APIRouter(prefix="/sessions", tags=["Sessions"])


@router.post("/", response_model=SessionResponse, status_code=201, summary="Schedule a session")
async def schedule_session(
    payload: SessionCreate, db: DbSession, current_user: CurrentUser
) -> SessionResponse:
    """Schedule a new therapy session for a patient.

    Args:
        payload: Session scheduling data (patient_id, scheduled_at, notes).
        db: Database session.
        current_user: The authenticated therapist.

    Returns:
        SessionResponse: The newly scheduled session.
    """
    return await SessionService(db).schedule_session(payload, current_user)


@router.get("/", response_model=PaginatedSessions, summary="List sessions")
async def list_sessions(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    patient_id: uuid.UUID | None = Query(None),
    status: SessionStatus | None = Query(None),
) -> PaginatedSessions:
    """Return a paginated list of sessions, scoped by the caller's role.

    Args:
        db: Database session.
        current_user: Authenticated user (therapists see only their sessions).
        page: Page number.
        page_size: Records per page.
        patient_id: Optional patient filter.
        status: Optional status filter.

    Returns:
        PaginatedSessions: Paginated result.
    """
    return await SessionService(db).list_sessions(
        page, page_size, patient_id, status, current_user
    )


@router.get("/{session_id}", response_model=SessionResponse, summary="Get session by ID")
async def get_session(
    session_id: uuid.UUID, db: DbSession, _: CurrentUser
) -> SessionResponse:
    """Retrieve a specific session by UUID.

    Args:
        session_id: UUID of the session to retrieve.
        db: Database session.

    Returns:
        SessionResponse: The session data.
    """
    return await SessionService(db).get_session(session_id)


@router.post("/{session_id}/start", response_model=SessionResponse, summary="Start a session")
async def start_session(
    session_id: uuid.UUID, db: DbSession, _: CurrentUser
) -> SessionResponse:
    """Mark a scheduled session as active and record the start timestamp.

    Args:
        session_id: UUID of the session to start.
        db: Database session.

    Returns:
        SessionResponse: The updated session with ACTIVE status.
    """
    return await SessionService(db).start_session(session_id)


@router.post("/{session_id}/end", response_model=SessionResponse, summary="End a session")
async def end_session(
    session_id: uuid.UUID,
    db: DbSession,
    _: CurrentUser,
    notes: str | None = Body(None, embed=True),
) -> SessionResponse:
    """Mark an active session as completed and record the end timestamp.

    Args:
        session_id: UUID of the session to end.
        db: Database session.
        notes: Optional final therapist notes.

    Returns:
        SessionResponse: The updated session with COMPLETED status.
    """
    return await SessionService(db).end_session(session_id, notes)


@router.patch("/{session_id}", response_model=SessionResponse, summary="Update session notes")
async def update_session(
    session_id: uuid.UUID, payload: SessionUpdate, db: DbSession, _: CurrentUser
) -> SessionResponse:
    """Update session scheduling or notes.

    Args:
        session_id: UUID of the session to update.
        payload: Partial update data.
        db: Database session.

    Returns:
        SessionResponse: The updated session.
    """
    from app.modules.sessions.repository import SessionRepository

    repo = SessionRepository(db)
    session = await repo.get_by_id(session_id)
    if not session:
        from app.core.exceptions import NotFoundError
        raise NotFoundError("Session")
    updated = await repo.update(session, **payload.model_dump(exclude_none=True))
    return SessionResponse.model_validate(updated)


@router.get(
    "/{session_id}/timeline",
    response_model=EmotionalTimeline,
    summary="Emotional timeline for dashboard",
)
async def get_emotional_timeline(
    session_id: uuid.UUID, db: DbSession, _: CurrentUser
) -> EmotionalTimeline:
    """Return the minute-by-minute emotional timeline for dashboard rendering.

    Args:
        session_id: UUID of the session.
        db: Database session.

    Returns:
        EmotionalTimeline: All emotional snapshots ordered chronologically.
    """
    return await SessionService(db).get_emotional_timeline(session_id)
