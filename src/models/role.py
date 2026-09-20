"""Modelo de rol."""

from src.models.base import BaseDocument


class RoleDocument(BaseDocument):
    """Colección `roles`. El `_id` ES la clave del rol (ej. `admin`): clave natural, sin joins.

    Los roles `is_system` no pueden eliminarse; los de sistema se sincronizan al arrancar.
    """

    name: str
    description: str = ""
    permissions: list[str] = []
    is_system: bool = False

    @property
    def key(self) -> str:
        return self.id or ""
