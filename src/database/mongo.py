"""Conexión a MongoDB.

Patrón: *Connection Manager*. Un único cliente (AsyncMongoClient) por proceso,
creado en el arranque de la app y cerrado al apagarla (ver `lifespan` en app.py).
Los servicios reciben el manager por inyección de dependencias, no lo importan
como global, lo que permite sustituirlo en las pruebas.
"""

import logging

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Encapsula el cliente y la base de datos de MongoDB."""

    def __init__(
        self, uri: str, db_name: str, timeout_ms: int = 2000, logs_db_name: str | None = None
    ) -> None:
        # El cliente es perezoso: no conecta hasta la primera operación.
        self._client: AsyncMongoClient = AsyncMongoClient(
            uri,
            serverSelectionTimeoutMS=timeout_ms,
            appname="centynella-core",
            tz_aware=True,  # las fechas leídas conservan su zona horaria (UTC)
        )
        self._db_name = db_name
        self._logs_db_name = logs_db_name or f"{db_name}_logs"

    @property
    def db(self) -> AsyncDatabase:
        """Base de datos activa, para que los repositorios/servicios consulten colecciones."""
        return self._client[self._db_name]

    @property
    def logs_db(self) -> AsyncDatabase:
        """Base de datos de la bitácora: SEPARADA de la de negocio, en el mismo cluster."""
        return self._client[self._logs_db_name]

    async def ping(self) -> bool:
        """`True` si MongoDB responde; `False` (sin lanzar) si no está disponible."""
        try:
            await self._client.admin.command("ping")
            return True
        except Exception as error:  # noqa: BLE001 - cualquier fallo de red equivale a "caído"
            logger.warning("MongoDB no responde: %s", error)
            return False

    async def close(self) -> None:
        """Cierra las conexiones. Se invoca al apagar la aplicación."""
        await self._client.close()
