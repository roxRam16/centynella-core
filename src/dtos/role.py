"""DTOs de roles y permisos."""

from typing import Self

from pydantic import BaseModel, Field, model_validator

from src.dtos.common import RoleKey
from src.models import RoleDocument


class RoleDTO(BaseModel):
    key: str
    name: str
    description: str
    permissions: list[str]
    is_system: bool = Field(description="Los roles de sistema no se pueden eliminar.")

    @classmethod
    def from_document(cls, role: RoleDocument) -> Self:
        return cls(
            key=role.key,
            name=role.name,
            description=role.description,
            permissions=role.permissions,
            is_system=role.is_system,
        )


class RoleCreateRequest(BaseModel):
    key: RoleKey = Field(description="Identificador estable: minúsculas, números, `-` y `_`.")
    name: str = Field(min_length=2, max_length=60)
    description: str = Field(default="", max_length=200)
    permissions: list[str] = Field(default_factory=list)


class RoleUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=60)
    description: str | None = Field(default=None, max_length=200)
    permissions: list[str] | None = None

    @model_validator(mode="after")
    def _at_least_one_field(self) -> Self:
        if self.name is None and self.description is None and self.permissions is None:
            raise ValueError("Envía al menos un campo para actualizar")
        return self


class PermissionDTO(BaseModel):
    key: str = Field(description="Formato `recurso:acción`.")
    description: str
