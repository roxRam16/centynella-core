"""Endpoints del catálogo de productos."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status

from src.dtos import (
    ProblemDetailsDTO,
    ProductCreateRequest,
    ProductDTO,
    ProductPageDTO,
    ProductUpdateRequest,
)
from src.models import Permission, ProductStatus
from src.routes.dependencies import CurrentUser, ServicesDep, require_permission

router = APIRouter(prefix="/products", tags=["Products"])

_E400 = {"model": ProblemDetailsDTO, "description": "Imagen inválida."}
_E401 = {"model": ProblemDetailsDTO, "description": "No autenticado."}
_E403 = {"model": ProblemDetailsDTO, "description": "Sin permiso para esta acción."}
_E404 = {"model": ProblemDetailsDTO, "description": "Producto no encontrado."}
_E409 = {"model": ProblemDetailsDTO, "description": "Conflicto con una regla de negocio."}


@router.get(
    "",
    response_model=ProductPageDTO,
    summary="Listar productos",
    description="Paginado, con búsqueda por nombre o SKU y filtros por categoría y estado. "
    "Requiere `products:read`.",
    dependencies=[Depends(require_permission(Permission.PRODUCTS_READ))],
    responses={401: _E401, 403: _E403},
)
async def list_products(
    services: ServicesDep,
    q: Annotated[str | None, Query(max_length=100, description="Busca en nombre y SKU.")] = None,
    category: Annotated[str | None, Query(max_length=60)] = None,
    status_: Annotated[ProductStatus | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ProductPageDTO:
    products, total = await services.products.list(
        query=q, category=category, status=status_, page=page, page_size=page_size
    )
    return ProductPageDTO(
        items=[ProductDTO.from_document(p) for p in products],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "",
    response_model=ProductDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un producto",
    description="Da de alta un producto en el catálogo. Requiere `products:create`.",
    responses={401: _E401, 403: _E403, 409: _E409},
)
async def create_product(
    body: ProductCreateRequest,
    response: Response,
    services: ServicesDep,
    _: Annotated[CurrentUser, Depends(require_permission(Permission.PRODUCTS_CREATE))],
) -> ProductDTO:
    product = await services.products.create(
        sku=body.sku,
        name=body.name,
        category=body.category,
        unit=body.unit,
        price=body.price,
        quantity=body.quantity,
        low_stock_threshold=body.low_stock_threshold,
        status=body.status,
        barcode=body.barcode,
        brand=body.brand,
        description=body.description,
        cost=body.cost,
    )
    response.headers["Location"] = f"/api/v1/products/{product.id}"
    return ProductDTO.from_document(product)


@router.get(
    "/{product_id}",
    response_model=ProductDTO,
    summary="Ver un producto",
    dependencies=[Depends(require_permission(Permission.PRODUCTS_READ))],
    responses={401: _E401, 403: _E403, 404: _E404},
)
async def get_product(product_id: str, services: ServicesDep) -> ProductDTO:
    return ProductDTO.from_document(await services.products.get(product_id))


@router.patch(
    "/{product_id}",
    response_model=ProductDTO,
    summary="Editar un producto",
    description="Nombre, categoría, unidad, precio, existencia, umbral de alerta o estado. "
    "Requiere `products:update`.",
    responses={401: _E401, 403: _E403, 404: _E404},
)
async def update_product(
    product_id: str,
    body: ProductUpdateRequest,
    services: ServicesDep,
    _: Annotated[CurrentUser, Depends(require_permission(Permission.PRODUCTS_UPDATE))],
) -> ProductDTO:
    product = await services.products.update(
        product_id,
        name=body.name,
        category=body.category,
        unit=body.unit,
        price=body.price,
        quantity=body.quantity,
        low_stock_threshold=body.low_stock_threshold,
        status=body.status,
        barcode=body.barcode,
        brand=body.brand,
        description=body.description,
        cost=body.cost,
    )
    return ProductDTO.from_document(product)


@router.post(
    "/{product_id}/image",
    response_model=ProductDTO,
    summary="Subir la foto de un producto",
    description="JPG, PNG o WEBP. Reemplaza la foto anterior si había. Requiere `products:update`.",
    responses={400: _E400, 401: _E401, 403: _E403, 404: _E404},
)
async def upload_product_image(
    product_id: str,
    services: ServicesDep,
    _: Annotated[CurrentUser, Depends(require_permission(Permission.PRODUCTS_UPDATE))],
    file: Annotated[UploadFile, File(description="Imagen JPG, PNG o WEBP.")],
) -> ProductDTO:
    content = await file.read()
    product = await services.products.set_image(product_id, content)
    return ProductDTO.from_document(product)


@router.delete(
    "/{product_id}/image",
    response_model=ProductDTO,
    summary="Quitar la foto de un producto",
    description="Requiere `products:update`.",
    responses={401: _E401, 403: _E403, 404: _E404},
)
async def delete_product_image(
    product_id: str,
    services: ServicesDep,
    _: Annotated[CurrentUser, Depends(require_permission(Permission.PRODUCTS_UPDATE))],
) -> ProductDTO:
    product = await services.products.remove_image(product_id)
    return ProductDTO.from_document(product)


@router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar un producto",
    description="Requiere `products:delete`.",
    responses={401: _E401, 403: _E403, 404: _E404},
)
async def delete_product(
    product_id: str,
    services: ServicesDep,
    _: Annotated[CurrentUser, Depends(require_permission(Permission.PRODUCTS_DELETE))],
) -> None:
    await services.products.delete(product_id)
