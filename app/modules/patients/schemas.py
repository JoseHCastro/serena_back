"""Pydantic schemas for the Patients module."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field

from app.modules.users.schemas import UserSummary


class PatientBase(BaseModel):
    """Shared fields for patient creation and updates."""

    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    birth_date: date | None = None
    gender: str | None = Field(None, max_length=50)
    phone: str | None = Field(None, max_length=30)
    email: EmailStr | None = None
    address: str | None = None
    emergency_contact_name: str | None = Field(None, max_length=200)
    emergency_contact_phone: str | None = Field(None, max_length=30)
    medical_notes: str | None = None


class PatientCreate(PatientBase):
    """Payload for registering a new patient.

    The therapist_id is automatically set to the authenticated user
    unless the caller has admin privileges.
    """

    therapist_id: uuid.UUID | None = None


class PatientUpdate(BaseModel):
    """Partial update payload (all fields optional)."""

    first_name: str | None = Field(None, min_length=1, max_length=100)
    last_name: str | None = Field(None, min_length=1, max_length=100)
    birth_date: date | None = None
    gender: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    address: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None
    medical_notes: str | None = None
    is_active: bool | None = None
    therapist_id: uuid.UUID | None = None


class PatientResponse(PatientBase):
    """Full patient record returned by the API."""

    id: uuid.UUID
    code: str
    is_active: bool
    therapist_id: uuid.UUID
    therapist: UserSummary
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PatientSummary(BaseModel):
    """Compact patient representation for embedded use."""

    id: uuid.UUID
    code: str
    full_name: str
    is_active: bool

    model_config = {"from_attributes": True}


class PaginatedPatients(BaseModel):
    """Paginated list of patients."""

    total: int
    page: int
    page_size: int
    items: list[PatientResponse]
