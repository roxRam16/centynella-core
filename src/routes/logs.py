"""Consulta de la bitácora del sistema (solo lectura)."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.dtos import LogEntryDTO, LogPageDTO, ProblemDetailsDTO
from src.models import LogLevel, Permission
from src.routes.dependencies import ServicesDep, require_permission

router = APIRouter(
    prefix="/logs", tags=["Logs"], dependencies=[Depends(require_permission(Permission.LOGS_READ))]
)

_E401 = {"model": ProblemDetailsDTO, "description": "No autenticado."}
_E403 = {"model": ProblemDetailsDTO, "description": "Requiere el permiso `logs:read`."}

_Short = Query(max_length=100)


@router.get(
    "",
    response_model=LogPageDTO,
    summary="Consultar la bitácora",
    description="Eventos del sistema, más recientes primero. Se filtran por **módulo**, **nivel** "
    "(ese nivel o superior), **usuario**, **sesión**, **petición**, servicio, rango de fechas y "
    "texto del mensaje. Las consultas a este endpoint no se registran en la bitácora. "
    "Requiere `logs:read`.",
    responses={401: _E401, 403: _E403},
)
async def search_logs(
    services: ServicesDep,
    module: Annotated[str | None, _Short] = None,
    level: Annotated[LogLevel | None, Query(description="Nivel mínimo.")] = None,
    event: Annotated[str | None, _Short] = None,
    service: Annotated[str | None, _Short] = None,
    user_id: Annotated[str | None, _Short] = None,
    session_id: Annotated[str | None, _Short] = None,
    request_id: Annotated[str | None, _Short] = None,
    since: Annotated[datetime | None, Query(description="Desde (ISO 8601, UTC).")] = None,
    until: Annotated[datetime | None, Query(description="Hasta (ISO 8601, UTC).")] = None,
    q: Annotated[str | None, Query(max_length=100, description="Texto del mensaje.")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> LogPageDTO:
    entries, total = await services.logs.search(
        module=module,
        min_level=level,
        event=event,
        service=service,
        user_id=user_id,
        session_id=session_id,
        request_id=request_id,
        since=since,
        until=until,
        text=q,
        page=page,
        page_size=page_size,
    )
    return LogPageDTO(
        items=[LogEntryDTO.from_entry(entry) for entry in entries],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/modules",
    response_model=list[str],
    summary="Módulos con eventos",
    description="Módulos que han registrado eventos (para armar filtros). Requiere `logs:read`.",
    responses={401: _E401, 403: _E403},
)
async def list_log_modules(services: ServicesDep) -> list[str]:
    return await services.logs.modules()


__all__ = ["LogEntryDTO", "router"]
