"""Envío de correos (patrón Strategy).

`EmailSender` es el contrato. Hoy solo existe `LogEmailSender`, que escribe el correo en el
log — suficiente para desarrollo (copias el enlace de recuperación de la consola).
Para producción se añade una implementación SMTP / Amazon SES y se elige en `create_app`.
"""

import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class EmailSender(Protocol):
    async def send(self, to: str, subject: str, body: str) -> None: ...


class LogEmailSender:
    """Registra el correo en el log en lugar de enviarlo."""

    async def send(self, to: str, subject: str, body: str) -> None:
        logger.info("[EMAIL simulado] Para: %s | Asunto: %s\n%s", to, subject, body)


def build_password_reset_email(name: str, link: str, ttl_minutes: int) -> tuple[str, str]:
    """Devuelve `(asunto, cuerpo)` del correo de recuperación de contraseña."""
    subject = "Recupera tu contraseña de CENTYNELLA"
    body = (
        f"Hola {name},\n\n"
        "Recibimos una solicitud para restablecer tu contraseña.\n"
        f"Usa este enlace (vence en {ttl_minutes} minutos):\n\n{link}\n\n"
        "Si no fuiste tú, ignora este mensaje: tu contraseña no cambiará."
    )
    return subject, body
