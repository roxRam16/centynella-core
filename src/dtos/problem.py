"""DTO de errores: Problem Details for HTTP APIs (RFC 9457).

Todos los errores de la API comparten este formato, con `Content-Type: application/problem+json`.
"""

from pydantic import BaseModel, ConfigDict, Field


class ProblemDetailsDTO(BaseModel):
    """Cuerpo estándar de error."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "type": "about:blank",
                "title": "Unauthorized",
                "status": 401,
                "detail": "Correo o contraseña incorrectos.",
                "code": "invalid_credentials",
                "instance": "/api/v1/auth/login",
                "request_id": "0b1c2d3e4f5a",
            }
        }
    )

    type: str = Field(default="about:blank", description="URI que identifica el tipo de problema.")
    title: str = Field(description="Resumen corto y legible (frase HTTP del status).")
    status: int = Field(description="Código de estado HTTP.")
    detail: str | None = Field(default=None, description="Explicación específica de este error.")
    code: str | None = Field(
        default=None, description="Código estable para máquinas (ej. `email_taken`, `last_admin`)."
    )
    instance: str | None = Field(default=None, description="Ruta de la petición que falló.")
    request_id: str | None = Field(
        default=None, description="Id para rastrear la petición en logs."
    )
    errors: list[dict] | None = Field(
        default=None, description="Errores de validación campo por campo (solo en 422)."
    )
