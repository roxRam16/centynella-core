"""Hash de contraseñas con Argon2id (ganador de la Password Hashing Competition)."""

import asyncio

from argon2 import PasswordHasher as _Argon2
from argon2.exceptions import InvalidHashError, VerificationError


class PasswordHasher:
    """Envuelve argon2. Es CPU-intensivo: corre en un hilo para no bloquear el event loop."""

    def __init__(self) -> None:
        self._argon2 = _Argon2()
        # Hash de mentira: verificarlo iguala el tiempo de respuesta cuando el usuario no existe
        # (evita enumerar cuentas midiendo la latencia del login).
        self._dummy_hash = self._argon2.hash("centynella-dummy-password")

    async def hash(self, password: str) -> str:
        return await asyncio.to_thread(self._argon2.hash, password)

    async def verify(self, password_hash: str, password: str) -> bool:
        try:
            return await asyncio.to_thread(self._argon2.verify, password_hash, password)
        except (VerificationError, InvalidHashError):
            return False

    async def verify_dummy(self, password: str) -> None:
        """Consume el mismo tiempo que una verificación real; el resultado se descarta."""
        await self.verify(self._dummy_hash, password)

    def needs_rehash(self, password_hash: str) -> bool:
        """`True` si el hash usa parámetros antiguos y conviene regenerarlo tras un login."""
        return self._argon2.check_needs_rehash(password_hash)
