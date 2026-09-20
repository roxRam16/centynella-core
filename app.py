"""Punto de entrada de CENTYNELLA-CORE (FastAPI).

    uvicorn app:create_app --factory --reload --port 8000     (o simplemente: python app.py)

Swagger UI: http://localhost:8000/docs · ReDoc: /redoc · OpenAPI: /openapi.json
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import Settings, get_settings
from src.database import DatabaseManager, Repositories, build_mongo_repositories
from src.middlewares import REQUEST_ID_HEADER, RequestIdMiddleware, register_exception_handlers
from src.routes import api_v1_router, health_router
from src.services import (
    EmailSender,
    LogEmailSender,
    Services,
    bootstrap_admin,
    build_services,
    seed_roles,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

API_DESCRIPTION = """
API de **CENTYNELLA-CORE**: administración y gestión de inventarios.

* Contrato RESTful versionado bajo `/api/v1`.
* Autenticación con **JWT** (`Authorization: Bearer`) + refresh token en cookie HttpOnly.
  Usa el botón **Authorize** e inicia sesión con `POST /api/v1/auth/login`.
* Autorización por **permisos** asignados a roles.
* Errores en formato *Problem Details* (RFC 9457) con un `code` estable.
* Sondas de salud en `/health` (liveness) y `/health/ready` (readiness).
"""

TAGS_METADATA = [
    {"name": "Authentication", "description": "Registro, sesión, recuperación de contraseña."},
    {"name": "Users", "description": "Perfil propio y administración de usuarios."},
    {"name": "Roles", "description": "Roles y permisos."},
    {"name": "Health", "description": "Sondas de salud para balanceador, ECS y Docker."},
    {"name": "Greeting", "description": "Prueba de humo *Hola Mundo* de la API."},
]


async def _prepare_data(settings: Settings, repositories: Repositories, services: Services) -> None:
    """Índices, roles de sistema y administrador inicial. Un fallo no impide arrancar
    (`/health/ready` reportará la base de datos caída)."""
    try:
        await repositories.ensure_indexes()
        await seed_roles(repositories)
        await bootstrap_admin(settings, repositories, services.hasher)
    except Exception:
        logger.exception("No se pudieron preparar los datos iniciales (¿MongoDB disponible?)")


def create_app(
    settings: Settings | None = None,
    database: DatabaseManager | None = None,
    repositories: Repositories | None = None,
    email_sender: EmailSender | None = None,
) -> FastAPI:
    """Application Factory: construye la app con dependencias inyectables.

    Args:
        settings: configuración; por defecto la del ambiente (`private/.env.<APP_ENV>`).
        database: manager de MongoDB; por defecto se crea uno con `settings`.
        repositories: repositorios de datos; por defecto los de MongoDB sobre `database`.
        email_sender: envío de correos; por defecto solo registra el correo en el log.
    Las pruebas inyectan dobles en memoria para no depender de una base real.
    """
    settings = settings or get_settings()
    database = database or DatabaseManager(
        settings.mongodb_uri, settings.mongodb_db, settings.mongodb_timeout_ms
    )
    repositories = repositories or build_mongo_repositories(database.db)
    services = build_services(settings, repositories, email_sender or LogEmailSender())

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await _prepare_data(settings, repositories, services)
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
    app.state.services = services

    if "*" in settings.cors_origins:
        logger.warning(
            "CORS_ORIGINS contiene '*': se ignora porque la sesión usa cookies. "
            "Lista los orígenes exactos (ej. http://localhost:5173)."
        )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.explicit_cors_origins,
        allow_credentials=True,  # necesario para la cookie del refresh token
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=[REQUEST_ID_HEADER],
    )
    # Añadido al final = capa más externa: el request id llega también a CORS y errores.
    app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(app)

    app.include_router(health_router)
    app.include_router(api_v1_router)
    return app


if __name__ == "__main__":
    uvicorn.run("app:create_app", factory=True, host="0.0.0.0", port=8000, reload=True)  # noqa: S104
