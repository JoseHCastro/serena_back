"""Users router — user and role CRUD endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import CurrentUser, DbSession, require_roles
from app.modules.users.schemas import PaginatedUsers, RoleResponse, UserCreate, UserResponse, UserUpdate
from app.modules.users.service import UserService

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/roles", response_model=list[RoleResponse], summary="List all roles (authenticated)")
async def list_roles(db: DbSession, _: CurrentUser) -> list[RoleResponse]:
    """Return all available roles. Accessible by any authenticated user."""
    from app.modules.users.repository import RoleRepository
    roles = await RoleRepository(db).list_all()
    return [RoleResponse.model_validate(r) for r in roles]


@router.get("/therapists", response_model=list[UserResponse], summary="List all therapists")
async def list_therapists(db: DbSession, _: CurrentUser) -> list[UserResponse]:
    """Return a list of all active users with the 'therapist' role.

    Accessible by any authenticated user.
    """
    return await UserService(db).list_therapists()


@router.get("/me", response_model=UserResponse, summary="Get current user profile")
async def get_me(current_user: CurrentUser) -> UserResponse:
    """Return the authenticated user's own profile.

    Args:
        current_user: The authenticated user from JWT dependency.

    Returns:
        UserResponse: The current user's data.
    """
    return UserResponse.model_validate(current_user)


@router.get(
    "/",
    response_model=PaginatedUsers,
    summary="List users (admin only)",
    dependencies=[Depends(require_roles("admin"))],
)
async def list_users(
    db: DbSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    role_name: str | None = Query(None),
) -> PaginatedUsers:
    """Return a paginated list of all system users.

    Args:
        db: Database session.
        page: Page number (1-indexed).
        page_size: Number of records per page.
        role_name: Optional role filter.

    Returns:
        PaginatedUsers: Paginated user list with metadata.
    """
    return await UserService(db).list_users(page, page_size, role_name)


@router.post(
    "/",
    response_model=UserResponse,
    status_code=201,
    summary="Create a new user (admin only)",
    dependencies=[Depends(require_roles("admin"))],
)
async def create_user(payload: UserCreate, db: DbSession) -> UserResponse:
    """Register a new system user.

    Args:
        payload: User creation data (email, password, full_name, role_id).
        db: Database session.

    Returns:
        UserResponse: The created user.
    """
    return await UserService(db).create_user(payload)


@router.get("/{user_id}", response_model=UserResponse, summary="Get user by ID")
async def get_user(
    user_id: uuid.UUID,
    db: DbSession,
    _: Annotated[None, Depends(require_roles("admin"))],
) -> UserResponse:
    """Retrieve a specific user by their UUID.

    Args:
        user_id: UUID of the user to retrieve.
        db: Database session.

    Returns:
        UserResponse: The user data.
    """
    return await UserService(db).get_user(user_id)


@router.patch(
    "/{user_id}",
    response_model=UserResponse,
    summary="Update a user (admin only)",
    dependencies=[Depends(require_roles("admin"))],
)
async def update_user(
    user_id: uuid.UUID, payload: UserUpdate, db: DbSession
) -> UserResponse:
    """Apply a partial update to a user.

    Args:
        user_id: UUID of the user to update.
        payload: Partial update data.
        db: Database session.

    Returns:
        UserResponse: The updated user.
    """
    return await UserService(db).update_user(user_id, payload)


@router.delete(
    "/{user_id}",
    status_code=204,
    summary="Soft-delete a user (admin only)",
    dependencies=[Depends(require_roles("admin"))],
)
async def delete_user(user_id: uuid.UUID, db: DbSession) -> None:
    """Soft-delete a user (sets deleted_at, deactivates account).

    Args:
        user_id: UUID of the user to delete.
        db: Database session.
    """
    await UserService(db).delete_user(user_id)
