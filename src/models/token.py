"""Modelos de tokens de un solo uso guardados en base de datos.

Nunca se guarda el token en claro: solo su hash SHA-256. Si la base se filtra,
los tokens no sirven. Ambas colecciones tienen un índice TTL sobre `expires_at`
que limpia los vencidos automáticamente.
"""

from datetime import datetime

from src.models.base import BaseDocument


class RefreshTokenDocument(BaseDocument):
    """Colección `refresh_tokens`: una sesión de un dispositivo.

    Los tokens rotan en cada uso y comparten un `family_id`; si se reutiliza uno ya
    rotado (posible robo) se revoca toda la familia.
    """

    user_id: str
    token_hash: str
    family_id: str
    expires_at: datetime
    revoked_at: datetime | None = None
    # Solo si lo sustituyó una rotación (no logout/robo): habilita la ventana de tolerancia.
    rotated_at: datetime | None = None
    user_agent: str | None = None


class PasswordResetDocument(BaseDocument):
    """Colección `password_resets`: solicitud de recuperación de contraseña."""

    user_id: str
    token_hash: str
    expires_at: datetime
    used_at: datetime | None = None
