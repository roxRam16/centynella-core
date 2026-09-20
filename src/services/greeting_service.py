"""Servicio del saludo "Hola Mundo" (prueba de humo del stack completo)."""

from src.config import Settings
from src.dtos import GreetingDTO


class GreetingService:
    """Construye el saludo de la API."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def get_greeting(self) -> GreetingDTO:
        return GreetingDTO(
            message="¡Hola Mundo!",
            service=self._settings.app_name,
            environment=self._settings.app_env,
        )
