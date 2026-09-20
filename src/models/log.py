"""Modelo de la bitácora (colección `logs` de la base de datos de logs).

La bitácora vive en una base de datos SEPARADA de la de negocio (`MONGODB_LOGS_DB`): así su
volumen, su retención y sus permisos se gestionan aparte, y una falla o un exceso de logs
nunca afecta a los datos de los usuarios.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.models.base import new_id, utc_now

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

# Orden de severidad: sirve para filtrar "este nivel o superior".
LEVEL_ORDER: dict[str, int] = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}


def levels_at_or_above(level: str) -> list[str]:
    """`WARNING` → ['WARNING', 'ERROR', 'CRITICAL']."""
    threshold = LEVEL_ORDER[level]
    return [name for name, value in LEVEL_ORDER.items() if value >= threshold]


class LogEntry(BaseModel):
    """Un evento del sistema.

    Se puede consultar por MÓDULO (`auth`, `users`, `database`…), por SERVICIO (`core`, y
    los microservicios futuros), por USUARIO (`user_id`) y por SESIÓN (`session_id`, la misma
    del refresh token) — y todo lo de una petición se enlaza con `request_id`.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=new_id, alias="_id")
    timestamp: datetime = Field(default_factory=utc_now)
    level: LogLevel
    service: str = Field(description="Servicio que emite el evento (core, …).")
    module: str = Field(description="Área funcional: auth, users, roles, database, http, system…")
    event: str = Field(description="Código estable del evento, ej. `auth.login.success`.")
    message: str
    environment: str
    request_id: str | None = None
    user_id: str | None = None
    session_id: str | None = None
    ip: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
