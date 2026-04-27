"""Patients repository — data access layer."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.patients.models import Patient


class PatientRepository:
    """Data access object for Patient (expediente clínico) entities.

    Args:
        db: The active AsyncSession injected via FastAPI dependency.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_id(self, patient_id: uuid.UUID) -> Patient | None:
        """Fetch an active (non-deleted) patient by primary key.

        Args:
            patient_id: UUID of the patient to retrieve.

        Returns:
            Patient | None: The Patient instance, or None if not found or deleted.
        """
        result = await self._db.execute(
            select(Patient)
            .options(joinedload(Patient.therapist))
            .where(
                Patient.id == patient_id, Patient.deleted_at.is_(None)
            )
        )
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> Patient | None:
        """Fetch a patient by their unique clinical code.

        Args:
            code: The clinical code (e.g., "PAC-0001").

        Returns:
            Patient | None: The Patient instance, or None.
        """
        result = await self._db.execute(
            select(Patient).where(Patient.code == code, Patient.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def list_paginated(
        self,
        page: int = 1,
        page_size: int = 20,
        therapist_id: uuid.UUID | None = None,
        search: str | None = None,
        active_only: bool = True,
    ) -> tuple[list[Patient], int]:
        """Return a paginated, filterable list of patients.

        Args:
            page: 1-indexed page number.
            page_size: Records per page.
            therapist_id: Filter by assigned therapist.
            search: Case-insensitive search across name, code, and email.
            active_only: If True, exclude inactive patients.

        Returns:
            tuple[list[Patient], int]: Page of patients and total count.
        """
        query = select(Patient).where(Patient.deleted_at.is_(None))

        if active_only:
            query = query.where(Patient.is_active.is_(True))
        if therapist_id:
            query = query.where(Patient.therapist_id == therapist_id)
        if search:
            term = f"%{search.lower()}%"
            query = query.where(
                or_(
                    func.lower(Patient.first_name).like(term),
                    func.lower(Patient.last_name).like(term),
                    func.lower(Patient.code).like(term),
                    func.lower(Patient.email).like(term),
                )
            )
        query = query.order_by(Patient.last_name, Patient.first_name)

        count_q = await self._db.execute(
            select(func.count()).select_from(query.subquery())
        )
        total = count_q.scalar_one()

        offset = (page - 1) * page_size
        result = await self._db.execute(query.offset(offset).limit(page_size))
        return list(result.scalars().all()), total

    async def generate_next_code(self) -> str:
        """Generate the next sequential patient clinical code (e.g., 'PAC-0042').

        Returns:
            str: The next available code in the PAC-XXXX format.
        """
        result = await self._db.execute(select(func.count()).select_from(Patient))
        count = result.scalar_one()
        return f"PAC-{(count + 1):04d}"

    async def create(self, **kwargs) -> Patient:
        """Persist a new Patient.

        Args:
            **kwargs: Field values matching Patient model attributes.

        Returns:
            Patient: The newly created and flushed Patient instance.
        """
        patient = Patient(**kwargs)
        self._db.add(patient)
        await self._db.flush()
        await self._db.refresh(patient, ["therapist"])
        return patient

    async def update(self, patient: Patient, **kwargs) -> Patient:
        """Apply partial updates to a Patient instance.

        Args:
            patient: The Patient ORM instance to update.
            **kwargs: Fields to update.

        Returns:
            Patient: The updated and flushed Patient instance.
        """
        for field, value in kwargs.items():
            if value is not None or field == "medical_notes":
                setattr(patient, field, value)
        await self._db.flush()
        # Explicitly refresh attributes that might be updated by DB or relations
        await self._db.refresh(patient, ["therapist", "updated_at"])
        return patient

    async def soft_delete(self, patient: Patient) -> Patient:
        """Soft-delete a patient by setting deleted_at and deactivating.

        Args:
            patient: The Patient ORM instance to soft-delete.

        Returns:
            Patient: The updated instance.
        """
        patient.deleted_at = datetime.now(UTC)
        patient.is_active = False
        await self._db.flush()
        return patient
