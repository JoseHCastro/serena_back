"""Patients service — clinical record management business logic."""

import uuid
from app.modules.sessions.repository import SessionRepository

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.modules.patients.repository import PatientRepository
from app.modules.patients.schemas import (
    PaginatedPatients,
    PatientCreate,
    PatientResponse,
    PatientUpdate,
)
from app.modules.users.models import User
from app.modules.users.repository import UserRepository


class PatientService:
    """Business logic for patient (expediente clínico) management.

    Args:
        db: The active AsyncSession injected via FastAPI dependency.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._repo = PatientRepository(db)
        self._user_repo = UserRepository(db)
        self._session_repo = SessionRepository(db)

    async def create_patient(
        self, payload: PatientCreate, current_user: User
    ) -> PatientResponse:
        """Register a new patient and assign a sequential clinical code.

        If the payload does not specify a therapist_id (and the caller is not
        an admin), the current authenticated user is assigned as the therapist.

        Args:
            payload: Validated PatientCreate schema.
            current_user: The authenticated user creating the record.

        Returns:
            PatientResponse: The newly created patient record.

        Raises:
            NotFoundError: If a specified therapist_id does not exist.
        """
        therapist_id = payload.therapist_id or current_user.id

        if payload.therapist_id and payload.therapist_id != current_user.id:
            therapist = await self._user_repo.get_by_id(payload.therapist_id)
            if not therapist:
                raise NotFoundError("Therapist")
            therapist_id = therapist.id

        code = await self._repo.generate_next_code()
        data = payload.model_dump(exclude={"therapist_id"})
        patient = await self._repo.create(code=code, therapist_id=therapist_id, **data)
        return PatientResponse.model_validate(patient)

    async def get_patient(self, patient_id: uuid.UUID) -> PatientResponse:
        """Retrieve a patient by ID.

        Args:
            patient_id: UUID of the patient to retrieve.

        Returns:
            PatientResponse: The patient record.

        Raises:
            NotFoundError: If the patient does not exist or is soft-deleted.
        """
        patient = await self._repo.get_by_id(patient_id)
        if not patient:
            raise NotFoundError("Patient")
        return PatientResponse.model_validate(patient)

    async def list_patients(
        self,
        page: int,
        page_size: int,
        therapist_id: uuid.UUID | None,
        search: str | None,
        active_only: bool,
        current_user: User,
    ) -> PaginatedPatients:
        """Return a paginated list of patients.

        Therapists see only their own patients unless they are admins.

        Args:
            page: 1-indexed page number.
            page_size: Records per page.
            therapist_id: Optional therapist filter (admins can filter by any).
            search: Full-text search string.
            active_only: If True, exclude inactive patients.
            current_user: The authenticated user.

        Returns:
            PaginatedPatients: Paginated result with metadata.
        """
        effective_therapist_id = therapist_id
        if current_user.role.name == "therapist":
            effective_therapist_id = current_user.id

        patients, total = await self._repo.list_paginated(
            page=page,
            page_size=page_size,
            therapist_id=effective_therapist_id,
            search=search,
            active_only=active_only,
        )
        return PaginatedPatients(
            total=total,
            page=page,
            page_size=page_size,
            items=[PatientResponse.model_validate(p) for p in patients],
        )

    async def update_patient(
        self, patient_id: uuid.UUID, payload: PatientUpdate
    ) -> PatientResponse:
        """Apply a partial update to a patient record.

        Args:
            patient_id: UUID of the patient to update.
            payload: Partial PatientUpdate schema.

        Returns:
            PatientResponse: The updated patient record.

        Raises:
            NotFoundError: If the patient does not exist.
        """
        patient = await self._repo.get_by_id(patient_id)
        if not patient:
            raise NotFoundError("Patient")
        updated = await self._repo.update(patient, **payload.model_dump(exclude_none=True))
        return PatientResponse.model_validate(updated)

    async def delete_patient(self, patient_id: uuid.UUID) -> None:
        """Soft-delete a patient record.

        Args:
            patient_id: UUID of the patient to delete.

        Raises:
            NotFoundError: If the patient does not exist.
        """
        patient = await self._repo.get_by_id(patient_id)
        if not patient:
            raise NotFoundError("Patient")
            
        # 1. Cleanup all associated sessions' media in Cloudinary
        from app.modules.biometric.tasks import delete_session_media_background
        sessions = await self._session_repo.list_by_patient(patient_id)
        for session in sessions:
            delete_session_media_background.delay(str(session.id))
            
        # 2. Soft-delete the patient record
        await self._repo.soft_delete(patient)
