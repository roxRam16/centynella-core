"""Proveedores de dependencias (Inyección de Dependencias de FastAPI).

Las rutas piden servicios con `Depends(...)`; nunca los construyen. Los recursos
compartidos (settings, base de datos, servicios) viven en `app.state`, creados en
`create_app`, lo que permite reemplazarlos limpiamente en las pruebas.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.config import Settings
from src.database import DatabaseManager
from src.models import Permission, UserDocument
from src.services import GreetingService, HealthService, Services
from src.services.errors import AuthenticationError, NotFoundError, PermissionDeniedError

# `auto_error=False`: los errores los produce `get_current_user` en formato Problem Details.
_bearer = HTTPBearer(auto_error=False, description="Access token JWT obtenido en `/auth/login`.")
_WWW_AUTHENTICATE = {"WWW-Authenticate": "Bearer"}


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_database(request: Request) -> DatabaseManager:
    return request.app.state.database


def get_services(request: Request) -> Services:
    return request.app.state.services


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
ServicesDep = Annotated[Services, Depends(get_services)]


def get_health_service(
    settings: SettingsDep, database: Annotated[DatabaseManager, Depends(get_database)]
) -> HealthService:
    return HealthService(settings, database)


def get_greeting_service(settings: SettingsDep) -> GreetingService:
    return GreetingService(settings)


HealthServiceDep = Annotated[HealthService, Depends(get_health_service)]
GreetingServiceDep = Annotated[GreetingService, Depends(get_greeting_service)]


@dataclass
class CurrentUser:
    """Usuario autenticado de la petición, con sus permisos efectivos."""

    user: UserDocument
    permissions: list[str]

    @property
    def id(self) -> str:
        return self.user.id or ""


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    services: ServicesDep,
) -> CurrentUser:
    """Valida el access token y carga al usuario (rechaza cuentas eliminadas o deshabilitadas)."""
    if credentials is None:
        raise AuthenticationError(
            "Debes iniciar sesión.", code="not_authenticated", headers=_WWW_AUTHENTICATE
        )
    try:
        user_id = services.tokens.decode_access_token(credentials.credentials)
        user = await services.users.get(user_id)
    except AuthenticationError as error:
        raise AuthenticationError(
            error.detail, code=error.code, headers=_WWW_AUTHENTICATE
        ) from error
    except NotFoundError as error:
        raise AuthenticationError(
            "La cuenta ya no existe.", code="invalid_token", headers=_WWW_AUTHENTICATE
        ) from error

    if user.status != "active":
        raise AuthenticationError(
            "Tu cuenta está deshabilitada.", code="account_disabled", headers=_WWW_AUTHENTICATE
        )
    return CurrentUser(user, await services.users.permissions_of(user))


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


def require_permission(*required: Permission) -> Callable[..., Awaitable[CurrentUser]]:
    """Dependencia que exige TODOS los permisos indicados (se protege por permiso, no por rol).

    Uso: `Depends(require_permission(Permission.USERS_READ))`.
    """

    async def dependency(current: CurrentUserDep) -> CurrentUser:
        missing = [p.value for p in required if p.value not in current.permissions]
        if missing:
            raise PermissionDeniedError(
                f"No tienes permiso para esta acción ({', '.join(missing)}).",
                code="insufficient_permissions",
            )
        return current

    return dependency
