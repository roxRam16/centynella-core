"""DTOs de proveedores (directorio simple)."""

from datetime import datetime
from typing import Self

from pydantic import BaseModel, Field, model_validator

from src.dtos.common import EmailAddress, Phone, SafeText
from src.models import SupplierDocument


class SupplierDTO(BaseModel):
    id: str
    name: str
    phone: str | None = None
    email: str | None = None
    address: str
    notes: str
    products_supplied: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_document(cls, supplier: SupplierDocument) -> Self:
        return cls(
            id=supplier.id or "",
            name=supplier.name,
            phone=supplier.phone,
            email=supplier.email,
            address=supplier.address,
            notes=supplier.notes,
            products_supplied=supplier.products_supplied,
            created_at=supplier.created_at,
            updated_at=supplier.updated_at,
        )


class SupplierCreateRequest(BaseModel):
    name: SafeText = Field(min_length=2, max_length=120)
    phone: Phone | None = None
    email: EmailAddress | None = None
    address: SafeText = Field(default="", max_length=200)
    notes: SafeText = Field(default="", max_length=500)
    products_supplied: SafeText = Field(default="", max_length=200)


class SupplierUpdateRequest(BaseModel):
    """Actualización parcial (PATCH): solo se cambian los campos enviados."""

    name: SafeText | None = Field(default=None, min_length=2, max_length=120)
    phone: Phone | None = None
    email: EmailAddress | None = None
    address: SafeText | None = Field(default=None, max_length=200)
    notes: SafeText | None = Field(default=None, max_length=500)
    products_supplied: SafeText | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _at_least_one_field(self) -> Self:
        if not self.model_dump(exclude_none=True):
            raise ValueError("Envía al menos un campo para actualizar")
        return self


class SupplierPageDTO(BaseModel):
    """Página de resultados del listado de proveedores."""

    items: list[SupplierDTO]
    total: int = Field(description="Total de proveedores que cumplen los filtros.")
    page: int
    page_size: int
