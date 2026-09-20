"""DTOs de la bitácora."""

from datetime import datetime
from typing import Any, Self

from pydantic import BaseModel, Field

from src.models import LogEntry


class LogEntryDTO(BaseModel):
    id: str
    timestamp: datetime
    level: str
    service: str = Field(description="Servicio que emitió el evento (core, …).")
    module: str = Field(description="Área funcional: auth, users, roles, database, http, system…")
    event: str = Field(description="Código estable, ej. `auth.login.success`.")
    message: str
    environment: str
    request_id: str | None = Field(default=None, description="Enlaza todo lo de una petición.")
    user_id: str | None = None
    session_id: str | None = Field(default=None, description="Sesión del usuario (refresh token).")
    ip: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_entry(cls, entry: LogEntry) -> Self:
        return cls(**entry.model_dump(exclude={"id"}), id=entry.id)


class LogPageDTO(BaseModel):
    items: list[LogEntryDTO]
    total: int = Field(description="Total de eventos que cumplen los filtros.")
    page: int
    page_size: int
