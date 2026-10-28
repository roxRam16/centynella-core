"""Proveedores: directorio simple (alta, edición, baja y búsqueda)."""

from __future__ import annotations

from src.database import Repositories
from src.models import SupplierDocument
from src.services.errors import NotFoundError
from src.services.event_logger import EventLogger


class SupplierService:
    def __init__(self, repositories: Repositories, events: EventLogger) -> None:
        self._events = events
        self._suppliers = repositories.suppliers

    async def get(self, supplier_id: str) -> SupplierDocument:
        supplier = await self._suppliers.get(supplier_id)
        if supplier is None:
            raise NotFoundError("Proveedor no encontrado.", code="supplier_not_found")
        return supplier

    async def list(
        self, *, query: str | None, page: int, page_size: int
    ) -> tuple[list[SupplierDocument], int]:
        return await self._suppliers.list(query=query, page=page, page_size=page_size)

    async def create(
        self,
        *,
        name: str,
        phone: str | None,
        email: str | None,
        address: str,
        notes: str,
        products_supplied: str,
    ) -> SupplierDocument:
        supplier = SupplierDocument(
            name=name,
            phone=phone,
            email=email,
            address=address,
            notes=notes,
            products_supplied=products_supplied,
        )
        created = await self._suppliers.create(supplier)
        self._events.info(
            "suppliers", "suppliers.created", "Proveedor creado", target_supplier_id=created.id
        )
        return created

    async def update(
        self,
        supplier_id: str,
        *,
        name: str | None,
        phone: str | None,
        email: str | None,
        address: str | None,
        notes: str | None,
        products_supplied: str | None,
    ) -> SupplierDocument:
        await self.get(supplier_id)  # 404 temprano si no existe
        changes: dict = {}
        for field, value in (
            ("name", name),
            ("phone", phone),
            ("email", email),
            ("address", address),
            ("notes", notes),
            ("products_supplied", products_supplied),
        ):
            if value is not None:
                changes[field] = value

        updated = (
            await self._suppliers.update(supplier_id, changes)
            if changes
            else await self.get(supplier_id)
        )
        if updated is None:
            raise NotFoundError("Proveedor no encontrado.", code="supplier_not_found")
        if changes:
            self._events.info(
                "suppliers",
                "suppliers.updated",
                "Proveedor modificado",
                target_supplier_id=supplier_id,
                changed=sorted(changes),
            )
        return updated

    async def delete(self, supplier_id: str) -> None:
        await self.get(supplier_id)  # 404 temprano si no existe
        await self._suppliers.delete(supplier_id)
        self._events.warning(
            "suppliers",
            "suppliers.deleted",
            "Proveedor eliminado",
            target_supplier_id=supplier_id,
        )
