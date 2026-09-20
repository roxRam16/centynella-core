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

    def __init__(self, uri: str, db_name: str, timeout_ms: int = 2000) -> None:
        # El cliente es perezoso: no conecta hasta la primera operación.
        self._client: AsyncMongoClient = AsyncMongoClient(
            uri, serverSelectionTimeoutMS=timeout_ms, appname="centynella-core"
        )
        self._db_name = db_name

    @property
    def db(self) -> AsyncDatabase:
        """Base de datos activa, para que los repositorios/servicios consulten colecciones."""
        return self._client[self._db_name]

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
