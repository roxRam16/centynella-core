"""Endpoints de ventas (punto de venta)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from src.dtos import ProblemDetailsDTO, SaleCreateRequest, SaleDTO, SalePageDTO
from src.models import Permission
from src.routes.dependencies import CurrentUser, ServicesDep, require_permission

router = APIRouter(prefix="/sales", tags=["Sales"])

_E400 = {"model": ProblemDetailsDTO, "description": "Datos de la venta inválidos."}
_E401 = {"model": ProblemDetailsDTO, "description": "No autenticado."}
_E403 = {"model": ProblemDetailsDTO, "description": "Sin permiso para esta acción."}
_E404 = {"model": ProblemDetailsDTO, "description": "Venta no encontrada."}
_E409 = {"model": ProblemDetailsDTO, "description": "Conflicto con una regla de negocio."}


@router.get(
    "",
    response_model=SalePageDTO,
    summary="Listar ventas",
    description="Paginado; filtra por cliente. Requiere `sales:read`.",
    dependencies=[Depends(require_permission(Permission.SALES_READ))],
    responses={401: _E401, 403: _E403},
)
async def list_sales(
    services: ServicesDep,
    customer_id: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> SalePageDTO:
    sales, total = await services.sales.list(
        customer_id=customer_id, page=page, page_size=page_size
    )
    return SalePageDTO(
        items=[SaleDTO.from_document(s) for s in sales],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "",
    response_model=SaleDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar una venta",
    description="Cobra un carrito: descuenta existencia y, si `payment_method` es "
    '"store_credit", anota el cargo en el fiado del cliente. Requiere `sales:create`.',
    responses={400: _E400, 401: _E401, 403: _E403, 409: _E409},
)
async def create_sale(
    body: SaleCreateRequest,
    response: Response,
    services: ServicesDep,
    current: Annotated[CurrentUser, Depends(require_permission(Permission.SALES_CREATE))],
) -> SaleDTO:
    sale = await services.sales.create(
        customer_id=body.customer_id,
        items=[(line.product_id, line.quantity) for line in body.items],
        payment_method=body.payment_method,
        amount_tendered=body.amount_tendered,
        note=body.note,
        created_by=current.id,
    )
    response.headers["Location"] = f"/api/v1/sales/{sale.id}"
    return SaleDTO.from_document(sale)


@router.get(
    "/{sale_id}",
    response_model=SaleDTO,
    summary="Ver una venta",
    dependencies=[Depends(require_permission(Permission.SALES_READ))],
    responses={401: _E401, 403: _E403, 404: _E404},
)
async def get_sale(sale_id: str, services: ServicesDep) -> SaleDTO:
    return SaleDTO.from_document(await services.sales.get(sale_id))
