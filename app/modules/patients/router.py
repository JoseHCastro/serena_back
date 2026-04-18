"""Patients router — clinical record CRUD endpoints."""

import uuid

from fastapi import APIRouter, Query

from app.core.dependencies import CurrentUser, DbSession
from app.modules.patients.schemas import PaginatedPatients, PatientCreate, PatientResponse, PatientUpdate
from app.modules.patients.service import PatientService

router = APIRouter(prefix="/patients", tags=["Patients"])


@router.post("/", response_model=PatientResponse, status_code=201, summary="Register new patient")
async def create_patient(
    payload: PatientCreate, db: DbSession, current_user: CurrentUser
) -> PatientResponse:
    """Register a new patient clinical record.

    If therapist_id is omitted, the authenticated user is assigned as therapist.

    Args:
        payload: Patient creation data.
        db: Database session.
        current_user: The authenticated user creating the record.

    Returns:
        PatientResponse: The newly created patient record with auto-generated code.
    """
    return await PatientService(db).create_patient(payload, current_user)


@router.get("/", response_model=PaginatedPatients, summary="List patients")
async def list_patients(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    therapist_id: uuid.UUID | None = Query(None),
    search: str | None = Query(None, description="Search by name, code, or email"),
    active_only: bool = Query(True),
) -> PaginatedPatients:
    """Return a paginated, searchable list of patients.

    Therapists only see their own patients. Admins can filter by any therapist.

    Args:
        db: Database session.
        current_user: The authenticated user.
        page: Page number.
        page_size: Records per page.
        therapist_id: Filter by therapist (admin only).
        search: Full-text search across name, code, and email.
        active_only: Exclude inactive patients when True.

    Returns:
        PaginatedPatients: Paginated result.
    """
    return await PatientService(db).list_patients(
        page, page_size, therapist_id, search, active_only, current_user
    )


@router.get("/{patient_id}", response_model=PatientResponse, summary="Get patient by ID")
async def get_patient(
    patient_id: uuid.UUID, db: DbSession, _: CurrentUser
) -> PatientResponse:
    """Retrieve a patient's full clinical record.

    Args:
        patient_id: UUID of the patient.
        db: Database session.

    Returns:
        PatientResponse: The full patient record.
    """
    return await PatientService(db).get_patient(patient_id)


@router.patch("/{patient_id}", response_model=PatientResponse, summary="Update patient record")
async def update_patient(
    patient_id: uuid.UUID, payload: PatientUpdate, db: DbSession, _: CurrentUser
) -> PatientResponse:
    """Apply a partial update to a patient's clinical record.

    Args:
        patient_id: UUID of the patient to update.
        payload: Partial update data.
        db: Database session.

    Returns:
        PatientResponse: The updated patient record.
    """
    return await PatientService(db).update_patient(patient_id, payload)


@router.delete("/{patient_id}", status_code=204, summary="Soft-delete patient")
async def delete_patient(
    patient_id: uuid.UUID, db: DbSession, _: CurrentUser
) -> None:
    """Soft-delete a patient record (sets deleted_at, marks inactive).

    Medical records are never physically deleted to preserve clinical history.

    Args:
        patient_id: UUID of the patient to soft-delete.
        db: Database session.
    """
    await PatientService(db).delete_patient(patient_id)
