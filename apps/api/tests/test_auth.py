import os
from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite://")

from apps.api.database import Base, get_db
from apps.api.main import app


@asynccontextmanager
async def app_lifespan(_app):
    yield


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-signing-secret-that-is-long-enough-123456")
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        session = testing_session()
        try:
            yield session
        finally:
            session.close()

    previous_lifespan = app.router.lifespan_context
    app.router.lifespan_context = app_lifespan
    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.router.lifespan_context = previous_lifespan
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def register(client: TestClient, email: str):
    response = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "correct horse battery staple",
            "organization_name": "Test organization",
        },
    )
    assert response.status_code == 201
    return response.json()


def bearer(token: str):
    return {"Authorization": f"Bearer {token}"}


def test_authentication_and_tenant_isolation(client):
    first = register(client, "First@Example.com")
    first_token = first["access_token"]
    first_org = first["organizations"][0]["id"]

    assert client.get("/organizations").status_code == 401
    organizations = client.get("/organizations", headers=bearer(first_token))
    assert organizations.status_code == 200
    assert [item["id"] for item in organizations.json()] == [first_org]

    project_response = client.post(
        f"/organizations/{first_org}/projects",
        headers=bearer(first_token),
        json={"name": "Private project"},
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]
    assert client.get(
        f"/organizations/{first_org}/projects",
        headers=bearer(first_token),
    ).json()[0]["id"] == project_id

    second = register(client, "second@example.com")
    second_token = second["access_token"]
    assert client.get("/organizations", headers=bearer(second_token)).json() == second["organizations"]
    assert client.get(
        f"/projects/{project_id}/documents",
        headers=bearer(second_token),
    ).status_code == 404
    assert client.post(
        f"/organizations/{first_org}/projects",
        headers=bearer(second_token),
        json={"name": "Unauthorized"},
    ).status_code == 404


def test_login_rejects_wrong_credentials_and_registration_conflicts(client):
    register(client, "person@example.com")

    login = client.post(
        "/auth/login",
        json={"email": "PERSON@example.com", "password": "correct horse battery staple"},
    )
    assert login.status_code == 200
    assert login.json()["token_type"] == "bearer"

    wrong_password = client.post(
        "/auth/login",
        json={"email": "person@example.com", "password": "wrong password"},
    )
    assert wrong_password.status_code == 401

    duplicate = client.post(
        "/auth/register",
        json={
            "email": "PERSON@example.com",
            "password": "another correct horse battery staple",
            "organization_name": "Duplicate",
        },
    )
    assert duplicate.status_code == 409


def test_protected_route_rejects_invalid_token(client):
    response = client.get("/organizations", headers=bearer("not-a-valid-token"))
    assert response.status_code == 401


def test_authentication_requires_configured_signing_secret(client, monkeypatch):
    monkeypatch.delenv("JWT_SECRET")
    response = client.post(
        "/auth/login",
        json={"email": "person@example.com", "password": "password"},
    )
    assert response.status_code == 503
