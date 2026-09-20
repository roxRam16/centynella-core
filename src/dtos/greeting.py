"""DTO del recurso de saludo (prueba de humo "Hola Mundo")."""

from pydantic import BaseModel, ConfigDict, Field


class GreetingDTO(BaseModel):
    """Saludo devuelto por la API."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "¡Hola Mundo!",
                "service": "CENTYNELLA-CORE",
                "environment": "sandbox",
            }
        }
    )

    message: str = Field(description="Mensaje de saludo.")
    service: str = Field(description="Servicio que responde.")
    environment: str = Field(description="Ambiente activo (sandbox | production).")
