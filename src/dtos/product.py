"""DTOs del catálogo de productos."""

from datetime import datetime
from typing import Self

from pydantic import BaseModel, Field, model_validator

from src.dtos.common import SafeText, Sku
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


class ProductUpdateRequest(BaseModel):
    """Actualización parcial (PATCH): solo se cambian los campos enviados."""

    name: SafeText | None = Field(default=None, min_length=2, max_length=120)
    category: SafeText | None = Field(default=None, max_length=60)
    unit: SafeText | None = Field(default=None, max_length=20)
    price: float | None = Field(default=None, ge=0, le=1_000_000)
    quantity: int | None = Field(default=None, ge=0, le=1_000_000)
    low_stock_threshold: int | None = Field(default=None, ge=0, le=1_000_000)
    status: ProductStatus | None = None

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
