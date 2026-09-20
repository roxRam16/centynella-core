"""Emisión y verificación de tokens.

· Access token: JWT firmado (HS256), de vida corta (por defecto 15 min). Viaja en la
  cabecera `Authorization: Bearer` y el frontend lo guarda SOLO en memoria.
· Refresh token: cadena opaca aleatoria (no JWT). Viaja en una cookie HttpOnly y en la
  base de datos solo se guarda su hash SHA-256.
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import timedelta

import jwt

from src.config import Settings
from src.models import new_id, utc_now
from src.services.errors import AuthenticationError

ACCESS_TOKEN_TYPE = "access"  # noqa: S105 - nombre del tipo de token, no un secreto


@dataclass(frozen=True)
class AccessClaims:
    """Lo que dice un access token válido."""

    user_id: str
    session_id: str | None


class TokenService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def create_access_token(self, user_id: str, session_id: str) -> tuple[str, int]:
        """Devuelve `(jwt, segundos_de_vida)`. `sid` enlaza el token con su sesión (bitácora)."""
        now = utc_now()
        lifetime = timedelta(minutes=self._settings.access_token_ttl_minutes)
        payload = {
            "sub": user_id,
            "sid": session_id,
            "typ": ACCESS_TOKEN_TYPE,
            "jti": new_id(),
            "iat": now,
            "exp": now + lifetime,
        }
        token = jwt.encode(
            payload, self._settings.jwt_secret_key, algorithm=self._settings.jwt_algorithm
        )
        return token, int(lifetime.total_seconds())

    def decode_access_token(self, token: str) -> AccessClaims:
        """Valida firma, expiración y tipo; devuelve el usuario (`sub`) y la sesión (`sid`)."""
        try:
            payload = jwt.decode(
                token,
                self._settings.jwt_secret_key,
                # Lista fija: nunca se acepta el algoritmo que declare el token (ataque `alg`).
                algorithms=[self._settings.jwt_algorithm],
                options={"require": ["sub", "exp", "iat", "typ"]},
            )
        except jwt.ExpiredSignatureError as error:
            raise AuthenticationError("La sesión expiró.", code="token_expired") from error
        except jwt.PyJWTError as error:
            raise AuthenticationError("Token inválido.", code="invalid_token") from error

        if payload["typ"] != ACCESS_TOKEN_TYPE:
            raise AuthenticationError("Token inválido.", code="invalid_token")
        sid = payload.get("sid")
        return AccessClaims(str(payload["sub"]), str(sid) if sid else None)

    @staticmethod
    def generate_opaque_token() -> tuple[str, str]:
        """Devuelve `(token_en_claro, hash)`. El claro se entrega al usuario; el hash se guarda."""
        raw = secrets.token_urlsafe(48)
        return raw, TokenService.hash_token(raw)

    @staticmethod
    def hash_token(raw: str) -> str:
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
