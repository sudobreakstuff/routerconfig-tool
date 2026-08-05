"""End-to-end API tests against the FastAPI app (uses a throwaway data dir)."""

import os

import pytest

os.environ["RC_DATA_DIR"] = "/tmp/routerconfig-test-apitests"

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402


@pytest.fixture()
def client():
    app = main.create_app()
    with TestClient(app) as c:
        yield c


def test_health_public(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_settings_app_returns_token(client):
    r = client.get("/api/settings/app")
    assert r.status_code == 200
    assert r.json()["token"]


def test_protected_routes_require_token(client):
    r = client.get("/api/devices")
    assert r.status_code == 401


def test_protected_routes_accept_token(client):
    token = client.get("/api/settings/app").json()["token"]
    r = client.get("/api/devices", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


def test_invalid_token_rejected(client):
    r = client.get("/api/devices", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401
