"""DTOs de clientes y fiado (crédito informal)."""

from datetime import datetime
from typing import Self

from pydantic import BaseModel, Field, model_validator

from src.dtos.common import EmailAddress, Phone, SafeText
from src.models import CreditMovementDocument, CreditMovementType, CustomerDocument


class CustomerDTO(BaseModel):
    id: str
    name: str
    phone: str | None = None
    email: str | None = None
    address: str
    notes: str
    credit_limit: float
    balance: float
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_document(cls, customer: CustomerDocument) -> Self:
        return cls(
            id=customer.id or "",
            name=customer.name,
            phone=customer.phone,
            email=customer.email,
            address=customer.address,
            notes=customer.notes,
            credit_limit=customer.credit_limit,
            balance=customer.balance,
            created_at=customer.created_at,
            updated_at=customer.updated_at,
        )


class CustomerCreateRequest(BaseModel):
    name: SafeText = Field(min_length=2, max_length=120)
    phone: Phone | None = None
    email: EmailAddress | None = None
    address: SafeText = Field(default="", max_length=200)
    notes: SafeText = Field(default="", max_length=500)
    credit_limit: float = Field(default=0.0, ge=0, le=1_000_000)


class CustomerUpdateRequest(BaseModel):
    """Actualización parcial (PATCH): solo se cambian los campos enviados. El saldo NO se
    edita aquí: se mueve con `POST /customers/{id}/credit-movements`."""

    name: SafeText | None = Field(default=None, min_length=2, max_length=120)
    phone: Phone | None = None
    email: EmailAddress | None = None
    address: SafeText | None = Field(default=None, max_length=200)
    notes: SafeText | None = Field(default=None, max_length=500)
    credit_limit: float | None = Field(default=None, ge=0, le=1_000_000)

    @model_validator(mode="after")
    def _at_least_one_field(self) -> Self:
        if not self.model_dump(exclude_none=True):
            raise ValueError("Envía al menos un campo para actualizar")
        return self


class CustomerPageDTO(BaseModel):
    """Página de resultados del listado de clientes."""

    items: list[CustomerDTO]
    total: int = Field(description="Total de clientes que cumplen los filtros.")
    page: int
    page_size: int


class CreditMovementDTO(BaseModel):
    id: str
    customer_id: str
    type: CreditMovementType
    amount: float
    note: str
    created_by: str | None = None
    created_at: datetime

    @classmethod
    def from_document(cls, movement: CreditMovementDocument) -> Self:
        return cls(
            id=movement.id or "",
            customer_id=movement.customer_id,
            type=movement.type,
            amount=movement.amount,
            note=movement.note,
            created_by=movement.created_by,
            created_at=movement.created_at,
        )


class CreditMovementCreateRequest(BaseModel):
    type: CreditMovementType
    amount: float = Field(gt=0, le=1_000_000, description="Siempre positivo.")
    note: SafeText = Field(default="", max_length=200)


class CreditMovementPageDTO(BaseModel):
    items: list[CreditMovementDTO]
    total: int
    page: int
    page_size: int
