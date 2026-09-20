"""Log de acceso: un evento `http.request` por petición (módulo `http` de la bitácora)."""

import time
from typing import TYPE_CHECKING

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.middlewares.context import get_context

if TYPE_CHECKING:
    from src.services.event_logger import EventLogger

# Ruta con la que el frontend intenta restaurar la sesión al abrir la app (su 401 es normal).
_SESSION_PROBE = "/auth/refresh"

# No se registran: sondas (ruido cada pocos segundos), documentación y la propia consulta de la
# bitácora (si no, mirar los logs generaría más logs).
DEFAULT_IGNORED_PREFIXES = ("/health", "/docs", "/redoc", "/openapi.json", "/api/v1/logs")


class AccessLogMiddleware:
    """Registra método, ruta, estado y duración de cada petición, con su usuario y sesión.

    Nunca registra la query string (podría llevar datos sensibles) ni cuerpos ni cabeceras.
    Severidad: 2xx/3xx → INFO · 4xx → WARNING · 5xx → ERROR.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        events: "EventLogger",
        ignored_prefixes: tuple[str, ...] = DEFAULT_IGNORED_PREFIXES,
    ) -> None:
        self.app = app
        self._events = events
        self._ignored = ignored_prefixes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path: str = scope.get("path", "")
        if scope["type"] != "http" or path.startswith(self._ignored):
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        status = 500  # si la app revienta antes de responder, el cliente recibe un 500

        async def capture_status(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, capture_status)
        finally:
            method = scope.get("method", "?")
            level = "ERROR" if status >= 500 else "WARNING" if status >= 400 else "INFO"
            if status == 401 and path.endswith(_SESSION_PROBE):
                # El frontend prueba /auth/refresh al abrir la app para restaurar la sesión: sin
                # cookie el 401 es lo NORMAL (visitante anónimo), no una advertencia.
                level = "INFO"
            self._events.log(
                level,
                "http",
                "http.request",
                f"{method} {path} → {status}",
                method=method,
                path=path,
                status=status,
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
                user_agent=get_context().user_agent,
            )
