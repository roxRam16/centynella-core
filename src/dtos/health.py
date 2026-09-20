"""DTOs de los endpoints de salud."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class HealthDTO(BaseModel):
    """Liveness: el proceso está vivo."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "ok",
                "service": "CENTYNELLA-CORE",
                "version": "0.1.0",
                "timestamp": "2026-09-19T12:00:00Z",
            }
        }
    )

    status: Literal["ok"] = Field(description="Siempre `ok` si el proceso responde.")
    service: str = Field(description="Nombre del servicio.")
    version: str = Field(description="Versión desplegada.")
    timestamp: datetime = Field(description="Hora del servidor (UTC).")


class ReadinessDTO(BaseModel):
    """Readiness: el servicio y sus dependencias pueden atender tráfico."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "ready",
                "service": "CENTYNELLA-CORE",
                "version": "0.1.0",
                "timestamp": "2026-09-19T12:00:00Z",
                "dependencies": {"mongodb": "up"},
            }
        }
    )

    status: Literal["ready", "degraded"] = Field(
        description="`ready` si todas las dependencias responden; `degraded` si alguna falla."
    )
    service: str
    version: str
    timestamp: datetime
    dependencies: dict[str, Literal["up", "down"]] = Field(
        description="Estado de cada dependencia externa."
    )
