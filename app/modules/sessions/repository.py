"""Sessions repository — data access layer."""

import uuid

from sqlalchemy import func, select, or_
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.sessions.models import Session, SessionStatus
from app.modules.patients.models import Patient


class SessionRepository:
    """Data access object for Session entities.

    Args:
        db: The active AsyncSession injected via FastAPI dependency.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_id(self, session_id: uuid.UUID) -> Session | None:
        """Fetch a session by primary key.

        Args:
            session_id: UUID of the session to retrieve.

        Returns:
            Session | None: The Session instance, or None if not found.
        """
        result = await self._db.execute(
            select(Session)
            .options(joinedload(Session.patient), joinedload(Session.therapist))
            .where(Session.id == session_id)
        )
        return result.scalar_one_or_none()

    async def list_paginated(
        self,
        page: int = 1,
        page_size: int = 20,
        patient_id: uuid.UUID | None = None,
        therapist_id: uuid.UUID | None = None,
        status: SessionStatus | None = None,
        search: str | None = None,
    ) -> tuple[list[Session], int]:
        """Return a paginated, filterable session list ordered by scheduled date.

        Args:
            page: 1-indexed page number.
            page_size: Records per page.
            patient_id: Filter by patient.
            therapist_id: Filter by therapist.
            status: Filter by session lifecycle status.
            search: Filter by text in notes or patient name.

        Returns:
            tuple[list[Session], int]: Page of sessions and total count.
        """
        query = select(Session).join(Session.patient)
        if patient_id:
            query = query.where(Session.patient_id == patient_id)
        if therapist_id:
            query = query.where(Session.therapist_id == therapist_id)
        if status:
            query = query.where(Session.status == status)
        if search:
            search_pattern = f"%{search}%"
            query = query.where(
                or_(
                    Patient.first_name.ilike(search_pattern),
                    Patient.last_name.ilike(search_pattern),
                    Session.notes.ilike(search_pattern)
                )
            )
        query = query.order_by(Session.scheduled_at.desc())

        count_result = await self._db.execute(
            select(func.count()).select_from(query.subquery())
        )
        total = count_result.scalar_one()

        offset = (page - 1) * page_size
        result = await self._db.execute(query.offset(offset).limit(page_size))
        return list(result.scalars().all()), total

    async def create(self, **kwargs) -> Session:
        """Persist a new Session.

        Args:
            **kwargs: Field values matching Session model attributes.

        Returns:
            Session: The newly created and flushed Session instance.
        """
        session = Session(**kwargs)
        self._db.add(session)
        await self._db.flush()
        await self._db.refresh(session, ["patient", "therapist"])
        return session

    async def update(self, session: Session, **kwargs) -> Session:
        """Apply partial updates to a Session instance.

        Args:
            session: The Session ORM instance to update.
            **kwargs: Fields to update.

        Returns:
            Session: The updated and flushed Session instance.
        """
        for field, value in kwargs.items():
            setattr(session, field, value)
        await self._db.flush()
        await self._db.refresh(session, ["patient", "therapist"])
        return session
