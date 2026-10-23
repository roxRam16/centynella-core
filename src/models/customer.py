"""Modelo de cliente y de sus movimientos de fiado (crédito informal)."""

from typing import Literal

from src.models.base import BaseDocument

CreditMovementType = Literal["charge", "payment"]


class CustomerDocument(BaseDocument):
    """Colección `customers`.

    `balance` es una CACHÉ (patrón de referencia extendida): se recalcula con cada
    `CreditMovementDocument` para no sumar el historial completo en cada lectura. La fuente
    de verdad es la colección de movimientos, que nunca se edita ni se borra (es auditable).
    """

    name: str
    phone: str | None = None
    email: str | None = None
    address: str = ""
    notes: str = ""
    credit_limit: float = 0.0
    balance: float = 0.0


class CreditMovementDocument(BaseDocument):
    """Colección `credit_movements`. `charge` = se le anota una venta; `payment` = abona."""

    customer_id: str
    type: CreditMovementType
    amount: float
    note: str = ""
    created_by: str | None = None
