"""Tipos reutilizables de validación para los DTOs."""

import re
from typing import Annotated

from pydantic import AfterValidator, EmailStr, Field, StringConstraints

MIN_PASSWORD_LENGTH = 8


def _check_password_strength(value: str) -> str:
    """Política de contraseña: 8+ caracteres, al menos una letra y un número."""
    if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
        raise ValueError("La contraseña debe incluir al menos una letra y un número")
    return value


def _lowercase(value: str) -> str:
    return value.strip().lower()


# Contraseña nueva (registro, cambio, recuperación). Máximo 128 para acotar el costo del hash.
Password = Annotated[
    str,
    Field(min_length=MIN_PASSWORD_LENGTH, max_length=128),
    AfterValidator(_check_password_strength),
]

# Correo válido y normalizado a minúsculas (el correo es único sin distinguir mayúsculas).
EmailAddress = Annotated[EmailStr, AfterValidator(_lowercase)]

# Correo tal como lo teclea el usuario al entrar: no se valida el formato, solo se normaliza.
LoginIdentifier = Annotated[
    str, StringConstraints(strip_whitespace=True, to_lower=True, min_length=3, max_length=254)
]

PersonName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80)]

# Clave de rol: minúsculas, números, guion y guion bajo.
RoleKey = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_-]{1,31}$")]
