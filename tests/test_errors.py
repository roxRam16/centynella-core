"""Los errores siguen Problem Details (RFC 9457) con `application/problem+json`."""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel


class _Payload(BaseModel):
    quantity: int


@pytest.fixture
def app_with_test_routes(make_app):
    app = make_app()

    @app.post("/_test/validate")
    async def validate(payload: _Payload) -> dict:
        return payload.model_dump()

    @app.get("/_test/conflict")
    async def conflict() -> None:
        raise HTTPException(status_code=409, detail="El SKU ya existe")

    @app.get("/_test/boom")
    async def boom() -> None:
        raise RuntimeError("secreto interno que no debe filtrarse")

    return app


def test_404_es_problem_details(client):
    response = client.get("/api/v1/no-existe")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["title"] == "Not Found"
    assert body["status"] == 404
    assert body["instance"] == "/api/v1/no-existe"
    assert body["request_id"] == response.headers["x-request-id"]


def test_http_exception_usa_su_detalle(app_with_test_routes):
    with TestClient(app_with_test_routes) as client:
        response = client.get("/_test/conflict")

    assert response.status_code == 409
    assert response.json()["detail"] == "El SKU ya existe"


def test_422_lista_los_errores_de_validacion(app_with_test_routes):
    with TestClient(app_with_test_routes) as client:
        response = client.post("/_test/validate", json={"quantity": "abc"})

    assert response.status_code == 422
    body = response.json()
    assert body["status"] == 422
    assert body["errors"][0]["loc"] == ["body", "quantity"]


def test_500_no_filtra_detalles_internos(app_with_test_routes):
    with TestClient(app_with_test_routes, raise_server_exceptions=False) as client:
        response = client.get("/_test/boom")

    assert response.status_code == 500
    assert "secreto interno" not in response.text
    assert response.json()["title"] == "Internal Server Error"
