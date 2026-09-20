"""Manejo centralizado de errores en formato Problem Details (RFC 9457)."""

import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.dtos import ProblemDetailsDTO
from src.services.errors import DomainError

logger = logging.getLogger(__name__)

PROBLEM_MEDIA_TYPE = "application/problem+json"


def problem_response(
    request: Request,
    status_code: int,
    detail: str | None = None,
    errors: list[dict] | None = None,
    code: str | None = None,
) -> JSONResponse:
    """Construye la respuesta de error estándar."""
    problem = ProblemDetailsDTO(
        title=HTTPStatus(status_code).phrase,
        status=status_code,
        detail=detail,
        code=code,
        instance=request.url.path,
        request_id=getattr(request.state, "request_id", None),
        errors=errors,
    )
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(problem, exclude_none=True),
        media_type=PROBLEM_MEDIA_TYPE,
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """404, 405, etc. y cualquier `HTTPException` lanzada por la app."""
    response = problem_response(request, exc.status_code, str(exc.detail))
    if exc.headers:
        response.headers.update(exc.headers)
    return response


async def domain_exception_handler(request: Request, exc: DomainError) -> JSONResponse:
    """Errores de negocio (401, 403, 404, 409, 429…) con su `code` estable."""
    response = problem_response(request, exc.status_code, exc.detail, code=exc.code)
    if exc.headers:
        response.headers.update(exc.headers)
    return response


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """422: el cuerpo, la query o el path no cumplen el contrato."""
    return problem_response(
        request,
        HTTPStatus.UNPROCESSABLE_ENTITY,
        detail="La petición no cumple el contrato de la API.",
        errors=jsonable_encoder(exc.errors(), exclude={"ctx", "input"}),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """500: error inesperado. Se registra completo pero NO se filtra al cliente."""
    logger.exception("Error no controlado en %s %s", request.method, request.url.path)
    return problem_response(
        request,
        HTTPStatus.INTERNAL_SERVER_ERROR,
        detail="Ocurrió un error interno. Cita el request_id al reportarlo.",
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Registra todos los handlers en la aplicación."""
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(DomainError, domain_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)
