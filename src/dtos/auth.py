"""DTOs de autenticación."""

from typing import Literal

from pydantic import BaseModel, Field

from src.dtos.common import EmailAddress, LoginIdentifier, Password, PersonName
from src.dtos.user import ProfileDTO


class RegisterRequest(BaseModel):
    name: PersonName
    email: EmailAddress
    password: Password


class LoginRequest(BaseModel):
    email: LoginIdentifier
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    """Sesión iniciada. El refresh token NO va aquí: viaja en una cookie HttpOnly."""

    access_token: str = Field(description="JWT de vida corta. Enviar en `Authorization: Bearer`.")
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 - tipo de esquema OAuth, no un secreto
    expires_in: int = Field(description="Segundos de vida del access token.")
    user: ProfileDTO


class PasswordResetRequestCreate(BaseModel):
    """Solicitud de recuperación: se envía un enlace al correo (si existe la cuenta)."""

    email: LoginIdentifier


class PasswordResetCreate(BaseModel):
    """Restablece la contraseña con el token recibido por correo."""

    token: str = Field(min_length=20, max_length=200)
    password: Password


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: Password


class GoogleLoginRequest(BaseModel):
    """Preparado para Google: el `id_token` que entrega Google Identity Services."""

    id_token: str = Field(min_length=10)
