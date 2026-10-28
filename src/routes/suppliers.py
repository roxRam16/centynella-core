"""Endpoints de proveedores (directorio simple)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from src.dtos import (
    ProblemDetailsDTO,
    SupplierCreateRequest,
    SupplierDTO,
    SupplierPageDTO,
    SupplierUpdateRequest,
)
from src.models import Permission
from src.routes.dependencies import CurrentUser, ServicesDep, require_permission

router = APIRouter(prefix="/suppliers", tags=["Suppliers"])

_E401 = {"model": ProblemDetailsDTO, "description": "No autenticado."}
_E403 = {"model": ProblemDetailsDTO, "description": "Sin permiso para esta acción."}
_E404 = {"model": ProblemDetailsDTO, "description": "Proveedor no encontrado."}


@router.get(
    "",
    response_model=SupplierPageDTO,
    summary="Listar proveedores",
    description="Paginado, con búsqueda por nombre, teléfono o lo que surte. Requiere "
    "`suppliers:read`.",
    dependencies=[Depends(require_permission(Permission.SUPPLIERS_READ))],
    responses={401: _E401, 403: _E403},
)
async def list_suppliers(
    services: ServicesDep,
    q: Annotated[
        str | None, Query(max_length=100, description="Busca en nombre, teléfono y lo que surte.")
    ] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> SupplierPageDTO:
    suppliers, total = await services.suppliers.list(query=q, page=page, page_size=page_size)
    return SupplierPageDTO(
        items=[SupplierDTO.from_document(s) for s in suppliers],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "",
    response_model=SupplierDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un proveedor",
    description="Requiere `suppliers:create`.",
    responses={401: _E401, 403: _E403},
)
async def create_supplier(
    body: SupplierCreateRequest,
    response: Response,
    services: ServicesDep,
    _: Annotated[CurrentUser, Depends(require_permission(Permission.SUPPLIERS_CREATE))],
) -> SupplierDTO:
    supplier = await services.suppliers.create(
        name=body.name,
        phone=body.phone,
        email=body.email,
        address=body.address,
        notes=body.notes,
        products_supplied=body.products_supplied,
    )
    response.headers["Location"] = f"/api/v1/suppliers/{supplier.id}"
    return SupplierDTO.from_document(supplier)


@router.get(
    "/{supplier_id}",
    response_model=SupplierDTO,
    summary="Ver un proveedor",
    dependencies=[Depends(require_permission(Permission.SUPPLIERS_READ))],
    responses={401: _E401, 403: _E403, 404: _E404},
)
async def get_supplier(supplier_id: str, services: ServicesDep) -> SupplierDTO:
    return SupplierDTO.from_document(await services.suppliers.get(supplier_id))


@router.patch(
    "/{supplier_id}",
    response_model=SupplierDTO,
    summary="Editar un proveedor",
    description="Requiere `suppliers:update`.",
    responses={401: _E401, 403: _E403, 404: _E404},
)
async def update_supplier(
    supplier_id: str,
    body: SupplierUpdateRequest,
    services: ServicesDep,
    _: Annotated[CurrentUser, Depends(require_permission(Permission.SUPPLIERS_UPDATE))],
) -> SupplierDTO:
    supplier = await services.suppliers.update(
        supplier_id,
        name=body.name,
        phone=body.phone,
        email=body.email,
        address=body.address,
        notes=body.notes,
        products_supplied=body.products_supplied,
    )
    return SupplierDTO.from_document(supplier)


@router.delete(
    "/{supplier_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar un proveedor",
    description="Requiere `suppliers:delete`.",
    responses={401: _E401, 403: _E403, 404: _E404},
)
async def delete_supplier(
    supplier_id: str,
    services: ServicesDep,
    _: Annotated[CurrentUser, Depends(require_permission(Permission.SUPPLIERS_DELETE))],
) -> None:
    await services.suppliers.delete(supplier_id)
