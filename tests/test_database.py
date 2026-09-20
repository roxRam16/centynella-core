import pytest

from src.config import get_settings
from src.database import DatabaseManager


@pytest.mark.anyio
async def test_ping_devuelve_false_sin_lanzar_si_mongo_no_esta_disponible():
    # Puerto 1: nadie escucha. El timeout corto evita esperar los 30 s por defecto.
    manager = DatabaseManager("mongodb://127.0.0.1:1", "test", timeout_ms=200)
    try:
        assert await manager.ping() is False
    finally:
        await manager.close()


@pytest.mark.anyio
async def test_expone_la_base_de_datos_configurada():
    manager = DatabaseManager("mongodb://127.0.0.1:1", "mi_db", timeout_ms=200)
    try:
        assert manager.db.name == "mi_db"
    finally:
        await manager.close()


@pytest.mark.integration
@pytest.mark.anyio
async def test_ping_con_la_mongodb_del_ambiente_activo():
    """Conecta a la MongoDB definida en `private/.env.<APP_ENV>` (Atlas).

    Ejecutar con `pytest -m integration` (ambiente por defecto: sandbox).
    Solo hace `ping`: no lee ni escribe datos.
    """
    get_settings.cache_clear()
    settings = get_settings()
    manager = DatabaseManager(
        settings.mongodb_uri, settings.mongodb_db, settings.mongodb_timeout_ms
    )
    try:
        assert await manager.ping() is True
    finally:
        await manager.close()
