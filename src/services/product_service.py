"""Catálogo de productos: alta, edición, baja y consulta con existencia."""

from src.database import DuplicateError, Repositories
from src.models import ProductDocument, ProductStatus
from src.services.errors import ConflictError, NotFoundError
from src.services.event_logger import EventLogger


class ProductService:
    def __init__(self, repositories: Repositories, events: EventLogger) -> None:
        self._events = events
        self._products = repositories.products

    async def get(self, product_id: str) -> ProductDocument:
        product = await self._products.get(product_id)
        if product is None:
            raise NotFoundError("Producto no encontrado.", code="product_not_found")
        return product

    async def list(
        self,
        *,
        query: str | None,
        category: str | None,
        status: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[ProductDocument], int]:
        return await self._products.list(
            query=query, category=category, status=status, page=page, page_size=page_size
        )

    async def create(
        self,
        *,
        sku: str,
        name: str,
        category: str,
        unit: str,
        price: float,
        quantity: int,
        low_stock_threshold: int,
        status: ProductStatus,
    ) -> ProductDocument:
        product = ProductDocument(
            sku=sku,
            name=name,
            category=category,
            unit=unit,
            price=price,
            quantity=quantity,
            low_stock_threshold=low_stock_threshold,
            status=status,
        )
        try:
            created = await self._products.create(product)
        except DuplicateError as error:
            raise ConflictError("Ya existe un producto con ese SKU.", code="sku_taken") from error
        self._events.info(
            "products", "products.created", "Producto creado", target_product_id=created.id, sku=sku
        )
        return created

    async def update(
        self,
        product_id: str,
        *,
        name: str | None,
        category: str | None,
        unit: str | None,
        price: float | None,
        quantity: int | None,
        low_stock_threshold: int | None,
        status: ProductStatus | None,
    ) -> ProductDocument:
        await self.get(product_id)  # 404 temprano si no existe
        changes: dict = {}
        for field, value in (
            ("name", name),
            ("category", category),
            ("unit", unit),
            ("price", price),
            ("quantity", quantity),
            ("low_stock_threshold", low_stock_threshold),
            ("status", status),
        ):
            if value is not None:
                changes[field] = value

        updated = (
            await self._products.update(product_id, changes)
            if changes
            else await self.get(product_id)
        )
        if updated is None:
            raise NotFoundError("Producto no encontrado.", code="product_not_found")
        if changes:
            self._events.info(
                "products",
                "products.updated",
                "Producto modificado",
                target_product_id=product_id,
                changed=sorted(changes),
            )
        return updated

    async def delete(self, product_id: str) -> None:
        await self.get(product_id)
        await self._products.delete(product_id)
        self._events.warning(
            "products", "products.deleted", "Producto eliminado", target_product_id=product_id
        )
