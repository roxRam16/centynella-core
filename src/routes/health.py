"""Endpoints de salud (sondas para balanceador / ECS / Docker).

Van en la raíz (`/health`) y no bajo `/api/v1`: son infraestructura, no parte del
contrato de negocio versionado.
"""

from fastapi import APIRouter, Response, status

from src.dtos import HealthDTO, ReadinessDTO
from src.routes.dependencies import HealthServiceDep

router = APIRouter(prefix="/health", tags=["Health"])

_NO_STORE = "no-store"


@router.get(
    "",
    response_model=HealthDTO,
    summary="Liveness",
    description="Indica que el proceso está vivo. No consulta dependencias.",
)
async def liveness(response: Response, service: HealthServiceDep) -> HealthDTO:
    response.headers["Cache-Control"] = _NO_STORE
    return service.liveness()


@router.get(
    "/ready",
    response_model=ReadinessDTO,
    summary="Readiness",
    description="Verifica las dependencias (MongoDB). Responde 503 si alguna no está disponible.",
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ReadinessDTO,
            "description": "Alguna dependencia no responde (`status: degraded`).",
        }
    },
)
async def readiness(response: Response, service: HealthServiceDep) -> ReadinessDTO:
    response.headers["Cache-Control"] = _NO_STORE
    result = await service.readiness()
    if result.status != "ready":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result
