"""Endpoints de clientes y fiado (crédito informal)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from src.dtos import (
    CreditMovementCreateRequest,
    CreditMovementDTO,
    CreditMovementPageDTO,
    CustomerCreateRequest,
    CustomerDTO,
    CustomerPageDTO,
    CustomerUpdateRequest,
    ProblemDetailsDTO,
)
from src.models import Permission
from src.routes.dependencies import CurrentUser, ServicesDep, require_permission

router = APIRouter(prefix="/customers", tags=["Customers"])

_E401 = {"model": ProblemDetailsDTO, "description": "No autenticado."}
_E403 = {"model": ProblemDetailsDTO, "description": "Sin permiso para esta acción."}
_E404 = {"model": ProblemDetailsDTO, "description": "Cliente no encontrado."}
_E409 = {"model": ProblemDetailsDTO, "description": "Conflicto con una regla de negocio."}


@router.get(
    "",
    response_model=CustomerPageDTO,
    summary="Listar clientes",
    description="Paginado, con búsqueda por nombre o teléfono. Requiere `customers:read`.",
    dependencies=[Depends(require_permission(Permission.CUSTOMERS_READ))],
    responses={401: _E401, 403: _E403},
)
async def list_customers(
    services: ServicesDep,
    q: Annotated[
        str | None, Query(max_length=100, description="Busca en nombre y teléfono.")
    ] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> CustomerPageDTO:
    customers, total = await services.customers.list(query=q, page=page, page_size=page_size)
    return CustomerPageDTO(
        items=[CustomerDTO.from_document(c) for c in customers],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "",
    response_model=CustomerDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un cliente",
    description="Requiere `customers:create`.",
    responses={401: _E401, 403: _E403},
)
async def create_customer(
    body: CustomerCreateRequest,
    response: Response,
    services: ServicesDep,
    _: Annotated[CurrentUser, Depends(require_permission(Permission.CUSTOMERS_CREATE))],
) -> CustomerDTO:
    customer = await services.customers.create(
        name=body.name,
        phone=body.phone,
        email=body.email,
        address=body.address,
        notes=body.notes,
        credit_limit=body.credit_limit,
    )
    response.headers["Location"] = f"/api/v1/customers/{customer.id}"
    return CustomerDTO.from_document(customer)


@router.get(
    "/{customer_id}",
    response_model=CustomerDTO,
    summary="Ver un cliente",
    dependencies=[Depends(require_permission(Permission.CUSTOMERS_READ))],
    responses={401: _E401, 403: _E403, 404: _E404},
)
async def get_customer(customer_id: str, services: ServicesDep) -> CustomerDTO:
    return CustomerDTO.from_document(await services.customers.get(customer_id))


@router.patch(
    "/{customer_id}",
    response_model=CustomerDTO,
    summary="Editar un cliente",
    description="Nombre, contacto o límite de crédito. El saldo se mueve con los movimientos "
    "de fiado, no aquí. Requiere `customers:update`.",
    responses={401: _E401, 403: _E403, 404: _E404},
)
async def update_customer(
    customer_id: str,
    body: CustomerUpdateRequest,
    services: ServicesDep,
    _: Annotated[CurrentUser, Depends(require_permission(Permission.CUSTOMERS_UPDATE))],
) -> CustomerDTO:
    customer = await services.customers.update(
        customer_id,
        name=body.name,
        phone=body.phone,
        email=body.email,
        address=body.address,
        notes=body.notes,
        credit_limit=body.credit_limit,
    )
    return CustomerDTO.from_document(customer)


@router.delete(
    "/{customer_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar un cliente",
    description="Solo si no tiene saldo pendiente de fiado. Requiere `customers:delete`.",
    responses={401: _E401, 403: _E403, 404: _E404, 409: _E409},
)
async def delete_customer(
    customer_id: str,
    services: ServicesDep,
    _: Annotated[CurrentUser, Depends(require_permission(Permission.CUSTOMERS_DELETE))],
) -> None:
    await services.customers.delete(customer_id)


@router.get(
    "/{customer_id}/credit-movements",
    response_model=CreditMovementPageDTO,
    summary="Historial de fiado del cliente",
    dependencies=[Depends(require_permission(Permission.CUSTOMERS_READ))],
    responses={401: _E401, 403: _E403, 404: _E404},
)
async def list_credit_movements(
    customer_id: str,
    services: ServicesDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> CreditMovementPageDTO:
    movements, total = await services.customers.list_movements(
        customer_id, page=page, page_size=page_size
    )
    return CreditMovementPageDTO(
        items=[CreditMovementDTO.from_document(m) for m in movements],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/{customer_id}/credit-movements",
    response_model=CustomerDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Anotar un cargo o un abono",
    description="`charge` = se le anota una venta a crédito; `payment` = abona (no puede ser "
    "mayor que el saldo). Devuelve el cliente con el saldo actualizado. "
    "Requiere `customers:credit`.",
    responses={401: _E401, 403: _E403, 404: _E404, 409: _E409},
)
async def create_credit_movement(
    customer_id: str,
    body: CreditMovementCreateRequest,
    services: ServicesDep,
    current: Annotated[CurrentUser, Depends(require_permission(Permission.CUSTOMERS_CREDIT))],
) -> CustomerDTO:
    customer, _movement = await services.customers.record_movement(
        customer_id,
        type=body.type,
        amount=body.amount,
        note=body.note,
        actor_id=current.id,
    )
    return CustomerDTO.from_document(customer)
