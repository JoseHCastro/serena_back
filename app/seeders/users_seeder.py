"""Users seeder — creates default admin and sample therapists/receptionists."""

from loguru import logger
from sqlalchemy import select

from app.core.security import hash_password
from app.modules.users.models import Role, User
from app.seeders.base_seeder import BaseSeeder

SEED_USERS = [
    {
        "email": "admin@serena.com",
        "password": "Admin1234!",
        "full_name": "Administrador Serena",
        "role_name": "admin",
    },
    {
        "email": "dra.garcia@serena.com",
        "password": "Terapeuta1!",
        "full_name": "Dra. Laura García Mendoza",
        "role_name": "therapist",
    },
    {
        "email": "dr.martinez@serena.com",
        "password": "Terapeuta2!",
        "full_name": "Dr. Carlos Martínez López",
        "role_name": "therapist",
    },
    {
        "email": "recepcion@serena.com",
        "password": "Recepcion1!",
        "full_name": "Ana Sofía Ramírez",
        "role_name": "receptionist",
    },
]


class UsersSeeder(BaseSeeder):
    """Seeds default system users.

    Skips users whose email already exists to ensure idempotency.
    """

    async def run(self) -> None:
        """Create all predefined users if they do not already exist."""
        for user_data in SEED_USERS:
            existing = await self._db.execute(
                select(User).where(User.email == user_data["email"])
            )
            if existing.scalar_one_or_none() is not None:
                logger.debug("User already exists: {}", user_data["email"])
                continue

            role_result = await self._db.execute(
                select(Role).where(Role.name == user_data["role_name"])
            )
            role = role_result.scalar_one_or_none()
            if not role:
                logger.warning("Role '{}' not found, skipping user {}", user_data["role_name"], user_data["email"])
                continue

            user = User(
                email=user_data["email"],
                hashed_password=hash_password(user_data["password"]),
                full_name=user_data["full_name"],
                role_id=role.id,
            )
            self._db.add(user)
            logger.info("Created user: {} ({})", user_data["email"], user_data["role_name"])
        await self._db.flush()
