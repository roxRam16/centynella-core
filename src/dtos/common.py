"""Tipos reutilizables de validación para los DTOs.

Toda entrada de texto pasa por aquí ANTES de llegar a la lógica de negocio. Reglas:
  · Los tipos son estrictos (Pydantic rechaza objetos donde se espera texto: un JSON como
    `{"$ne": ""}` en lugar de un correo NO pasa → no hay inyección NoSQL por operadores).
  · Nombres y textos libres rechazan `<`, `>` y caracteres de control (no hay HTML/scripts
    guardados). La interfaz además escapa todo al mostrarlo (React no interpreta HTML).
  · Las contraseñas se guardan solo como hash y nunca se muestran, por eso pueden llevar
    cualquier símbolo; sí se exigen mayúscula, minúscula, número y símbolo.
"""

import re
import unicodedata
from typing import Annotated

from pydantic import AfterValidator, EmailStr, Field, StringConstraints

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_STRICT_EMAIL = re.compile(r"^[a-z0-9._%+-]{1,64}@[a-z0-9-]+(\.[a-z0-9-]+)+$")


def _check_password_strength(value: str) -> str:
    """Política: mayúscula, minúscula, número y símbolo; sin espacios ni caracteres de control."""
    missing = []
    if not re.search(r"[A-Z]", value):
        missing.append("una mayúscula")
    if not re.search(r"[a-z]", value):
        missing.append("una minúscula")
    if not re.search(r"\d", value):
        missing.append("un número")
    if not re.search(r"[^A-Za-z0-9\s]", value):
        missing.append("un símbolo (ej. ! @ # $ %)")
    if missing:
        raise ValueError("La contraseña debe incluir " + ", ".join(missing))
    if re.search(r"\s", value) or _CONTROL_CHARS.search(value):
        raise ValueError("La contraseña no puede contener espacios ni caracteres de control")
    return value


def _strict_email(value: str) -> str:
    """Correo en minúsculas y con un patrón conservador (sin comillas, `<`, `>` ni espacios).

    Es más estricto que el RFC a propósito: descarta direcciones exóticas (`"a b"@x.com`,
    `o'brien@x.com`) que casi nunca son reales y sí sirven para colar caracteres peligrosos.
    """
    email = value.strip().lower()
    if len(email) > 254 or not _STRICT_EMAIL.match(email):
        raise ValueError("El correo contiene caracteres no permitidos")
    return email


def _check_person_name(value: str) -> str:
    """Solo letras (cualquier idioma), espacios, apóstrofes, puntos y guiones."""
    if not (value[0].isalpha()):
        raise ValueError("El nombre debe empezar con una letra")
    for char in value:
        if not (char.isalpha() or unicodedata.category(char).startswith("M") or char in " '.-"):
            raise ValueError("El nombre solo admite letras, espacios, apóstrofes, puntos y guiones")
    return value


def _check_safe_text(value: str) -> str:
    """Texto libre sin marcado HTML ni caracteres de control."""
    if "<" in value or ">" in value or _CONTROL_CHARS.search(value):
        raise ValueError("El texto no puede contener < > ni caracteres de control")
    return value


# Contraseña nueva (registro, cambio, recuperación). Máximo 128 para acotar el costo del hash.
Password = Annotated[
    str,
    Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH),
    AfterValidator(_check_password_strength),
]

# Correo válido (RFC + patrón estricto) y normalizado a minúsculas.
EmailAddress = Annotated[EmailStr, AfterValidator(_strict_email)]

# Correo tal como lo teclea el usuario al entrar: solo se normaliza (se usa para BUSCAR, no se
# guarda). Sigue siendo `str` estricto, así que un objeto JSON se rechaza.
LoginIdentifier = Annotated[
    str, StringConstraints(strip_whitespace=True, to_lower=True, min_length=3, max_length=254)
]

PersonName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=2, max_length=80),
    AfterValidator(_check_person_name),
]

# Clave de rol: minúsculas, números, guion y guion bajo (también al referenciarla desde un usuario).
RoleKey = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_-]{1,31}$")]

# Texto libre corto (nombre/descripcion de un rol…): sin HTML ni caracteres de control.
SafeText = Annotated[
    str, StringConstraints(strip_whitespace=True), AfterValidator(_check_safe_text)
]
