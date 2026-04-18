"""Roles seeder — creates the base system roles."""

from loguru import logger
from sqlalchemy import select

from app.modules.users.models import Role
from app.seeders.base_seeder import BaseSeeder

ROLES = [
    {"name": "admin", "description": "Full system access. Manages users, roles, and configuration."},
    {"name": "therapist", "description": "Conducts therapy sessions. Accesses own patients and sessions."},
    {"name": "receptionist", "description": "Manages patient registration and appointment scheduling."},
]


class RolesSeeder(BaseSeeder):
    """Seeds the system roles (admin, therapist, receptionist).

    Roles are idempotent: existing roles with the same name are not duplicated.
    """

    async def run(self) -> None:
        """Create all predefined system roles if they do not already exist."""
        for role_data in ROLES:
            existing = await self._db.execute(
                select(Role).where(Role.name == role_data["name"])
            )
            if existing.scalar_one_or_none() is None:
                self._db.add(Role(**role_data))
                logger.info("Created role: {}", role_data["name"])
            else:
                logger.debug("Role already exists: {}", role_data["name"])
        await self._db.flush()
