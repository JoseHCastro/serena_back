"""Sessions service — therapy session lifecycle business logic."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, NotFoundError
from app.modules.patients.repository import PatientRepository
from app.modules.sessions.models import SessionStatus
from app.modules.sessions.repository import SessionRepository
from app.modules.sessions.schemas import (
    EmotionalTimeline,
    EmotionalTimelinePoint,
    PaginatedSessions,
    SessionCreate,
    SessionResponse,
    SessionUpdate,
)
from app.modules.users.models import User


class SessionService:
    """Business logic for therapy session lifecycle management.

    Args:
        db: The active AsyncSession injected via FastAPI dependency.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._repo = SessionRepository(db)
        self._patient_repo = PatientRepository(db)

    async def schedule_session(
        self, payload: SessionCreate, current_user: User
    ) -> SessionResponse:
        """Schedule a new therapy session for a patient.

        Args:
            payload: Validated SessionCreate schema.
            current_user: The authenticated user scheduling the session.

        Returns:
            SessionResponse: The newly created session.

        Raises:
            NotFoundError: If the patient or specified therapist does not exist.
            BadRequestError: If a non-therapist omits therapist_id.
        """
        from app.modules.users.repository import UserRepository

        patient = await self._patient_repo.get_by_id(payload.patient_id)
        if not patient:
            raise NotFoundError("Patient")

        if payload.therapist_id:
            user_repo = UserRepository(self._db)
            therapist = await user_repo.get_by_id(payload.therapist_id)
            if not therapist:
                raise NotFoundError("Therapist")
            therapist_id = payload.therapist_id
        elif current_user.role.name in ("admin", "receptionist"):
            raise BadRequestError("Se debe especificar el terapeuta para la sesión.")
        else:
            therapist_id = current_user.id

        session = await self._repo.create(
            patient_id=payload.patient_id,
            therapist_id=therapist_id,
            scheduled_at=payload.scheduled_at,
            notes=payload.notes,
            status=SessionStatus.SCHEDULED,
        )
        return SessionResponse.model_validate(session)

    async def start_session(self, session_id: uuid.UUID) -> SessionResponse:
        """Mark a session as active and record the start timestamp.

        Args:
            session_id: UUID of the session to start.

        Returns:
            SessionResponse: The updated session.

        Raises:
            NotFoundError: If the session does not exist.
            BadRequestError: If the session is not in SCHEDULED state.
        """
        session = await self._repo.get_by_id(session_id)
        if not session:
            raise NotFoundError("Session")
        if session.status != SessionStatus.SCHEDULED:
            raise BadRequestError(
                f"Cannot start a session with status '{session.status.value}'."
            )
        updated = await self._repo.update(
            session,
            status=SessionStatus.ACTIVE,
            started_at=datetime.now(UTC),
        )
        # Ensure all fields are refreshed for Pydantic
        await self._db.refresh(updated)
        return SessionResponse.model_validate(updated)

    async def end_session(
        self, session_id: uuid.UUID, notes: str | None = None
    ) -> SessionResponse:
        """Mark a session as completed and record the end timestamp.

        Args:
            session_id: UUID of the session to end.
            notes: Optional final session notes.

        Returns:
            SessionResponse: The completed session.

        Raises:
            NotFoundError: If the session does not exist.
            BadRequestError: If the session is not currently active.
        """
        session = await self._repo.get_by_id(session_id)
        if not session:
            raise NotFoundError("Session")
        if session.status != SessionStatus.ACTIVE:
            raise BadRequestError("Only active sessions can be ended.")

        update_kwargs: dict = {"status": SessionStatus.COMPLETED, "ended_at": datetime.now(UTC)}
        if notes is not None:
            update_kwargs["notes"] = notes

        updated = await self._repo.update(session, **update_kwargs)
        # Ensure all fields are refreshed for Pydantic
        await self._db.refresh(updated)
        return SessionResponse.model_validate(updated)

    async def get_session(self, session_id: uuid.UUID) -> SessionResponse:
        """Retrieve a session by ID.

        Args:
            session_id: UUID of the session.

        Returns:
            SessionResponse: The session data.

        Raises:
            NotFoundError: If the session does not exist.
        """
        session = await self._repo.get_by_id(session_id)
        if not session:
            raise NotFoundError("Session")
        return SessionResponse.model_validate(session)

    async def list_sessions(
        self,
        page: int,
        page_size: int,
        patient_id: uuid.UUID | None,
        status: SessionStatus | None,
        current_user: User,
        search: str | None = None,
    ) -> PaginatedSessions:
        """Return a paginated list of sessions, scoped by role.

        Args:
            page: 1-indexed page number.
            page_size: Records per page.
            patient_id: Optional patient filter.
            status: Optional status filter.
            current_user: The authenticated user.
            search: Optional search text.

        Returns:
            PaginatedSessions: Paginated result with metadata.
        """
        therapist_id = (
            current_user.id if current_user.role.name == "therapist" else None
        )
        sessions, total = await self._repo.list_paginated(
            page=page,
            page_size=page_size,
            patient_id=patient_id,
            therapist_id=therapist_id,
            status=status,
            search=search,
        )
        return PaginatedSessions(
            total=total,
            page=page,
            page_size=page_size,
            items=[SessionResponse.model_validate(s) for s in sessions],
        )

    async def get_emotional_timeline(self, session_id: uuid.UUID) -> EmotionalTimeline:
        """Build the emotional timeline data structure for dashboard visualization.

        Args:
            session_id: UUID of the session to build the timeline for.

        Returns:
            EmotionalTimeline: Timeline points ready for chart rendering.

        Raises:
            NotFoundError: If the session does not exist.
        """
        from app.modules.biometric.repository import EmotionalSnapshotRepository

        session = await self._repo.get_by_id(session_id)
        if not session:
            raise NotFoundError("Session")

        snapshot_repo = EmotionalSnapshotRepository(self._db)
        snapshots = await snapshot_repo.list_by_session(session_id)

        duration = None
        if snapshots:
            duration = max(s.timestamp_offset for s in snapshots)
        elif session.started_at and session.ended_at:
            duration = (session.ended_at - session.started_at).total_seconds()

        points = [
            EmotionalTimelinePoint(
                timestamp_offset=s.timestamp_offset,
                happiness=s.happiness,
                sadness=s.sadness,
                anger=s.anger,
                fear=s.fear,
                disgust=s.disgust,
                surprise=s.surprise,
                neutral=s.neutral,
                dominant_emotion=s.dominant_emotion,
                confidence=s.confidence,
                raw_data=s.raw_data,
            )
            for s in snapshots
        ]
        return EmotionalTimeline(
            session_id=session_id,
            total_snapshots=len(points),
            duration_seconds=duration,
            points=points,
        )

    async def delete_session(self, session_id: uuid.UUID) -> None:
        """Delete a session and trigger background media cleanup on Cloudinary.

        Args:
            session_id: UUID of the session to delete.

        Raises:
            NotFoundError: If the session does not exist.
        """
        session = await self._repo.get_by_id(session_id)
        if not session:
            raise NotFoundError("Session")

        # 1. Trigger background media cleanup (Celery)
        from app.modules.biometric.tasks import delete_session_media_background
        delete_session_media_background.delay(str(session_id))

        # 2. Delete session from DB
        await self._repo.delete(session)
