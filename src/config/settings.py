"""Configuración de la aplicación.

Patrón: *Settings* tipadas y validadas (pydantic-settings) + *Singleton* vía
``lru_cache``. Las variables se leen del entorno y, si existe, de
``private/.env.<APP_ENV>`` (sandbox | production). Las variables reales del
sistema siempre tienen prioridad sobre el archivo (útil en contenedores/AWS).
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PRIVATE_DIR = PROJECT_ROOT / "private"

AppEnvironment = Literal["sandbox", "production"]


class Settings(BaseSettings):
    """Variables de entorno de CENTYNELLA-CORE."""

    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    app_name: str = "CENTYNELLA-CORE"
    app_env: AppEnvironment = "sandbox"
    app_version: str = "0.1.0"

    # Swagger / ReDoc. Desactivable por ambiente si se requiere.
    docs_enabled: bool = True

    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "centynella"
    mongodb_timeout_ms: int = 2000

    # Orígenes permitidos por CORS (el shell del MFE). Separados por coma en el .env.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]

    # ── Autenticación ────────────────────────────────────────────────────────
    # Sin valor por defecto a propósito: la app NO arranca sin un secreto real.
    jwt_secret_key: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = Field(default=15, ge=1)
    refresh_token_ttl_days: int = Field(default=14, ge=1)
    # Ventana en la que reusar un refresh token recién rotado NO se considera robo
    # (dos pestañas del navegador refrescando a la vez).
    refresh_reuse_leeway_seconds: int = Field(default=10, ge=0)
    password_reset_ttl_minutes: int = Field(default=60, ge=5)
    max_failed_logins: int = Field(default=5, ge=1)
    lockout_minutes: int = Field(default=15, ge=1)

    # Registro público de usuarios (siempre con el rol por defecto, sin permisos de administración).
    registration_enabled: bool = True
    default_role: str = "viewer"

    # URL pública del shell: se usa para construir el enlace del correo de recuperación.
    frontend_url: str = "http://localhost:5173"

    # Administrador inicial: se crea al arrancar SOLO si no existe ningún usuario.
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: str | None = None
    bootstrap_admin_name: str = "Administrador"

    # Preparado para "Continuar con Google" (aún sin implementar).
    google_client_id: str | None = None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Permite `CORS_ORIGINS=http://a,http://b` además de una lista JSON."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def _validate_production(self) -> Self:
        """En producción no se admite CORS abierto: la sesión viaja en una cookie."""
        if self.app_env == "production" and "*" in self.cors_origins:
            raise ValueError("CORS_ORIGINS no puede contener '*' en producción")
        return self

    @property
    def explicit_cors_origins(self) -> list[str]:
        """Orígenes concretos. El comodín `*` se descarta: no es compatible con cookies."""
        return [origin for origin in self.cors_origins if origin != "*"]

    @property
    def cookie_secure(self) -> bool:
        """La cookie de sesión solo viaja por HTTPS en producción."""
        return self.app_env == "production"


def resolve_env_file(app_env: str | None = None) -> Path:
    """Ruta de `private/.env.<ambiente>` (puede no existir; entonces se usan defaults)."""
    return PRIVATE_DIR / f".env.{app_env or os.getenv('APP_ENV', 'sandbox')}"


@lru_cache
def get_settings() -> Settings:
    """Devuelve la configuración única de la aplicación (cacheada)."""
    return Settings(_env_file=resolve_env_file())  # type: ignore[call-arg]
