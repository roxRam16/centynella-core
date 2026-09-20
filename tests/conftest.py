"""Fixtures compartidas. Las pruebas unitarias NO requieren MongoDB real."""

import pytest
from fastapi.testclient import TestClient

from app import create_app
from src.config import Settings


class FakeDatabase:
    """Doble de `DatabaseManager`: permite simular Mongo arriba o caído."""

    def __init__(self, up: bool = True) -> None:
        self.up = up
        self.closed = False

    async def ping(self) -> bool:
        return self.up

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def settings() -> Settings:
    return Settings(
        app_name="CENTYNELLA-CORE",
        app_env="sandbox",
        app_version="9.9.9",
        cors_origins=["http://localhost:5173"],
    )


@pytest.fixture
def database() -> FakeDatabase:
    return FakeDatabase(up=True)


@pytest.fixture
def client(settings: Settings, database: FakeDatabase):
    # `with` dispara el lifespan (startup/shutdown) igual que en producción.
    with TestClient(create_app(settings, database)) as test_client:  # type: ignore[arg-type]
        yield test_client


@pytest.fixture
def anyio_backend() -> str:
    """Las pruebas asíncronas (`@pytest.mark.anyio`) corren solo sobre asyncio."""
    return "asyncio"
