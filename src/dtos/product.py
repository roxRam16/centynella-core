"""DTOs del catálogo de productos."""

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from src.dtos.common import Barcode, SafeText, Sku
from src.models import ProductDocument, ProductStatus


class ProductDTO(BaseModel):
    id: str
    sku: str
    name: str
    category: str
    unit: str
    price: float
    quantity: int
    low_stock_threshold: int
    status: ProductStatus
    barcode: str | None
    brand: str
    description: str
    cost: float
    # Ruta pública servida por el API (`/media/...`); `None` sin foto. El frontend le antepone
    # su `VITE_API_BASE_URL`.
    image_url: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_document(cls, product: ProductDocument) -> Self:
        return cls(
            id=product.id or "",
            sku=product.sku,
            name=product.name,
            category=product.category,
            unit=product.unit,
            price=product.price,
            quantity=product.quantity,
            low_stock_threshold=product.low_stock_threshold,
            status=product.status,
            barcode=product.barcode,
            brand=product.brand,
            description=product.description,
            cost=product.cost,
            image_url=f"/media/{product.image_path}" if product.image_path else None,
            created_at=product.created_at,
            updated_at=product.updated_at,
        )


class ProductCreateRequest(BaseModel):
    sku: Sku
    name: SafeText = Field(min_length=2, max_length=120)
    category: SafeText = Field(default="", max_length=60)
    unit: SafeText = Field(default="pieza", max_length=20)
    price: float = Field(default=0.0, ge=0, le=1_000_000)
    quantity: int = Field(default=0, ge=0, le=1_000_000)
    low_stock_threshold: int = Field(default=5, ge=0, le=1_000_000)
    status: ProductStatus = "active"
    barcode: Barcode | None = None
    brand: SafeText = Field(default="", max_length=60)
    description: SafeText = Field(default="", max_length=500)
    cost: float = Field(default=0.0, ge=0, le=1_000_000)


class ProductUpdateRequest(BaseModel):
    """Actualización parcial (PATCH): solo se cambian los campos enviados."""

    name: SafeText | None = Field(default=None, min_length=2, max_length=120)
    category: SafeText | None = Field(default=None, max_length=60)
    unit: SafeText | None = Field(default=None, max_length=20)
    price: float | None = Field(default=None, ge=0, le=1_000_000)
    quantity: int | None = Field(default=None, ge=0, le=1_000_000)
    low_stock_threshold: int | None = Field(default=None, ge=0, le=1_000_000)
    status: ProductStatus | None = None
    barcode: Barcode | None = None
    brand: SafeText | None = Field(default=None, max_length=60)
    description: SafeText | None = Field(default=None, max_length=500)
    cost: float | None = Field(default=None, ge=0, le=1_000_000)

    @model_validator(mode="after")
    def _at_least_one_field(self) -> Self:
        if not self.model_dump(exclude_none=True):
            raise ValueError("Envía al menos un campo para actualizar")
        return self


class ProductPageDTO(BaseModel):
    """Página de resultados del listado de productos."""

    items: list[ProductDTO]
    total: int = Field(description="Total de productos que cumplen los filtros.")
    page: int
    page_size: int


class ProductBulkRow(BaseModel):
    """Una fila de la carga masiva (plantilla de Excel o cuadrícula tipo Excel).

    Mismas reglas que `ProductCreateRequest` (el frontend valida con el mismo esquema antes de
    mandar el lote). `id` es lo único que la distingue: con `id` es una EDICIÓN de un producto
    existente; sin `id`, un ALTA nueva.
    """

    id: str | None = None
    sku: Sku
    name: SafeText = Field(min_length=2, max_length=120)
    category: SafeText = Field(default="", max_length=60)
    unit: SafeText = Field(default="pieza", max_length=20)
    price: float = Field(default=0.0, ge=0, le=1_000_000)
    quantity: int = Field(default=0, ge=0, le=1_000_000)
    low_stock_threshold: int = Field(default=5, ge=0, le=1_000_000)
    status: ProductStatus = "active"
    barcode: Barcode | None = None
    brand: SafeText = Field(default="", max_length=60)
    description: SafeText = Field(default="", max_length=500)
    cost: float = Field(default=0.0, ge=0, le=1_000_000)


class ProductBulkRequest(BaseModel):
    # Tope generoso pero no infinito: una carga de verdad no necesita más en un solo lote.
    items: list[ProductBulkRow] = Field(min_length=1, max_length=500)


class ProductBulkRowResult(BaseModel):
    """Resultado de UNA fila del lote — "mejor esfuerzo": una fila con error no tumba las demás."""

    row: int = Field(description="Índice de la fila dentro de la petición (empieza en 0).")
    outcome: Literal["created", "updated", "error"]
    product: ProductDTO | None = None
    error: str | None = None
    code: str | None = None


class ProductBulkResponse(BaseModel):
    results: list[ProductBulkRowResult]
    created: int
    updated: int
    failed: int
