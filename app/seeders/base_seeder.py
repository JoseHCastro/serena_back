"""Base seeder interface.

All seeders must inherit from BaseSeeder and implement the `run` method.
This ensures a consistent interface that run_seeders.py can rely on.
"""

from abc import ABC, abstractmethod

from sqlalchemy.ext.asyncio import AsyncSession


class BaseSeeder(ABC):
    """Abstract base class for all database seeders.

    Args:
        db: An active AsyncSession to use for all database operations.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    @abstractmethod
    async def run(self) -> None:
        """Execute the seeder logic.

        Implementations should use self._db for all database operations.
        Do NOT call db.commit() inside run() — the runner handles commits.
        """
        ...

    @property
    def name(self) -> str:
        """Human-readable name of this seeder (defaults to class name)."""
        return self.__class__.__name__
