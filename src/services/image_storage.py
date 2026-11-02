"""Almacenamiento de imágenes de producto en disco local.

MVP: guarda en `media_dir/products/<id>.<ext>` y sirve desde `/media` (ver `app.py`). En un
despliegue real a ECS el disco no persiste entre despliegues — el día que haga falta, cambiar
la implementación detrás de esta misma interfaz (p. ej. subir a S3) sin tocar quien la usa.
"""

from pathlib import Path

from src.services.errors import BadRequestError

# Firma de bytes (magic numbers) por formato: se valida el contenido real, no solo lo que el
# cliente declaró en `Content-Type` (un archivo renombrado no cuela).
_SIGNATURES: dict[bytes, str] = {
    b"\xff\xd8\xff": "jpg",
    b"\x89PNG\r\n\x1a\n": "png",
}
_WEBP_RIFF = b"RIFF"
_WEBP_MARKER = b"WEBP"


def _detect_extension(content: bytes) -> str | None:
    for signature, extension in _SIGNATURES.items():
        if content.startswith(signature):
            return extension
    if content[:4] == _WEBP_RIFF and content[8:12] == _WEBP_MARKER:
        return "webp"
    return None


class ProductImageStorage:
    """Guarda y borra la foto de un producto en `media_dir/products/`."""

    def __init__(self, media_dir: Path, *, max_bytes: int) -> None:
        self._root = media_dir / "products"
        self._root.mkdir(parents=True, exist_ok=True)
        self._max_bytes = max_bytes

    def save(self, product_id: str, content: bytes) -> str:
        """Valida y guarda la imagen. Devuelve la ruta relativa a `media_dir` (p. ej.
        "products/<id>.jpg"). Borra cualquier foto previa del producto (con otra extensión)."""
        if len(content) > self._max_bytes:
            raise BadRequestError(
                f"La imagen supera el máximo de {self._max_bytes // 1024} KB.",
                code="image_too_large",
            )
        extension = _detect_extension(content)
        if extension is None:
            raise BadRequestError(
                "Formato de imagen no soportado. Usa JPG, PNG o WEBP.",
                code="unsupported_image_type",
            )

        self.delete(product_id)
        relative_path = f"products/{product_id}.{extension}"
        (self._root / f"{product_id}.{extension}").write_bytes(content)
        return relative_path

    def delete(self, product_id: str) -> None:
        """Borra cualquier foto existente del producto, sin importar la extensión."""
        for extension in ("jpg", "png", "webp"):
            path = self._root / f"{product_id}.{extension}"
            if path.exists():
                path.unlink()
