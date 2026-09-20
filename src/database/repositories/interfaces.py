"""Contratos de los repositorios (patrón Repository).

Los servicios dependen de estos `Protocol`, no de MongoDB: así se pueden probar con
implementaciones en memoria (tests/fakes.py) y el almacenamiento es intercambiable.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from src.models import (
    LogEntry,
    PasswordResetDocument,
    RefreshTokenDocument,
    RoleDocument,
    UserDocument,
)


class UserRepository(Protocol):
    async def create(self, user: UserDocument) -> UserDocument:
        """Inserta. Lanza `DuplicateError('email')` si el correo ya existe."""

    async def get(self, user_id: str) -> UserDocument | None: ...

    async def get_by_email(self, email: str) -> UserDocument | None: ...

    async def update(self, user_id: str, changes: dict[str, Any]) -> UserDocument | None:
        """Aplica `changes` (y `updated_at`). `None` si no existe."""

    async def delete(self, user_id: str) -> bool: ...

    async def list(
        self, *, query: str | None, role: str | None, status: str | None, page: int, page_size: int
    ) -> tuple[list[UserDocument], int]:
        """Página de usuarios (más recientes primero) y total que cumple los filtros."""

    async def count(self, *, role: str | None = None, status: str | None = None) -> int: ...


class RoleRepository(Protocol):
    async def create(self, role: RoleDocument) -> RoleDocument:
        """Inserta. Lanza `DuplicateError('key')` si la clave ya existe."""

    async def get(self, key: str) -> RoleDocument | None: ...

    async def list(self) -> list[RoleDocument]: ...

    async def update(self, key: str, changes: dict[str, Any]) -> RoleDocument | None: ...

    async def delete(self, key: str) -> bool: ...


class RefreshTokenRepository(Protocol):
    async def create(self, token: RefreshTokenDocument) -> RefreshTokenDocument: ...

    async def get_by_hash(self, token_hash: str) -> RefreshTokenDocument | None: ...

    async def rotate(self, token_id: str) -> None:
        """Revoca el token porque fue sustituido por uno nuevo (marca `rotated_at`)."""

    async def revoke_family(self, family_id: str) -> None: ...

    async def revoke_all_for_user(self, user_id: str) -> None: ...


class PasswordResetRepository(Protocol):
    async def create(self, reset: PasswordResetDocument) -> PasswordResetDocument: ...

    async def get_by_hash(self, token_hash: str) -> PasswordResetDocument | None: ...

    async def mark_used(self, reset_id: str) -> None: ...

    async def invalidate_for_user(self, user_id: str) -> None:
        """Marca como usadas las solicitudes pendientes del usuario."""


@dataclass
class LogQuery:
    """Filtros de búsqueda de la bitácora. Todos son opcionales y se combinan con AND."""

    module: str | None = None
    levels: list[str] | None = None
    event: str | None = None
    service: str | None = None
    user_id: str | None = None
    session_id: str | None = None
    request_id: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    text: str | None = None


class LogRepository(Protocol):
    """Bitácora (base de datos de logs, separada de la de negocio)."""

    async def insert_many(self, entries: list[LogEntry]) -> None: ...

    async def search(
        self, query: LogQuery, *, page: int, page_size: int
    ) -> tuple[list[LogEntry], int]:
        """Página de eventos (más recientes primero) y total que cumple los filtros."""

    async def modules(self) -> list[str]:
        """Módulos que han registrado eventos (para el filtro de la interfaz)."""
