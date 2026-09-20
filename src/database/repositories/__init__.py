"""Repositorios de datos y su contenedor.

`Repositories` agrupa los cuatro repositorios que usan los servicios. En producción se
construye sobre MongoDB (`build_mongo_repositories`); en pruebas se inyecta uno en memoria.
"""

from dataclasses import dataclass

from pymongo.asynchronous.database import AsyncDatabase

from src.database.repositories.interfaces import (
    PasswordResetRepository,
    RefreshTokenRepository,
    RoleRepository,
    UserRepository,
)
from src.database.repositories.mongo import (
    MongoPasswordResetRepository,
    MongoRefreshTokenRepository,
    MongoRoleRepository,
    MongoUserRepository,
)


@dataclass
class Repositories:
    users: UserRepository
    roles: RoleRepository
    refresh_tokens: RefreshTokenRepository
    password_resets: PasswordResetRepository

    async def ensure_indexes(self) -> None:
        """Crea los índices de los repositorios que los necesitan (idempotente)."""
        for repository in (self.users, self.roles, self.refresh_tokens, self.password_resets):
            ensure = getattr(repository, "ensure_indexes", None)
            if ensure is not None:
                await ensure()


def build_mongo_repositories(db: AsyncDatabase) -> Repositories:
    """Repositorios reales sobre la base de datos `db`."""
    return Repositories(
        users=MongoUserRepository(db),
        roles=MongoRoleRepository(db),
        refresh_tokens=MongoRefreshTokenRepository(db),
        password_resets=MongoPasswordResetRepository(db),
    )


__all__ = [
    "MongoPasswordResetRepository",
    "MongoRefreshTokenRepository",
    "MongoRoleRepository",
    "MongoUserRepository",
    "PasswordResetRepository",
    "RefreshTokenRepository",
    "Repositories",
    "RoleRepository",
    "UserRepository",
    "build_mongo_repositories",
]
