"""Punto de entrada de CENTYNELLA-CORE (FastAPI).

    uvicorn app:app --reload --port 8000

Swagger UI: http://localhost:8000/docs · ReDoc: /redoc · OpenAPI: /openapi.json
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import Settings, get_settings
from src.database import DatabaseManager
from src.middlewares import REQUEST_ID_HEADER, RequestIdMiddleware, register_exception_handlers
from src.routes import api_v1_router, health_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

API_DESCRIPTION = """
API de **CENTYNELLA-CORE**: administración y gestión de inventarios.

* Contrato RESTful versionado bajo `/api/v1`.
* Errores en formato *Problem Details* (RFC 9457).
* Sondas de salud en `/health` (liveness) y `/health/ready` (readiness).
"""

TAGS_METADATA = [
    {"name": "Health", "description": "Sondas de salud para balanceador, ECS y Docker."},
    {"name": "Greeting", "description": "Prueba de humo *Hola Mundo* de la API."},
]


def create_app(
    settings: Settings | None = None, database: DatabaseManager | None = None
) -> FastAPI:
    """Application Factory: construye la app con dependencias inyectables.

    Args:
        settings: configuración; por defecto la del ambiente (`private/.env.<APP_ENV>`).
        database: manager de MongoDB; por defecto se crea uno con `settings`. Las pruebas
            inyectan aquí un doble para no depender de una base real.
    """
    settings = settings or get_settings()
    database = database or DatabaseManager(
        settings.mongodb_uri, settings.mongodb_db, settings.mongodb_timeout_ms
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await database.close()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=API_DESCRIPTION,
        openapi_tags=TAGS_METADATA,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.database = database

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=[REQUEST_ID_HEADER],
    )
    # Añadido al final = capa más externa: el request id llega también a CORS y errores.
    app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(app)

    app.include_router(health_router)
    app.include_router(api_v1_router)
    return app


app = create_app()

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)  # noqa: S104
