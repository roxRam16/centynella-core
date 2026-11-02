"""Catálogo de productos: alta, edición, baja y consulta con existencia."""

from src.database import DuplicateError, Repositories
from src.models import ProductDocument, ProductStatus
from src.services.errors import ConflictError, NotFoundError
from src.services.event_logger import EventLogger
from src.services.image_storage import ProductImageStorage


class ProductService:
    def __init__(
        self,
        repositories: Repositories,
        events: EventLogger,
        images: ProductImageStorage,
    ) -> None:
        self._events = events
        self._products = repositories.products
        self._images = images

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
        barcode: str | None,
        brand: str,
        description: str,
        cost: float,
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
            barcode=barcode,
            brand=brand,
            description=description,
            cost=cost,
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
        barcode: str | None,
        brand: str | None,
        description: str | None,
        cost: float | None,
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
            ("barcode", barcode),
            ("brand", brand),
            ("description", description),
            ("cost", cost),
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
        self._images.delete(product_id)
        self._events.warning(
            "products", "products.deleted", "Producto eliminado", target_product_id=product_id
        )

    async def set_image(self, product_id: str, content: bytes) -> ProductDocument:
        """Valida y guarda la foto del producto (JPG/PNG/WEBP); reemplaza la anterior si había."""
        await self.get(product_id)  # 404 temprano si no existe
        relative_path = self._images.save(product_id, content)
        updated = await self._products.update(product_id, {"image_path": relative_path})
        if updated is None:
            raise NotFoundError("Producto no encontrado.", code="product_not_found")
        self._events.info(
            "products",
            "products.image_set",
            "Foto del producto actualizada",
            target_product_id=product_id,
        )
        return updated

    async def remove_image(self, product_id: str) -> ProductDocument:
        await self.get(product_id)  # 404 temprano si no existe
        self._images.delete(product_id)
        updated = await self._products.update(product_id, {"image_path": None})
        if updated is None:
            raise NotFoundError("Producto no encontrado.", code="product_not_found")
        self._events.info(
            "products",
            "products.image_removed",
            "Foto del producto eliminada",
            target_product_id=product_id,
        )
        return updated
