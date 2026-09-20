"""Administración de roles y permisos."""

from __future__ import (
    annotations,
)  # el método `list` no debe ocultar al `list[...]` de las anotaciones

from src.database import DuplicateError, Repositories
from src.models import ADMIN_ROLE, PERMISSION_DESCRIPTIONS, Permission, RoleDocument
from src.services.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from src.services.event_logger import EventLogger

_VALID_PERMISSIONS = {permission.value for permission in Permission}


class RoleService:
    def __init__(self, repositories: Repositories, events: EventLogger) -> None:
        self._events = events
        self._roles = repositories.roles
        self._users = repositories.users

    @staticmethod
    def list_permissions() -> list[tuple[str, str]]:
        """Catálogo de permisos disponibles: `(clave, descripción)`."""
        return [(p.value, PERMISSION_DESCRIPTIONS[p]) for p in Permission]

    async def list(self) -> list[RoleDocument]:
        return await self._roles.list()

    async def get(self, key: str) -> RoleDocument:
        role = await self._roles.get(key)
        if role is None:
            raise NotFoundError("Rol no encontrado.", code="role_not_found")
        return role

    async def create(
        self, *, key: str, name: str, description: str, permissions: list[str]
    ) -> RoleDocument:
        self._validate_permissions(permissions)
        role = RoleDocument(
            id=key, name=name, description=description, permissions=sorted(set(permissions))
        )
        try:
            created = await self._roles.create(role)
            self._events.info(
                "roles",
                "roles.created",
                "Rol creado",
                role_key=key,
                permissions=created.permissions,
            )
            return created
        except DuplicateError as error:
            raise ConflictError("Ya existe un rol con esa clave.", code="role_exists") from error

    async def update(
        self,
        key: str,
        *,
        name: str | None,
        description: str | None,
        permissions: list[str] | None,
    ) -> RoleDocument:
        role = await self.get(key)
        changes: dict = {}
        if name is not None:
            changes["name"] = name
        if description is not None:
            changes["description"] = description
        if permissions is not None:
            if key == ADMIN_ROLE:
                raise PermissionDeniedError(
                    "Los permisos del administrador no se pueden modificar.",
                    code="admin_role_locked",
                )
            self._validate_permissions(permissions)
            changes["permissions"] = sorted(set(permissions))
        updated = await self._roles.update(key, changes) if changes else role
        if changes:
            self._events.warning(
                "roles",
                "roles.updated",
                "Rol modificado",
                role_key=key,
                changed=sorted(changes),
                permissions=changes.get("permissions"),
            )
        return updated or role

    async def delete(self, key: str) -> None:
        role = await self.get(key)
        if role.is_system:
            raise PermissionDeniedError(
                "Los roles de sistema no se pueden eliminar.", code="system_role"
            )
        if await self._users.count(role=key) > 0:
            raise ConflictError(
                "El rol tiene usuarios asignados; reasígnalos antes de eliminarlo.",
                code="role_in_use",
            )
        await self._roles.delete(key)
        self._events.warning("roles", "roles.deleted", "Rol eliminado", role_key=key)

    @staticmethod
    def _validate_permissions(permissions: list[str]) -> None:
        unknown = sorted(set(permissions) - _VALID_PERMISSIONS)
        if unknown:
            raise ValidationFailedError(
                f"Permisos desconocidos: {', '.join(unknown)}", code="invalid_permission"
            )
