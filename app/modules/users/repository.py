"""Users and Roles repository — data access layer."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.models import Role, User


class RoleRepository:
    """Data access object for Role entities.

    Args:
        db: The active AsyncSession injected via FastAPI dependency.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_id(self, role_id: uuid.UUID) -> Role | None:
        """Fetch a role by its primary key.

        Args:
            role_id: UUID of the role to retrieve.

        Returns:
            Role | None: The Role instance, or None if not found.
        """
        result = await self._db.execute(select(Role).where(Role.id == role_id))
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Role | None:
        """Fetch a role by its unique name.

        Args:
            name: The machine-readable role name (e.g., "therapist").

        Returns:
            Role | None: The Role instance, or None if not found.
        """
        result = await self._db.execute(select(Role).where(Role.name == name))
        return result.scalar_one_or_none()

    async def list_all(self) -> list[Role]:
        """Return all roles ordered by name.

        Returns:
            list[Role]: All persisted roles.
        """
        result = await self._db.execute(select(Role).order_by(Role.name))
        return list(result.scalars().all())

    async def create(self, name: str, description: str | None = None) -> Role:
        """Persist a new Role.

        Args:
            name: Unique role name.
            description: Optional human-readable description.

        Returns:
            Role: The newly created and flushed Role instance.
        """
        role = Role(name=name, description=description)
        self._db.add(role)
        await self._db.flush()
        return role


class UserRepository:
    """Data access object for User entities.

    Args:
        db: The active AsyncSession injected via FastAPI dependency.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        """Fetch an active (non-deleted) user by primary key.

        Args:
            user_id: UUID of the user to retrieve.

        Returns:
            User | None: The User instance, or None if not found or soft-deleted.
        """
        result = await self._db.execute(
            select(User).where(User.id == user_id, User.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        """Fetch an active user by email address (case-insensitive).

        Args:
            email: The email address to search for.

        Returns:
            User | None: The User instance, or None if not found.
        """
        result = await self._db.execute(
            select(User).where(
                func.lower(User.email) == email.lower(),
                User.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_paginated(
        self,
        page: int = 1,
        page_size: int = 20,
        role_name: str | None = None,
    ) -> tuple[list[User], int]:
        """Return a paginated list of active users with optional role filter.

        Args:
            page: 1-indexed page number.
            page_size: Number of records per page.
            role_name: Optional role name to filter by.

        Returns:
            tuple[list[User], int]: The page of users and the total count.
        """
        from app.modules.users.models import Role

        query = select(User).where(User.deleted_at.is_(None))
        if role_name:
            query = query.join(Role).where(Role.name == role_name)
        query = query.order_by(User.created_at.desc())

        count_result = await self._db.execute(
            select(func.count()).select_from(query.subquery())
        )
        total = count_result.scalar_one()

        offset = (page - 1) * page_size
        paginated = await self._db.execute(query.offset(offset).limit(page_size))
        return list(paginated.scalars().all()), total

    async def create(self, **kwargs) -> User:
        """Persist a new User.

        Args:
            **kwargs: Field values matching User model attributes.

        Returns:
            User: The newly created and flushed User instance.
        """
        user = User(**kwargs)
        self._db.add(user)
        await self._db.flush()
        return user

    async def update(self, user: User, **kwargs) -> User:
        """Apply partial updates to a User instance.

        Args:
            user: The User ORM instance to update.
            **kwargs: Fields to update (only non-None values are applied).

        Returns:
            User: The updated and flushed User instance.
        """
        for field, value in kwargs.items():
            if value is not None:
                setattr(user, field, value)
        await self._db.flush()
        return user

    async def soft_delete(self, user: User) -> User:
        """Mark a user as deleted by setting deleted_at timestamp.

        Args:
            user: The User ORM instance to soft-delete.

        Returns:
            User: The updated User instance with deleted_at set.
        """
        user.deleted_at = datetime.now(UTC)
        user.is_active = False
        await self._db.flush()
        return user

    async def update_last_login(self, user: User) -> None:
        """Update the user's last_login timestamp to now.

        Args:
            user: The User ORM instance to update.
        """
        user.last_login = datetime.now(UTC)
        await self._db.flush()
