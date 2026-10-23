"""Clientes y fiado (crédito informal): alta, edición, baja y movimientos de cuenta."""

# `from __future__ import annotations`: diferir las anotaciones a texto. Sin esto, el método
# `list` de esta clase se cuela como nombre local y rompe `list[...]` en las anotaciones que
# vienen después de él en el mismo cuerpo de clase (ej. en `list_movements`).
from __future__ import annotations

from src.database import Repositories
from src.models import CreditMovementDocument, CreditMovementType, CustomerDocument
from src.services.errors import ConflictError, NotFoundError
from src.services.event_logger import EventLogger


class CustomerService:
    def __init__(self, repositories: Repositories, events: EventLogger) -> None:
        self._events = events
        self._customers = repositories.customers
        self._movements = repositories.credit_movements

    async def get(self, customer_id: str) -> CustomerDocument:
        customer = await self._customers.get(customer_id)
        if customer is None:
            raise NotFoundError("Cliente no encontrado.", code="customer_not_found")
        return customer

    async def list(
        self, *, query: str | None, page: int, page_size: int
    ) -> tuple[list[CustomerDocument], int]:
        return await self._customers.list(query=query, page=page, page_size=page_size)

    async def create(
        self,
        *,
        name: str,
        phone: str | None,
        email: str | None,
        address: str,
        notes: str,
        credit_limit: float,
    ) -> CustomerDocument:
        customer = CustomerDocument(
            name=name,
            phone=phone,
            email=email,
            address=address,
            notes=notes,
            credit_limit=credit_limit,
        )
        created = await self._customers.create(customer)
        self._events.info(
            "customers", "customers.created", "Cliente creado", target_customer_id=created.id
        )
        return created

    async def update(
        self,
        customer_id: str,
        *,
        name: str | None,
        phone: str | None,
        email: str | None,
        address: str | None,
        notes: str | None,
        credit_limit: float | None,
    ) -> CustomerDocument:
        await self.get(customer_id)  # 404 temprano si no existe
        changes: dict = {}
        for field, value in (
            ("name", name),
            ("phone", phone),
            ("email", email),
            ("address", address),
            ("notes", notes),
            ("credit_limit", credit_limit),
        ):
            if value is not None:
                changes[field] = value

        updated = (
            await self._customers.update(customer_id, changes)
            if changes
            else await self.get(customer_id)
        )
        if updated is None:
            raise NotFoundError("Cliente no encontrado.", code="customer_not_found")
        if changes:
            self._events.info(
                "customers",
                "customers.updated",
                "Cliente modificado",
                target_customer_id=customer_id,
                changed=sorted(changes),
            )
        return updated

    async def delete(self, customer_id: str) -> None:
        customer = await self.get(customer_id)
        if customer.balance != 0:
            raise ConflictError(
                "No puedes eliminar un cliente con saldo pendiente de fiado.",
                code="customer_has_balance",
            )
        await self._customers.delete(customer_id)
        self._events.warning(
            "customers", "customers.deleted", "Cliente eliminado", target_customer_id=customer_id
        )

    async def record_movement(
        self,
        customer_id: str,
        *,
        type: CreditMovementType,  # noqa: A002 - nombre del campo del dominio, no built-in
        amount: float,
        note: str,
        actor_id: str | None,
    ) -> tuple[CustomerDocument, CreditMovementDocument]:
        """Anota un cargo (venta a crédito) o un abono. Un abono nunca deja el saldo en negativo."""
        customer = await self.get(customer_id)
        if type == "payment" and amount > customer.balance:
            raise ConflictError(
                "El abono no puede ser mayor que el saldo pendiente.",
                code="payment_exceeds_balance",
            )

        delta = amount if type == "charge" else -amount
        updated = await self._customers.adjust_balance(customer_id, delta)
        if updated is None:
            raise NotFoundError("Cliente no encontrado.", code="customer_not_found")

        movement = await self._movements.create(
            CreditMovementDocument(
                customer_id=customer_id, type=type, amount=amount, note=note, created_by=actor_id
            )
        )
        event = "customers.credit.charged" if type == "charge" else "customers.credit.paid"
        self._events.info(
            "customers",
            event,
            "Fiado anotado" if type == "charge" else "Abono registrado",
            target_customer_id=customer_id,
            amount=amount,
            new_balance=updated.balance,
        )
        if type == "charge" and updated.balance > updated.credit_limit > 0:
            self._events.warning(
                "customers",
                "customers.credit.over_limit",
                "Cliente superó su límite de crédito",
                target_customer_id=customer_id,
                balance=updated.balance,
                credit_limit=updated.credit_limit,
            )
        return updated, movement

    async def list_movements(
        self, customer_id: str, *, page: int, page_size: int
    ) -> tuple[list[CreditMovementDocument], int]:
        await self.get(customer_id)  # 404 si el cliente no existe
        return await self._movements.list_for_customer(customer_id, page=page, page_size=page_size)
