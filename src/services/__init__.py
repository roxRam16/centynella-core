"""Capa de servicios (lógica de negocio) y su contenedor."""

from dataclasses import dataclass

from src.config import Settings
from src.database import LogRepository, Repositories
from src.services.auth_service import AuthService, AuthSession
from src.services.bootstrap import bootstrap_admin, seed_roles
from src.services.email_sender import EmailSender, LogEmailSender
from src.services.event_logger import BridgeLogHandler, EventLogger, mask_email
from src.services.greeting_service import GreetingService
from src.services.health_service import HealthService
from src.services.log_service import LogService
from src.services.password_hasher import PasswordHasher
from src.services.role_service import RoleService
from src.services.token_service import TokenService
from src.services.user_service import UserService


@dataclass
class Services:
    """Servicios de autenticación y administración, listos para inyectar en las rutas."""

    auth: AuthService
    users: UserService
    roles: RoleService
    logs: LogService
    events: EventLogger
    tokens: TokenService
    hasher: PasswordHasher


def build_services(
    settings: Settings,
    repositories: Repositories,
    email_sender: EmailSender,
    events: EventLogger,
    log_repository: LogRepository,
) -> Services:
    """Cablea los servicios (composition root de la capa de negocio)."""
    hasher = PasswordHasher()
    tokens = TokenService(settings)
    return Services(
        auth=AuthService(settings, repositories, hasher, tokens, email_sender, events),
        users=UserService(repositories, hasher, events),
        roles=RoleService(repositories, events),
        logs=LogService(log_repository),
        events=events,
        tokens=tokens,
        hasher=hasher,
    )


__all__ = [
    "AuthService",
    "BridgeLogHandler",
    "EventLogger",
    "LogService",
    "AuthSession",
    "EmailSender",
    "GreetingService",
    "HealthService",
    "LogEmailSender",
    "PasswordHasher",
    "RoleService",
    "Services",
    "TokenService",
    "UserService",
    "bootstrap_admin",
    "mask_email",
    "build_services",
    "seed_roles",
]
