from datetime import datetime

from fastapi.testclient import TestClient

from tests.fakes import FakeDatabase


def test_liveness_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "CENTYNELLA-CORE"
    assert body["version"] == "9.9.9"
    datetime.fromisoformat(body["timestamp"])  # timestamp ISO-8601 válido
    assert response.headers["cache-control"] == "no-store"


def test_liveness_no_consulta_dependencias(make_app):
    """Con Mongo caído, liveness sigue respondiendo 200 (el proceso está vivo)."""
    with TestClient(make_app(database=FakeDatabase(up=False))) as client:
        assert client.get("/health").status_code == 200


def test_readiness_ready_cuando_mongo_responde(client):
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["dependencies"] == {"mongodb": "up"}


def test_readiness_503_cuando_mongo_esta_caido(make_app):
    with TestClient(make_app(database=FakeDatabase(up=False))) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert response.json()["dependencies"] == {"mongodb": "down"}


def test_el_lifespan_cierra_la_base_de_datos(make_app, database):
    with TestClient(make_app()):
        assert database.closed is False

    assert database.closed is True
