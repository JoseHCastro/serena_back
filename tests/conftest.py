"""
Pytest configuration and shared fixtures.

Provides an in-memory test database, async test client,
and a pre-seeded admin user for use across all test modules.
"""

import asyncio
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app

# Use an in-memory SQLite database for tests (fast, no setup required)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """Create and initialize the test database schema."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine):
    """Provide a transactional test database session that rolls back after each test."""
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_session):
    """Provide an async HTTP test client with the test DB session injected."""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_token(client, db_session):
    """Create an admin user and return a valid access token for authenticated requests."""
    from sqlalchemy import select
    from app.modules.users.models import Role, User

    # Ensure admin role exists
    role_result = await db_session.execute(select(Role).where(Role.name == "admin"))
    role = role_result.scalar_one_or_none()
    if not role:
        role = Role(name="admin", description="Administrator")
        db_session.add(role)
        await db_session.flush()

    # Create admin user
    user = User(
        email="test_admin@serena.com",
        hashed_password=hash_password("Admin1234!"),
        full_name="Test Admin",
        role_id=role.id,
    )
    db_session.add(user)
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "test_admin@serena.com", "password": "Admin1234!"},
    )
    return response.json()["access_token"]
