"""Pydantic schemas for the Users and Roles module."""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


# ---------------------------------------------------------------------------
# Role schemas
# ---------------------------------------------------------------------------


class RoleBase(BaseModel):
    """Shared fields for Role creation and response."""

    name: str = Field(..., min_length=2, max_length=50, examples=["therapist"])
    description: str | None = Field(None, max_length=255)


class RoleCreate(RoleBase):
    """Payload for creating a new role."""


class RoleResponse(RoleBase):
    """Role representation returned by the API."""

    id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# User schemas
# ---------------------------------------------------------------------------


class UserBase(BaseModel):
    """Shared fields for User creation and update."""

    email: EmailStr
    full_name: str = Field(..., min_length=2, max_length=255)
    role_id: uuid.UUID


class UserCreate(UserBase):
    """Payload for registering a new user (includes plain-text password)."""

    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        """Validate that the password contains at least one digit.

        Args:
            v: The raw password string.

        Returns:
            str: The validated password.

        Raises:
            ValueError: If the password contains no digits.
        """
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit.")
        return v


class UserUpdate(BaseModel):
    """Partial update payload for a user (all fields optional)."""

    full_name: str | None = Field(None, min_length=2, max_length=255)
    role_id: uuid.UUID | None = None
    is_active: bool | None = None
    password: str | None = Field(None, min_length=8, max_length=128)


class UserResponse(UserBase):
    """User representation returned by the API (no password field)."""

    id: uuid.UUID
    is_active: bool
    last_login: datetime | None
    created_at: datetime
    updated_at: datetime
    role: RoleResponse

    model_config = {"from_attributes": True}


class UserSummary(BaseModel):
    """Compact user representation for embedded use in other responses."""

    id: uuid.UUID
    full_name: str
    email: EmailStr

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Pagination wrapper
# ---------------------------------------------------------------------------


class PaginatedUsers(BaseModel):
    """Paginated list of users."""

    total: int
    page: int
    page_size: int
    items: list[UserResponse]
