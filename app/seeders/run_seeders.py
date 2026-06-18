"""
Seeder runner — executes all seeders in dependency order.

Usage (inside Docker container):
    docker compose exec serena_api python -m app.seeders.run_seeders

Usage (locally with .venv active):
    python -m app.seeders.run_seeders
"""

import asyncio

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.seeders.alerts_seeder import AlertsSeeder
from app.seeders.biometric_seeder import BiometricSeeder
from app.seeders.patients_seeder import PatientsSeeder
from app.seeders.roles_seeder import RolesSeeder
from app.seeders.sessions_seeder import SessionsSeeder
from app.seeders.users_seeder import UsersSeeder

# Import all models to ensure they are registered in the SQLAlchemy registry
import app.modules.users.models      # noqa
import app.modules.auth.models       # noqa
import app.modules.patients.models   # noqa
import app.modules.sessions.models   # noqa
import app.modules.biometric.models  # noqa
import app.modules.alerts.models     # noqa


async def run_all_seeders() -> None:
    """Execute all seeders in strict dependency order within a single transaction.

    Order matters:
        1. Roles        (no dependencies)
        2. Users        (depends on Roles)
        3. Patients     (depends on Users/Therapists)
        4. Sessions     (depends on Patients)
        5. Biometric    (depends on Sessions)
        6. Alerts       (depends on Sessions + Patients)
    """
    connect_args = {}
    if "render.com" in settings.DATABASE_URL:
        connect_args["ssl"] = True

    engine = create_async_engine(settings.DATABASE_URL, echo=False, connect_args=connect_args)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as db:
        seeders = [
            RolesSeeder(db),
            UsersSeeder(db),
            PatientsSeeder(db),
            SessionsSeeder(db),
            BiometricSeeder(db),
            AlertsSeeder(db),
        ]

        for seeder in seeders:
            logger.info("Running seeder: {}", seeder.name)
            try:
                await seeder.run()
                await db.commit()
                logger.success("✓ {} completed", seeder.name)
            except Exception:
                await db.rollback()
                logger.exception("✗ {} failed — rolling back", seeder.name)
                raise

    await engine.dispose()
    logger.success("All seeders completed successfully.")


if __name__ == "__main__":
    asyncio.run(run_all_seeders())
