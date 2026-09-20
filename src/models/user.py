"""Modelo de usuario."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from src.models.base import BaseDocument

UserStatus = Literal["active", "disabled"]
ProviderName = Literal["password", "google"]


class AuthProviderLink(BaseModel):
    """Cómo se autentica el usuario. Preparado para Google: `subject` = id de la cuenta Google."""

    provider: ProviderName
    subject: str | None = None


class UserDocument(BaseDocument):
    """Colección `users`.

    `role` es una *referencia* (clave del rol) — los permisos se resuelven desde `roles`,
    así cambiar los permisos de un rol aplica a todos sus usuarios sin migrar datos.
    """

    email: str
    name: str
    # None si el usuario solo entra con un proveedor externo (Google).
    password_hash: str | None = None
    role: str
    status: UserStatus = "active"
    providers: list[AuthProviderLink] = Field(
        default_factory=lambda: [AuthProviderLink(provider="password")]
    )
    failed_login_attempts: int = 0
    locked_until: datetime | None = None
    last_login_at: datetime | None = None
