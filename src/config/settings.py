"""Configuración de la aplicación.

Patrón: *Settings* tipadas y validadas (pydantic-settings) + *Singleton* vía
``lru_cache``. Las variables se leen del entorno y, si existe, de
``private/.env.<APP_ENV>`` (sandbox | production). Las variables reales del
sistema siempre tienen prioridad sobre el archivo (útil en contenedores/AWS).
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import field_validator
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

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Permite `CORS_ORIGINS=http://a,http://b` además de una lista JSON."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


def resolve_env_file(app_env: str | None = None) -> Path:
    """Ruta de `private/.env.<ambiente>` (puede no existir; entonces se usan defaults)."""
    return PRIVATE_DIR / f".env.{app_env or os.getenv('APP_ENV', 'sandbox')}"


@lru_cache
def get_settings() -> Settings:
    """Devuelve la configuración única de la aplicación (cacheada)."""
    return Settings(_env_file=resolve_env_file())  # type: ignore[call-arg]
