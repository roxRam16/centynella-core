"""Enrutado de la API.

Estándar RESTful:
  · Versionado en la URL: `/api/v1/...` (un cambio incompatible crea `/api/v2`).
  · Recursos en sustantivos y plural cuando son colecciones (`/products`), verbos HTTP
    para las acciones (GET/POST/PUT/PATCH/DELETE) y códigos de estado correctos
    (200, 201 + Location, 204, 400/404/409/422).
  · Errores en `application/problem+json` (RFC 9457).
"""

from fastapi import APIRouter, status

from src.dtos import ProblemDetailsDTO
from src.routes import greeting, health

# Respuestas de error comunes documentadas en Swagger para todos los endpoints de negocio.
_COMMON_ERRORS = {
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "model": ProblemDetailsDTO,
        "description": "Validation Error",
    },
    status.HTTP_500_INTERNAL_SERVER_ERROR: {
        "model": ProblemDetailsDTO,
        "description": "Internal Server Error",
    },
}

api_v1_router = APIRouter(prefix="/api/v1", responses=_COMMON_ERRORS)
api_v1_router.include_router(greeting.router)

health_router = health.router

__all__ = ["api_v1_router", "health_router"]
