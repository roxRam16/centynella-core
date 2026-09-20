"""Lógica de negocio de los chequeos de salud."""

from src.config import Settings
from src.database import DatabaseManager
from src.dtos import HealthDTO, ReadinessDTO
from src.models import utc_now


class HealthService:
    """Reporta liveness (proceso vivo) y readiness (dependencias listas)."""

    def __init__(self, settings: Settings, database: DatabaseManager) -> None:
        self._settings = settings
        self._database = database

    def liveness(self) -> HealthDTO:
        """El proceso está vivo. No consulta dependencias (debe ser instantáneo)."""
        return HealthDTO(
            status="ok",
            service=self._settings.app_name,
            version=self._settings.app_version,
            timestamp=utc_now(),
        )

    async def readiness(self) -> ReadinessDTO:
        """Verifica cada dependencia externa; `degraded` si alguna no responde."""
        mongodb_up = await self._database.ping()
        return ReadinessDTO(
            status="ready" if mongodb_up else "degraded",
            service=self._settings.app_name,
            version=self._settings.app_version,
            timestamp=utc_now(),
            dependencies={"mongodb": "up" if mongodb_up else "down"},
        )
