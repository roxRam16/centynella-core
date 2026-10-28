"""Modelo de proveedor: directorio simple (sin órdenes de compra todavía)."""

from src.models.base import BaseDocument


class SupplierDocument(BaseDocument):
    """Colección `suppliers`."""

    name: str
    phone: str | None = None
    email: str | None = None
    address: str = ""
    notes: str = ""
    products_supplied: str = ""
