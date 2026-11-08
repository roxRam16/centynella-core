"""Ventas (punto de venta): cobra un carrito, descuenta existencia y, si se cobró a crédito,
anota el cargo en el fiado del cliente (ver `CustomerService.record_movement`)."""

# `from __future__ import annotations`: diferir las anotaciones a texto. Sin esto, el método
# `list` de esta clase se cuela como nombre local y rompe `list[...]` en las anotaciones que
# vienen después de él en el mismo cuerpo de clase (ej. en `create`).
from __future__ import annotations

from src.database import Repositories
from src.models import ProductDocument, SaleDocument, SaleItem, SalePaymentMethod
from src.services.customer_service import CustomerService
from src.services.errors import BadRequestError, ConflictError, NotFoundError
from src.services.event_logger import EventLogger
from src.services.product_service import ProductService


class SaleService:
    def __init__(
        self,
        repositories: Repositories,
        events: EventLogger,
        products: ProductService,
        customers: CustomerService,
    ) -> None:
        self._events = events
        self._sales = repositories.sales
        self._products = products
        self._customers = customers

    async def get(self, sale_id: str) -> SaleDocument:
        sale = await self._sales.get(sale_id)
        if sale is None:
            raise NotFoundError("Venta no encontrada.", code="sale_not_found")
        return sale

    async def list(
        self, *, customer_id: str | None, page: int, page_size: int
    ) -> tuple[list[SaleDocument], int]:
        return await self._sales.list(customer_id=customer_id, page=page, page_size=page_size)

    async def create(
        self,
        *,
        customer_id: str | None,
        items: list[tuple[str, int]],  # (product_id, quantity)
        payment_method: SalePaymentMethod,
        amount_tendered: float | None,
        note: str,
        created_by: str | None,
    ) -> SaleDocument:
        if payment_method == "store_credit" and not customer_id:
            raise BadRequestError(
                "Una venta a crédito necesita un cliente.", code="customer_required"
            )

        # 1.º pase (sin tocar nada): valida que haya existencia suficiente de TODO antes de
        # descontar una sola unidad — una venta no se hace a medias.
        resolved: list[tuple[ProductDocument, int]] = []
        for product_id, quantity in items:
            product = await self._products.get(product_id)
            if product.quantity < quantity:
                raise ConflictError(
                    f'No hay suficiente existencia de "{product.name}" '
                    f"(quedan {product.quantity}, se pidieron {quantity}).",
                    code="insufficient_stock",
                )
            resolved.append((product, quantity))

        # 2.º pase: descuenta existencia y registra la venta. Si algo falla a medio camino
        # (efectivo insuficiente, una carrera rarísima de existencia), revierte lo ya descontado.
        decremented: list[tuple[str, int]] = []
        try:
            for product, quantity in resolved:
                await self._products.decrement_stock(product.id or "", quantity)
                decremented.append((product.id or "", quantity))

            sale_items = [
                SaleItem(
                    product_id=product.id or "",
                    sku=product.sku,
                    name=product.name,
                    unit=product.unit,
                    quantity=quantity,
                    unit_price=product.price,
                    subtotal=round(product.price * quantity, 2),
                )
                for product, quantity in resolved
            ]
            total = round(sum(item.subtotal for item in sale_items), 2)

            change_due = None
            if payment_method == "cash":
                if amount_tendered is None or amount_tendered < total:
                    raise BadRequestError(
                        "El efectivo recibido no cubre el total.", code="insufficient_cash"
                    )
                change_due = round(amount_tendered - total, 2)

            sale = await self._sales.create(
                SaleDocument(
                    customer_id=customer_id,
                    items=sale_items,
                    payment_method=payment_method,
                    total=total,
                    amount_tendered=amount_tendered if payment_method == "cash" else None,
                    change_due=change_due,
                    note=note,
                    created_by=created_by,
                )
            )
        except Exception:
            for product_id, quantity in decremented:
                await self._products.decrement_stock(product_id, -quantity)
            raise

        if payment_method == "store_credit" and customer_id:
            await self._customers.record_movement(
                customer_id,
                type="charge",
                amount=sale.total,
                note=f"Venta {sale.id}",
                actor_id=created_by,
            )

        self._events.info(
            "sales",
            "sales.created",
            "Venta registrada",
            target_sale_id=sale.id,
            total=sale.total,
            payment_method=payment_method,
        )
        return sale
