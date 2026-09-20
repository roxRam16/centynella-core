"""Modelo base para documentos de MongoDB.

Todos los modelos de colección heredan de `BaseDocument` (reutilización): así comparten
`_id` y las marcas de auditoría `created_at` / `updated_at`.

Guía de patrones de modelado (aplicar según el caso, ver README):
  · Set / Subset  → embeber datos que se leen juntos (ej. últimos N movimientos del producto).
  · Reference     → guardar solo el `_id` del otro documento (ej. `category_id`).
  · Extended ref  → referencia + copia de los campos que se leen siempre
                    (ej. `{category_id, category_name}`) para evitar `$lookup`.
"""

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def new_id() -> str:
    """Identificador de documento: UUID v4 en hexadecimal (str, sin ObjectId)."""
    return uuid4().hex


def utc_now() -> datetime:
    """Hora actual con zona horaria UTC (nunca datetimes "naive")."""
    return datetime.now(UTC)


class BaseDocument(BaseModel):
    """Campos comunes de todo documento."""

    model_config = ConfigDict(populate_by_name=True)

    # Mongo genera `_id` (ObjectId); aquí se expone como str para la API.
    id: str | None = Field(default=None, alias="_id")
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
