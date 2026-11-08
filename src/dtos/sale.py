"""DTOs de ventas (punto de venta)."""

from datetime import datetime
from typing import Self

from pydantic import BaseModel, Field

from src.dtos.common import SafeText
from src.models import SaleDocument, SaleItem, SalePaymentMethod


class SaleItemDTO(BaseModel):
    product_id: str
    sku: str
    name: str
    unit: str
    quantity: int
    unit_price: float
    subtotal: float

    @classmethod
    def from_item(cls, item: SaleItem) -> Self:
        return cls(
            product_id=item.product_id,
            sku=item.sku,
            name=item.name,
            unit=item.unit,
            quantity=item.quantity,
            unit_price=item.unit_price,
            subtotal=item.subtotal,
        )


class SaleDTO(BaseModel):
    id: str
    customer_id: str | None
    items: list[SaleItemDTO]
    payment_method: SalePaymentMethod
    total: float
    amount_tendered: float | None
    change_due: float | None
    note: str
    created_by: str | None
    created_at: datetime

    @classmethod
    def from_document(cls, sale: SaleDocument) -> Self:
        return cls(
            id=sale.id or "",
            customer_id=sale.customer_id,
            items=[SaleItemDTO.from_item(item) for item in sale.items],
            payment_method=sale.payment_method,
            total=sale.total,
            amount_tendered=sale.amount_tendered,
            change_due=sale.change_due,
            note=sale.note,
            created_by=sale.created_by,
            created_at=sale.created_at,
        )


class SaleLineRequest(BaseModel):
    product_id: SafeText = Field(min_length=1, max_length=64)
    quantity: int = Field(gt=0, le=10_000)


class SaleCreateRequest(BaseModel):
    customer_id: str | None = None
    items: list[SaleLineRequest] = Field(min_length=1, max_length=200)
    payment_method: SalePaymentMethod
    # Solo aplica (y es obligatorio) con `payment_method = "cash"`.
    amount_tendered: float | None = Field(default=None, ge=0, le=10_000_000)
    note: SafeText = Field(default="", max_length=200)


class SalePageDTO(BaseModel):
    items: list[SaleDTO]
    total: int = Field(description="Total de ventas que cumplen los filtros.")
    page: int
    page_size: int
