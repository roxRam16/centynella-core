"""Bitácora de eventos: registra QUÉ pasa, en QUÉ módulo, con QUÉ usuario y QUÉ sesión.

Diseño:
  · `EventLogger.log(...)` es SÍNCRONO y no bloquea: mete el evento en una cola en memoria y
    vuelve al instante. Un trabajador en segundo plano los guarda en la base de datos de logs
    por lotes. Así una petición nunca espera a la bitácora, y si la base de logs se cae la
    aplicación sigue funcionando (los eventos se reintentan y, si no hay remedio, se descartan
    avisándolo por el log de Python).
  · Usuario, sesión, IP y `request_id` se toman solos del contexto de la petición.
  · Nunca se guardan secretos: las claves que parecen contraseña/token se reemplazan y los
    textos largos se recortan. Los correos se enmascaran (`a***@dominio.com`).
"""

import asyncio
import contextlib
import logging
import re
from typing import Any

from src.database import LogRepository
from src.middlewares.context import get_context
from src.models import LEVEL_ORDER, LogEntry, LogLevel

logger = logging.getLogger(__name__)

_SENSITIVE_KEY = re.compile(r"pass|token|secret|authorization|cookie|api[_-]?key|credential", re.I)
_MAX_STRING = 2000
_MAX_DEPTH = 4


def mask_email(email: str | None) -> str | None:
    """`ana@example.com` → `a***@example.com` (permite investigar sin exponer el correo)."""
    if not email or "@" not in email:
        return email
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}"


def sanitize(value: Any, depth: int = 0) -> Any:
    """Deja `value` listo para guardar: sin secretos, sin textos enormes, compatible con Mongo."""
    if depth > _MAX_DEPTH:
        return "[demasiado anidado]"
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            # Mongo no admite claves con "." ni que empiecen con "$".
            safe_key = str(key).replace(".", "_").lstrip("$") or "_"
            clean[safe_key] = (
                "[oculto]" if _SENSITIVE_KEY.search(safe_key) else sanitize(item, depth + 1)
            )
        return clean
    if isinstance(value, list | tuple | set):
        return [sanitize(item, depth + 1) for item in list(value)[:50]]
    if isinstance(value, str):
        return value if len(value) <= _MAX_STRING else value[:_MAX_STRING] + "…"
    if value is None or isinstance(value, bool | int | float):
        return value
    return sanitize(str(value), depth + 1)


