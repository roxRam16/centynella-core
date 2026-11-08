"""Modelo de venta (punto de venta): el carrito ya cobrado, como quedó registrado."""

from typing import Literal

from pydantic import BaseModel

from src.models.base import BaseDocument

SalePaymentMethod = Literal["cash", "credit_card", "debit_card", "transfer", "store_credit"]


class SaleItem(BaseModel):
    """Línea de una venta: copia del producto al momento de cobrar (patrón SUBCONJUNTO/snapshot)
    — si el precio o el nombre del producto cambian después, el historial de ventas no se altera."""

    product_id: str
    sku: str
    name: str
    unit: str
    quantity: int
    unit_price: float
    subtotal: float


class SaleDocument(BaseDocument):
    """Colección `sales`. `payment_method = "store_credit"` ata la venta al fiado del cliente
    (ver `CustomerService.record_movement`); las demás formas de pago no tocan `customers`."""

    customer_id: str | None = None
    items: list[SaleItem]
    payment_method: SalePaymentMethod
    total: float
    amount_tendered: float | None = None  # solo "cash": lo que entregó el cliente
    change_due: float | None = None  # solo "cash": el cambio calculado
    note: str = ""
    created_by: str | None = None
