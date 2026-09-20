from fastapi.testclient import TestClient

from app import create_app
from src.config import Settings


def test_swagger_y_redoc_disponibles(client):
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200


def test_openapi_documenta_los_endpoints(client):
    schema = client.get("/openapi.json").json()

    assert schema["info"]["title"] == "CENTYNELLA-CORE"
    assert schema["info"]["version"] == "9.9.9"
    assert {"/health", "/health/ready", "/api/v1/greeting"} <= set(schema["paths"])
    assert "503" in schema["paths"]["/health/ready"]["get"]["responses"]


def test_docs_se_pueden_desactivar(database):
    settings = Settings(docs_enabled=False)
    with TestClient(create_app(settings, database)) as client:  # type: ignore[arg-type]
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404


def test_cors_permite_el_origen_del_shell(client):
    response = client.get("/health", headers={"Origin": "http://localhost:5173"})

    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_no_permite_origenes_desconocidos(client):
    response = client.get("/health", headers={"Origin": "http://malicioso.example"})

    assert "access-control-allow-origin" not in response.headers
