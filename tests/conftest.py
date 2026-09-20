"""Fixtures compartidas. Las pruebas unitarias NO requieren MongoDB real."""

import argon2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import create_app
from src.config import Settings
from src.database import Repositories
from tests.fakes import (
    FakeDatabase,
    InMemoryLogRepository,
    OutboxEmailSender,
    build_in_memory_repositories,
)

ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "Admin#12345"
USER_PASSWORD = "Segura#12345"


@pytest.fixture
def anyio_backend() -> str:
    """Las pruebas asíncronas (`@pytest.mark.anyio`) corren solo sobre asyncio."""
    return "asyncio"


@pytest.fixture(autouse=True)
def fast_password_hashing(monkeypatch):
    """Argon2 con costo mínimo: en producción se usan los parámetros seguros por defecto."""
    monkeypatch.setattr(
        "src.services.password_hasher._Argon2",
        lambda: argon2.PasswordHasher(time_cost=1, memory_cost=8, parallelism=1),
    )


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        app_name="CENTYNELLA-CORE",
        app_env="sandbox",
        app_version="9.9.9",
        cors_origins=["http://localhost:5173"],
        jwt_secret_key="clave-de-pruebas-de-al-menos-32-caracteres",
        bootstrap_admin_email=ADMIN_EMAIL,
        bootstrap_admin_password=ADMIN_PASSWORD,
        frontend_url="http://localhost:5173",
        log_flush_interval_seconds=0,  # la bitácora se escribe al instante en las pruebas
    )


@pytest.fixture
def database() -> FakeDatabase:
    return FakeDatabase(up=True)


@pytest.fixture
def repositories() -> Repositories:
    return build_in_memory_repositories()


@pytest.fixture
def log_repository() -> InMemoryLogRepository:
    return InMemoryLogRepository()


@pytest.fixture
def outbox() -> OutboxEmailSender:
    return OutboxEmailSender()


@pytest.fixture
def make_app(settings, database, repositories, outbox, log_repository):
    """Fábrica de apps con dobles en memoria; cada argumento puede sobrescribirse."""

    def factory(**overrides) -> FastAPI:
        options = {
            "settings": settings,
            "database": database,
            "repositories": repositories,
            "email_sender": outbox,
            "log_repository": log_repository,
        }
        return create_app(**{**options, **overrides})  # type: ignore[arg-type]

    return factory


@pytest.fixture
def client(make_app):
    # `with` dispara el lifespan (índices, roles de sistema, admin inicial) igual que en producción.
    with TestClient(make_app()) as test_client:
        yield test_client


def login(client: TestClient, email: str, password: str) -> dict:
    """Inicia sesión y devuelve el cuerpo de la respuesta (la cookie queda en `client`)."""
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers(client) -> dict[str, str]:
    """Cabeceras del administrador inicial (creado por `bootstrap_admin`)."""
    return auth_headers(login(client, ADMIN_EMAIL, ADMIN_PASSWORD)["access_token"])


@pytest.fixture
def register_user(client):
    """Registra una cuenta pública y devuelve su cuerpo JSON."""

    def register(name="Ana Pérez", email="ana@example.com", password=USER_PASSWORD) -> dict:
        response = client.post(
            "/api/v1/auth/register", json={"name": name, "email": email, "password": password}
        )
        assert response.status_code == 201, response.text
        return response.json()

    return register


@pytest.fixture
def flush_logs(client):
    """Espera a que la bitácora termine de guardar lo pendiente (corre en el loop de la app)."""

    def flush() -> None:
        client.portal.call(client.app.state.events.flush)

    return flush
