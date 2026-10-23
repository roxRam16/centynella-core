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
    PRODUCTS_READ = "products:read"
    PRODUCTS_CREATE = "products:create"
    PRODUCTS_UPDATE = "products:update"
    PRODUCTS_DELETE = "products:delete"
    CUSTOMERS_READ = "customers:read"
    CUSTOMERS_CREATE = "customers:create"
    CUSTOMERS_UPDATE = "customers:update"
    CUSTOMERS_DELETE = "customers:delete"
    CUSTOMERS_CREDIT = "customers:credit"


PERMISSION_DESCRIPTIONS: dict[Permission, str] = {
    Permission.USERS_READ: "Ver el listado y el detalle de usuarios",
    Permission.USERS_CREATE: "Crear usuarios",
    Permission.USERS_UPDATE: "Editar usuarios (nombre, rol, estado)",
    Permission.USERS_DELETE: "Eliminar usuarios",
    Permission.ROLES_READ: "Ver roles y permisos",
    Permission.ROLES_MANAGE: "Crear, editar y eliminar roles",
    Permission.LOGS_READ: "Consultar la bitácora del sistema",
    Permission.PRODUCTS_READ: "Ver el catálogo de productos y su existencia",
    Permission.PRODUCTS_CREATE: "Dar de alta productos",
    Permission.PRODUCTS_UPDATE: "Editar productos y ajustar su existencia",
    Permission.PRODUCTS_DELETE: "Eliminar productos",
    Permission.CUSTOMERS_READ: "Ver clientes y su saldo de fiado",
    Permission.CUSTOMERS_CREATE: "Dar de alta clientes",
    Permission.CUSTOMERS_UPDATE: "Editar datos de contacto y límite de crédito",
    Permission.CUSTOMERS_DELETE: "Eliminar clientes (solo sin saldo pendiente)",
    Permission.CUSTOMERS_CREDIT: "Anotar cargos (fiado) y abonos",
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
        description="Consulta usuarios y roles; administra el catálogo y los clientes.",
        permissions=(
            Permission.USERS_READ.value,
            Permission.ROLES_READ.value,
            Permission.PRODUCTS_READ.value,
            Permission.PRODUCTS_CREATE.value,
            Permission.PRODUCTS_UPDATE.value,
            Permission.CUSTOMERS_READ.value,
            Permission.CUSTOMERS_CREATE.value,
            Permission.CUSTOMERS_UPDATE.value,
            Permission.CUSTOMERS_CREDIT.value,
        ),
    ),
    SystemRole(
        key="viewer",
        name="Consulta",
        description="Usuario estándar sin permisos de administración (rol por defecto). "
        "Puede ver el catálogo y cobrar/anotar fiado (pensado para un cajero).",
        permissions=(
            Permission.PRODUCTS_READ.value,
            Permission.CUSTOMERS_READ.value,
            Permission.CUSTOMERS_CREDIT.value,
        ),
    ),
)