class EventLogger:
    """Registrador de eventos con cola asíncrona. Una instancia por proceso."""

    def __init__(
        self,
        repository: LogRepository,
        *,
        service: str,
        environment: str,
        min_level: LogLevel = "INFO",
        batch_size: int = 100,
        flush_interval: float = 1.0,
        retry_delay: float = 0.5,
        queue_size: int = 10_000,
    ) -> None:
        self._repository = repository
        self._service = service
        self._environment = environment
        self._min_level = LEVEL_ORDER[min_level]
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._retry_delay = retry_delay
        self._queue: asyncio.Queue[LogEntry] = asyncio.Queue(maxsize=queue_size)
        self._worker: asyncio.Task | None = None
        self.dropped = 0  # eventos descartados por cola llena o base de logs caída

    # ── API de registro ─────────────────────────────────────────────────────────
    def log(
        self,
        level: LogLevel,
        module: str,
        event: str,
        message: str,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
        **details: Any,
    ) -> None:
        """Registra un evento. No bloquea ni lanza: la bitácora nunca rompe una petición."""
        if LEVEL_ORDER[level] < self._min_level:
            return
        context = get_context()
        entry = LogEntry(
            level=level,
            service=self._service,
            module=module,
            event=event,
            message=message[:500],
            environment=self._environment,
            request_id=context.request_id,
            user_id=user_id or context.user_id,
            session_id=session_id or context.session_id,
            ip=context.ip,
            details=sanitize(details),
        )
        try:
            self._queue.put_nowait(entry)
        except asyncio.QueueFull:
            self.dropped += 1

    def debug(self, module: str, event: str, message: str, **kwargs: Any) -> None:
        self.log("DEBUG", module, event, message, **kwargs)

    def info(self, module: str, event: str, message: str, **kwargs: Any) -> None:
        self.log("INFO", module, event, message, **kwargs)

    def warning(self, module: str, event: str, message: str, **kwargs: Any) -> None:
        self.log("WARNING", module, event, message, **kwargs)

    def error(self, module: str, event: str, message: str, **kwargs: Any) -> None:
        self.log("ERROR", module, event, message, **kwargs)

    def critical(self, module: str, event: str, message: str, **kwargs: Any) -> None:
        self.log("CRITICAL", module, event, message, **kwargs)

    # ── Ciclo de vida ───────────────────────────────────────────────────────────
    async def start(self) -> None:
        """Arranca el trabajador que guarda los eventos. Idempotente."""
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._run(), name="event-logger")

    async def flush(self) -> None:
        """Espera a que todo lo encolado se haya guardado (pruebas y apagado)."""
        await self._queue.join()

    async def stop(self, timeout: float = 5.0) -> None:
        """Guarda lo pendiente (hasta `timeout` s) y detiene el trabajador."""
        if self._worker is None:
            return
        try:
            await asyncio.wait_for(self.flush(), timeout)
        except TimeoutError:
            logger.warning("Apagado con %d eventos de bitácora sin guardar", self._queue.qsize())
        self._worker.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._worker
        self._worker = None

    # ── Trabajador ──────────────────────────────────────────────────────────────
    async def _run(self) -> None:
        while True:
            batch = [await self._queue.get()]
            if self._flush_interval:
                await asyncio.sleep(self._flush_interval)  # deja acumular un lote
            while len(batch) < self._batch_size:
                try:
                    batch.append(self._queue.get_nowait())
                except asyncio.QueueEmpty:
                    break
            try:
                await self._write(batch)
            finally:
                for _ in batch:
                    self._queue.task_done()

    async def _write(self, batch: list[LogEntry]) -> None:
        for attempt in range(1, 4):
            try:
                await self._repository.insert_many(batch)
                return
            except Exception as error:  # noqa: BLE001 - la bitácora jamás debe tumbar la app
                if attempt == 3:
                    self.dropped += len(batch)
                    logger.error("Se perdieron %d eventos de bitácora: %s", len(batch), error)
                else:
                    await asyncio.sleep(self._retry_delay * attempt)


# Loggers de Python que NO se reenvían a la bitácora (evita bucles y ruido).
_IGNORED_LOGGERS = ("src.services.event_logger", "pymongo", "uvicorn.access", "httpx", "httpcore")


class BridgeLogHandler(logging.Handler):
    """Reenvía a la bitácora los WARNING/ERROR/CRITICAL del `logging` estándar de Python.

    Así, aunque el código no llame a `EventLogger`, los avisos y errores de cualquier librería
    (ej. "MongoDB no responde") también quedan en la bitácora.
    """

    def __init__(self, events: EventLogger) -> None:
        super().__init__(level=logging.WARNING)
        self._events = events

    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith(_IGNORED_LOGGERS):
            return
        try:
            level: LogLevel = (
                "CRITICAL"
                if record.levelno >= logging.CRITICAL
                else "ERROR"
                if record.levelno >= logging.ERROR
                else "WARNING"
            )
            details: dict[str, Any] = {"logger": record.name}
            if record.exc_info and record.exc_info[1] is not None:
                details["exception"] = f"{type(record.exc_info[1]).__name__}: {record.exc_info[1]}"
            module = "database" if "database" in record.name else "system"
            self._events.log(level, module, f"python.{record.name}", record.getMessage(), **details)
        except Exception:  # noqa: BLE001
            self.handleError(record)
