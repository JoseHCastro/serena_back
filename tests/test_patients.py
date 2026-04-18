"""Tests for the Patients module — CRUD operations."""

import pytest


@pytest.mark.asyncio
async def test_create_patient(client, admin_token, db_session):
    """Admin should be able to create a patient record."""
    response = await client.post(
        "/api/v1/patients/",
        json={
            "first_name": "María",
            "last_name": "González Pérez",
            "birth_date": "1990-05-15",
            "gender": "Femenino",
            "phone": "5512345678",
            "email": "maria.gonzalez@email.com",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["first_name"] == "María"
    assert data["code"].startswith("PAC-")
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_list_patients(client, admin_token):
    """Authenticated user should be able to list patients."""
    response = await client.get(
        "/api/v1/patients/",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_get_patient(client, admin_token):
    """Should retrieve a patient by ID."""
    # Create a patient first
    create_resp = await client.post(
        "/api/v1/patients/",
        json={"first_name": "Pedro", "last_name": "Ramírez"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    patient_id = create_resp.json()["id"]

    response = await client.get(
        f"/api/v1/patients/{patient_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    assert response.json()["id"] == patient_id


@pytest.mark.asyncio
async def test_update_patient(client, admin_token):
    """Should update a patient's notes."""
    create_resp = await client.post(
        "/api/v1/patients/",
        json={"first_name": "Luis", "last_name": "Torres"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    patient_id = create_resp.json()["id"]

    response = await client.patch(
        f"/api/v1/patients/{patient_id}",
        json={"medical_notes": "Actualización de notas clínicas."},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    assert response.json()["medical_notes"] == "Actualización de notas clínicas."


@pytest.mark.asyncio
async def test_delete_patient(client, admin_token):
    """Soft-deleting a patient should return 204 and hide the patient from listings."""
    create_resp = await client.post(
        "/api/v1/patients/",
        json={"first_name": "Ana", "last_name": "López"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    patient_id = create_resp.json()["id"]

    delete_resp = await client.delete(
        f"/api/v1/patients/{patient_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert delete_resp.status_code == 204

    get_resp = await client.get(
        f"/api/v1/patients/{patient_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_patient_not_found(client, admin_token):
    """Fetching a non-existent patient should return 404."""
    import uuid
    fake_id = uuid.uuid4()
    response = await client.get(
        f"/api/v1/patients/{fake_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"
