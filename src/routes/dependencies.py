"""Proveedores de dependencias (Inyección de Dependencias de FastAPI).

Las rutas piden servicios con `Depends(...)`; nunca los construyen. Los recursos
compartidos (settings, base de datos) viven en `app.state`, creados en `create_app`,
lo que permite reemplazarlos limpiamente en las pruebas.
"""

from typing import Annotated

from fastapi import Depends, Request

from src.config import Settings
from src.database import DatabaseManager
from src.services import GreetingService, HealthService


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_database(request: Request) -> DatabaseManager:
    return request.app.state.database


def get_health_service(
    settings: Annotated[Settings, Depends(get_app_settings)],
    database: Annotated[DatabaseManager, Depends(get_database)],
) -> HealthService:
    return HealthService(settings, database)


def get_greeting_service(
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> GreetingService:
    return GreetingService(settings)


HealthServiceDep = Annotated[HealthService, Depends(get_health_service)]
GreetingServiceDep = Annotated[GreetingService, Depends(get_greeting_service)]
