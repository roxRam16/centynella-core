"""Modelo de producto (catálogo e inventario)."""

from typing import Literal

from src.models.base import BaseDocument

ProductStatus = Literal["active", "discontinued"]


class ProductDocument(BaseDocument):
    """Colección `products`.

    Patrón de modelado: SUBCONJUNTO — `quantity` (la existencia) vive embebida en el propio
    producto porque siempre se lee junto con él y el MVP no maneja varios almacenes; el día que
    haya más de una ubicación, se separa en una colección `stock_by_location` referenciando
    `product_id` (REFERENCIA), sin tocar el resto del documento.
    """

    sku: str
    name: str
    category: str = ""
    unit: str = "pieza"
    price: float = 0.0
    quantity: int = 0
    low_stock_threshold: int = 5
    status: ProductStatus = "active"
