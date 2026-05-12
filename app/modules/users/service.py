"""Users service — user and role management business logic."""

import uuid
from app.modules.patients.repository import PatientRepository
from app.modules.sessions.repository import SessionRepository

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.security import hash_password
from app.modules.users.repository import RoleRepository, UserRepository
from app.modules.users.schemas import (
    PaginatedUsers,
    UserCreate,
    UserResponse,
    UserUpdate,
)


class UserService:
    """Business logic for user lifecycle management.

    Args:
        db: The active AsyncSession injected via FastAPI dependency.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._user_repo = UserRepository(db)
        self._role_repo = RoleRepository(db)
        self._patient_repo = PatientRepository(db)
        self._session_repo = SessionRepository(db)

    async def create_user(self, payload: UserCreate) -> UserResponse:
        """Register a new user after validating uniqueness and role existence.

        Args:
            payload: Validated UserCreate schema with email, password, role.

        Returns:
            UserResponse: The newly created user.

        Raises:
            ConflictError: If the email is already registered.
            NotFoundError: If the specified role does not exist.
        """
        existing = await self._user_repo.get_by_email(payload.email)
        if existing:
            raise ConflictError(f"Email '{payload.email}' is already registered.")

        role = await self._role_repo.get_by_id(payload.role_id)
        if not role:
            raise NotFoundError("Role")

        user = await self._user_repo.create(
            email=payload.email,
            hashed_password=hash_password(payload.password),
            full_name=payload.full_name,
            role_id=payload.role_id,
        )
        return UserResponse.model_validate(user)

    async def get_user(self, user_id: uuid.UUID) -> UserResponse:
        """Retrieve a user by ID.

        Args:
            user_id: UUID of the user to retrieve.

        Returns:
            UserResponse: The user data.

        Raises:
            NotFoundError: If the user does not exist.
        """
        user = await self._user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundError("User")
        return UserResponse.model_validate(user)

    async def list_users(
        self, page: int, page_size: int, role_name: str | None = None
    ) -> PaginatedUsers:
        """Return a paginated list of users.

        Args:
            page: 1-indexed page number.
            page_size: Records per page.
            role_name: Optional role filter.

        Returns:
            PaginatedUsers: Paginated result with metadata.
        """
        users, total = await self._user_repo.list_paginated(page, page_size, role_name)
        return PaginatedUsers(
            total=total,
            page=page,
            page_size=page_size,
            items=[UserResponse.model_validate(u) for u in users],
        )

    async def list_therapists(self) -> list[UserResponse]:
        """Return all active therapists in the system."""
        users, _ = await self._user_repo.list_paginated(page=1, page_size=1000, role_name="therapist")
        return [UserResponse.model_validate(u) for u in users]

    async def update_user(self, user_id: uuid.UUID, payload: UserUpdate) -> UserResponse:
        """Apply a partial update to a user.

        Args:
            user_id: UUID of the user to update.
            payload: Partial UserUpdate schema.

        Returns:
            UserResponse: The updated user.

        Raises:
            NotFoundError: If the user does not exist.
        """
        user = await self._user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundError("User")
        updated = await self._user_repo.update(
            user, **payload.model_dump(exclude_none=True)
        )
        return UserResponse.model_validate(updated)

    async def delete_user(self, user_id: uuid.UUID) -> None:
        """Soft-delete a user by ID.

        Args:
            user_id: UUID of the user to delete.

        Raises:
            NotFoundError: If the user does not exist.
        """
        user = await self._user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundError("User")
            
        # 1. Cleanup all associated media for all patients of this therapist
        from app.modules.biometric.tasks import delete_session_media_background
        
        # List all patients for this therapist
        patients, _ = await self._patient_repo.list_paginated(page=1, page_size=1000, therapist_id=user_id)
        for patient in patients:
            sessions = await self._session_repo.list_by_patient(patient.id)
            for session in sessions:
                delete_session_media_background.delay(str(session.id))
            # Also soft delete the patient
            await self._patient_repo.soft_delete(patient)

        # 2. Soft-delete the user
        await self._user_repo.soft_delete(user)
