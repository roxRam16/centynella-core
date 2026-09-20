"""Recurso `greeting` (Hola Mundo) — prueba de humo de la API versionada."""

from fastapi import APIRouter

from src.dtos import GreetingDTO
from src.routes.dependencies import GreetingServiceDep

router = APIRouter(prefix="/greeting", tags=["Greeting"])


@router.get(
    "",
    response_model=GreetingDTO,
    summary="Obtener el saludo",
    description="Devuelve el saludo *Hola Mundo*. Sirve para verificar que la API responde.",
)
async def get_greeting(service: GreetingServiceDep) -> GreetingDTO:
    return service.get_greeting()
