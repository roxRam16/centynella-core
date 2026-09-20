"""Catálogo de permisos y roles de sistema.

Un *permiso* es una capacidad concreta con formato `recurso:acción`. Un *rol* es un
conjunto nombrado de permisos. El código protege endpoints por PERMISO (nunca por rol),
así los roles pueden reconfigurarse sin tocar código.

Cada módulo nuevo (inventario, pedidos…) añade aquí sus permisos.
"""

from dataclasses import dataclass
from enum import StrEnum


class Permission(StrEnum):
    USERS_READ = "users:read"
    USERS_CREATE = "users:create"
    USERS_UPDATE = "users:update"
    USERS_DELETE = "users:delete"
    ROLES_READ = "roles:read"
    ROLES_MANAGE = "roles:manage"
    LOGS_READ = "logs:read"


PERMISSION_DESCRIPTIONS: dict[Permission, str] = {
    Permission.USERS_READ: "Ver el listado y el detalle de usuarios",
    Permission.USERS_CREATE: "Crear usuarios",
    Permission.USERS_UPDATE: "Editar usuarios (nombre, rol, estado)",
    Permission.USERS_DELETE: "Eliminar usuarios",
    Permission.ROLES_READ: "Ver roles y permisos",
    Permission.ROLES_MANAGE: "Crear, editar y eliminar roles",
    Permission.LOGS_READ: "Consultar la bitácora del sistema",
}

ADMIN_ROLE = "admin"


@dataclass(frozen=True)
class SystemRole:
    key: str
    name: str
    description: str
    permissions: tuple[str, ...]


# Roles que se crean al arrancar. `admin` siempre se sincroniza con TODOS los permisos.
SYSTEM_ROLES: tuple[SystemRole, ...] = (
    SystemRole(
        key=ADMIN_ROLE,
        name="Administrador",
        description="Acceso total al sistema.",
        permissions=tuple(p.value for p in Permission),
    ),
    SystemRole(
        key="manager",
        name="Gerente",
        description="Consulta usuarios y roles.",
        permissions=(Permission.USERS_READ.value, Permission.ROLES_READ.value),
    ),
    SystemRole(
        key="viewer",
        name="Consulta",
        description="Usuario estándar sin permisos de administración (rol por defecto).",
        permissions=(),
    ),
)
