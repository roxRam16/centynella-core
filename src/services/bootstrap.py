"""Datos iniciales: roles de sistema y administrador de arranque."""

import logging
from contextlib import suppress

from src.config import Settings
from src.database import DuplicateError, Repositories
from src.models import ADMIN_ROLE, SYSTEM_ROLES, RoleDocument, UserDocument
from src.services.event_logger import EventLogger
from src.services.password_hasher import PasswordHasher

logger = logging.getLogger(__name__)


async def seed_roles(repositories: Repositories, events: EventLogger | None = None) -> None:
    """Crea los roles de sistema que falten. Idempotente y seguro con varias instancias.

    · Los roles existentes NO se pisan (un administrador pudo ajustar sus permisos).
    · `admin` sí se sincroniza siempre: al añadir un permiso nuevo al código, el admin lo recibe.
    """
    for system_role in SYSTEM_ROLES:
        existing = await repositories.roles.get(system_role.key)
        if existing is None:
            with suppress(DuplicateError):  # otra instancia lo creó a la vez
                await repositories.roles.create(
                    RoleDocument(
                        id=system_role.key,
                        name=system_role.name,
                        description=system_role.description,
                        permissions=list(system_role.permissions),
                        is_system=True,
                    )
                )
                if events:
                    events.info(
                        "system", "roles.seeded", "Rol de sistema creado", role_key=system_role.key
                    )
        elif system_role.key == ADMIN_ROLE and sorted(existing.permissions) != sorted(
            system_role.permissions
        ):
            await repositories.roles.update(
                ADMIN_ROLE, {"permissions": sorted(system_role.permissions)}
            )


async def bootstrap_admin(
    settings: Settings,
    repositories: Repositories,
    hasher: PasswordHasher,
    events: EventLogger | None = None,
) -> bool:
    """Crea el primer administrador si no hay ningún usuario y hay credenciales configuradas.

    Devuelve `True` si lo creó. Solo actúa con la base vacía: nunca sobrescribe usuarios.
    """
    if not (settings.bootstrap_admin_email and settings.bootstrap_admin_password):
        return False
    if await repositories.users.count() > 0:
        return False

    try:
        await repositories.users.create(
            UserDocument(
                email=settings.bootstrap_admin_email.strip().lower(),
                name=settings.bootstrap_admin_name,
                password_hash=await hasher.hash(settings.bootstrap_admin_password),
                role=ADMIN_ROLE,
            )
        )
    except DuplicateError:
        return False
    logger.info("Administrador inicial creado: %s", settings.bootstrap_admin_email)
    if events:
        events.warning(
            "system",
            "system.bootstrap_admin_created",
            "Administrador inicial creado",
            email=settings.bootstrap_admin_email,
        )
    return True
