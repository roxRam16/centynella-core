"""Endpoints de roles y permisos."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from src.dtos import PermissionDTO, ProblemDetailsDTO, RoleCreateRequest, RoleDTO, RoleUpdateRequest
from src.models import Permission
from src.routes.dependencies import CurrentUser, ServicesDep, require_permission

router = APIRouter(tags=["Roles"])

_E401 = {"model": ProblemDetailsDTO, "description": "No autenticado."}
_E403 = {"model": ProblemDetailsDTO, "description": "Sin permiso para esta acción."}
_E404 = {"model": ProblemDetailsDTO, "description": "Rol no encontrado."}
_E409 = {"model": ProblemDetailsDTO, "description": "Conflicto con una regla de negocio."}
_CAN_READ = [Depends(require_permission(Permission.ROLES_READ))]
_CAN_MANAGE = Annotated[CurrentUser, Depends(require_permission(Permission.ROLES_MANAGE))]


@router.get(
    "/permissions",
    response_model=list[PermissionDTO],
    summary="Catálogo de permisos",
    description="Todos los permisos que se pueden asignar a un rol. Requiere `roles:read`.",
    dependencies=_CAN_READ,
    responses={401: _E401, 403: _E403},
)
async def list_permissions(services: ServicesDep) -> list[PermissionDTO]:
    return [PermissionDTO(key=k, description=d) for k, d in services.roles.list_permissions()]


@router.get(
    "/roles",
    response_model=list[RoleDTO],
    summary="Listar roles",
    dependencies=_CAN_READ,
    responses={401: _E401, 403: _E403},
)
async def list_roles(services: ServicesDep) -> list[RoleDTO]:
    return [RoleDTO.from_document(r) for r in await services.roles.list()]


@router.get(
    "/roles/{key}",
    response_model=RoleDTO,
    summary="Ver un rol",
    dependencies=_CAN_READ,
    responses={401: _E401, 403: _E403, 404: _E404},
)
async def get_role(key: str, services: ServicesDep) -> RoleDTO:
    return RoleDTO.from_document(await services.roles.get(key))


@router.post(
    "/roles",
    response_model=RoleDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un rol",
    description="Requiere `roles:manage`.",
    responses={401: _E401, 403: _E403, 409: _E409},
)
async def create_role(
    body: RoleCreateRequest, response: Response, services: ServicesDep, _: _CAN_MANAGE
) -> RoleDTO:
    role = await services.roles.create(
        key=body.key, name=body.name, description=body.description, permissions=body.permissions
    )
    response.headers["Location"] = f"/api/v1/roles/{role.key}"
    return RoleDTO.from_document(role)


@router.patch(
    "/roles/{key}",
    response_model=RoleDTO,
    summary="Editar un rol",
    description="Nombre, descripción o permisos. Los permisos de `admin` no se pueden cambiar. "
    "Requiere `roles:manage`.",
    responses={401: _E401, 403: _E403, 404: _E404},
)
async def update_role(
    key: str, body: RoleUpdateRequest, services: ServicesDep, _: _CAN_MANAGE
) -> RoleDTO:
    role = await services.roles.update(
        key, name=body.name, description=body.description, permissions=body.permissions
    )
    return RoleDTO.from_document(role)


@router.delete(
    "/roles/{key}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar un rol",
    description="No se pueden eliminar roles de sistema ni roles con usuarios asignados. "
    "Requiere `roles:manage`.",
    responses={401: _E401, 403: _E403, 404: _E404, 409: _E409},
)
async def delete_role(key: str, services: ServicesDep, _: _CAN_MANAGE) -> None:
    await services.roles.delete(key)
