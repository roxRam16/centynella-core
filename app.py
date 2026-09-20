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
from src.database import (
    DatabaseManager,
    LogRepository,
    MongoLogRepository,
    Repositories,
    build_mongo_repositories,
)
from src.middlewares import (
    REQUEST_ID_HEADER,
    AccessLogMiddleware,
    BodySizeLimitMiddleware,
    RequestIdMiddleware,
    SecurityHeadersMiddleware,
    register_exception_handlers,
)
from src.routes import api_v1_router, health_router
from src.services import (
    BridgeLogHandler,
    EmailSender,
    EventLogger,
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
* **Bitácora** de todo lo que ocurre (por módulo, usuario y sesión) en una base de datos aparte.
* Errores en formato *Problem Details* (RFC 9457) con un `code` estable.
* Sondas de salud en `/health` (liveness) y `/health/ready` (readiness).
"""

TAGS_METADATA = [
    {"name": "Authentication", "description": "Registro, sesión, recuperación de contraseña."},
    {"name": "Users", "description": "Perfil propio y administración de usuarios."},
    {"name": "Roles", "description": "Roles y permisos."},
    {"name": "Logs", "description": "Bitácora del sistema (solo lectura)."},
    {"name": "Health", "description": "Sondas de salud para balanceador, ECS y Docker."},
    {"name": "Greeting", "description": "Prueba de humo *Hola Mundo* de la API."},
]


async def _prepare_data(
    settings: Settings,
    repositories: Repositories,
    log_repository: LogRepository,
    services: Services,
    database: DatabaseManager,
) -> None:
    """Conexión, índices, roles de sistema y administrador inicial; todo queda en la bitácora.
    Un fallo no impide arrancar (`/health/ready` reportará la base de datos caída)."""
    events = services.events
    try:
        if await database.ping():
            events.info(
                "database",
                "database.connected",
                "MongoDB conectada",
                database=settings.mongodb_db,
                logs_database=settings.mongodb_logs_db,
            )
        else:
            events.error(
                "database",
                "database.unreachable",
                "MongoDB no responde al arrancar",
                database=settings.mongodb_db,
            )
        await repositories.ensure_indexes()
        ensure_log_indexes = getattr(log_repository, "ensure_indexes", None)
        if ensure_log_indexes is not None:
            await ensure_log_indexes()
        events.info("database", "database.indexes_ready", "Índices verificados")
        await seed_roles(repositories, events)
        await bootstrap_admin(settings, repositories, services.hasher, events)
    except Exception as error:
        logger.exception("No se pudieron preparar los datos iniciales (¿MongoDB disponible?)")
        events.error(
            "system",
            "system.startup_data_failed",
            "No se prepararon los datos iniciales",
            error=str(error),
        )


def create_app(
    settings: Settings | None = None,
    database: DatabaseManager | None = None,
    repositories: Repositories | None = None,
    email_sender: EmailSender | None = None,
    log_repository: LogRepository | None = None,
) -> FastAPI:
    """Application Factory: construye la app con dependencias inyectables.

    Args:
        settings: configuración; por defecto la del ambiente (`private/.env.<APP_ENV>`).
        database: manager de MongoDB; por defecto se crea uno con `settings`.
        repositories: repositorios de datos; por defecto los de MongoDB sobre `database`.
        email_sender: envío de correos; por defecto solo registra el correo en el log.
        log_repository: bitácora; por defecto la base de datos de logs de MongoDB.
    Las pruebas inyectan dobles en memoria para no depender de una base real.
    """
    settings = settings or get_settings()
    database = database or DatabaseManager(
        settings.mongodb_uri,
        settings.mongodb_db,
        settings.mongodb_timeout_ms,
        settings.mongodb_logs_db,
    )
    repositories = repositories or build_mongo_repositories(database.db)
    log_repository = log_repository or MongoLogRepository(
        database.logs_db, settings.log_retention_days
    )
    events = EventLogger(
        log_repository,
        service=settings.service_name,
        environment=settings.app_env,
        min_level=settings.log_min_level,
        flush_interval=settings.log_flush_interval_seconds,
    )
    services = build_services(
        settings, repositories, email_sender or LogEmailSender(), events, log_repository
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await events.start()
        bridge = BridgeLogHandler(events)  # avisos/errores de Python también a la bitácora
        logging.getLogger().addHandler(bridge)
        events.info(
            "system",
            "system.startup",
            f"{settings.app_name} iniciando",
            version=settings.app_version,
            environment=settings.app_env,
        )
        await _prepare_data(settings, repositories, log_repository, services, database)
        yield
        events.info("system", "system.shutdown", f"{settings.app_name} apagándose")
        logging.getLogger().removeHandler(bridge)
        await events.stop()
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
    app.state.events = events

    if "*" in settings.cors_origins:
        logger.warning(
            "CORS_ORIGINS contiene '*': se ignora porque la sesión usa cookies. "
            "Lista los orígenes exactos (ej. http://localhost:5173)."
        )
    # add_middleware: el PRIMERO queda más adentro y el ÚLTIMO más afuera.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.explicit_cors_origins,
        allow_credentials=True,  # necesario para la cookie del refresh token
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=[REQUEST_ID_HEADER],
    )
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_body_bytes)
    app.add_middleware(AccessLogMiddleware, events=events)
    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.cookie_secure)
    app.add_middleware(RequestIdMiddleware)  # la más externa: todo lleva id y contexto
    register_exception_handlers(app)

    app.include_router(health_router)
    app.include_router(api_v1_router)
    return app


if __name__ == "__main__":
    uvicorn.run("app:create_app", factory=True, host="0.0.0.0", port=8000, reload=True)  # noqa: S104
