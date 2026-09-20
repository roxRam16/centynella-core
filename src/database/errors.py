"""Errores de la capa de datos (independientes del driver de MongoDB)."""


class DuplicateError(Exception):
    """Violación de unicidad. `field` indica qué campo se repite (ej. `email`, `key`)."""

    def __init__(self, field: str) -> None:
        super().__init__(f"Valor duplicado en '{field}'")
        self.field = field
