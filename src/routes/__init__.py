"""Enrutado de la API.

Estándar RESTful:
  · Versionado en la URL: `/api/v1/...` (un cambio incompatible crea `/api/v2`).
  · Recursos en sustantivos y plural cuando son colecciones (`/users`, `/roles`), verbos HTTP
    para las acciones (GET/POST/PUT/PATCH/DELETE) y códigos de estado correctos
    (200, 201 + Location, 202, 204, 400/401/403/404/409/422/429).
  · Errores en `application/problem+json` (RFC 9457) con un `code` estable.
"""

from fastapi import APIRouter, status

from src.dtos import ProblemDetailsDTO
from src.routes import auth, greeting, health, logs, roles, users

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
api_v1_router.include_router(auth.router)
api_v1_router.include_router(users.router)
api_v1_router.include_router(roles.router)
api_v1_router.include_router(logs.router)
api_v1_router.include_router(greeting.router)

health_router = health.router

__all__ = ["api_v1_router", "health_router"]
