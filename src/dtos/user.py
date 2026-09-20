"""DTOs de usuarios y perfil."""

from datetime import datetime
from typing import Self

from pydantic import BaseModel, Field, model_validator

from src.dtos.common import EmailAddress, Password, PersonName
from src.models import UserDocument, UserStatus


class UserDTO(BaseModel):
    """Usuario tal como lo ve la API. Nunca incluye el hash de la contraseña."""

    id: str
    name: str
    email: str
    role: str = Field(description="Clave del rol (ver `/api/v1/roles`).")
    status: UserStatus
    providers: list[str] = Field(description="Métodos de acceso: `password`, `google`.")
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None = None

    @classmethod
    def from_document(cls, user: UserDocument) -> Self:
        return cls(
            id=user.id or "",
            name=user.name,
            email=user.email,
            role=user.role,
            status=user.status,
            providers=[link.provider for link in user.providers],
            created_at=user.created_at,
            updated_at=user.updated_at,
            last_login_at=user.last_login_at,
        )


class ProfileDTO(UserDTO):
    """Usuario autenticado, con sus permisos efectivos (para mostrar/ocultar opciones en la UI)."""

    permissions: list[str]

    @classmethod
    def from_user(cls, user: UserDocument, permissions: list[str]) -> Self:
        return cls(**UserDTO.from_document(user).model_dump(), permissions=permissions)


class UserCreateRequest(BaseModel):
    name: PersonName
    email: EmailAddress
    password: Password
    role: str = Field(description="Clave de un rol existente.")
    status: UserStatus = "active"


class UserUpdateRequest(BaseModel):
    """Actualización parcial (PATCH): solo se cambian los campos enviados."""

    name: PersonName | None = None
    role: str | None = None
    status: UserStatus | None = None

    @model_validator(mode="after")
    def _at_least_one_field(self) -> Self:
        if self.name is None and self.role is None and self.status is None:
            raise ValueError("Envía al menos un campo para actualizar")
        return self


class ProfileUpdateRequest(BaseModel):
    name: PersonName


class UserPageDTO(BaseModel):
    """Página de resultados del listado de usuarios."""

    items: list[UserDTO]
    total: int = Field(description="Total de usuarios que cumplen los filtros.")
    page: int
    page_size: int
