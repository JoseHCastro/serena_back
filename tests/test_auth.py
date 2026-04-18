"""Tests for the Auth module — login, refresh, and logout flows."""

import pytest


@pytest.mark.asyncio
async def test_login_success(client, admin_token):
    """Login should return access and refresh tokens for valid credentials."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "test_admin@serena.com", "password": "Admin1234!"},
    )
    # Token was already obtained via fixture; here we verify the endpoint works
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client, admin_token):
    """Login should return 401 for incorrect password."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "test_admin@serena.com", "password": "WrongPassword!"},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_login_unknown_email(client):
    """Login should return 401 for non-existent email."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "ghost@serena.com", "password": "Any1234!"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me(client, admin_token):
    """Authenticated user should be able to retrieve their own profile."""
    response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "test_admin@serena.com"
    assert data["role"]["name"] == "admin"


@pytest.mark.asyncio
async def test_get_me_no_token(client):
    """Unauthenticated request to /me should return 403 (no bearer token)."""
    response = await client.get("/api/v1/users/me")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_health_check(client):
    """Health endpoint should return 200 without authentication."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
