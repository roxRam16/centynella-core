"""Capa de servicios (lógica de negocio) y su contenedor."""

from dataclasses import dataclass

from src.config import Settings
from src.database import Repositories
from src.services.auth_service import AuthService, AuthSession
from src.services.bootstrap import bootstrap_admin, seed_roles
from src.services.email_sender import EmailSender, LogEmailSender
from src.services.greeting_service import GreetingService
from src.services.health_service import HealthService
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
    tokens: TokenService
    hasher: PasswordHasher


def build_services(
    settings: Settings, repositories: Repositories, email_sender: EmailSender
) -> Services:
    """Cablea los servicios (composition root de la capa de negocio)."""
    hasher = PasswordHasher()
    tokens = TokenService(settings)
    return Services(
        auth=AuthService(settings, repositories, hasher, tokens, email_sender),
        users=UserService(repositories, hasher),
        roles=RoleService(repositories),
        tokens=tokens,
        hasher=hasher,
    )


__all__ = [
    "AuthService",
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
    "build_services",
    "seed_roles",
]
