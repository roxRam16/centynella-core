"""Implementaciones de los repositorios sobre MongoDB (driver `pymongo` asíncrono).

Convenciones:
  · `_id` es un `str` (UUID hex), generado aquí al insertar. Sin ObjectId → sin conversiones.
  · Los índices únicos son la fuente de verdad de la unicidad (evita condiciones de carrera).
  · Los tokens llevan un índice TTL sobre `expires_at`: MongoDB limpia los vencidos solo.
"""

import re
from typing import Any

from pymongo import DESCENDING, ReturnDocument
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from src.database.errors import DuplicateError
from src.database.repositories.interfaces import LogQuery
from src.models import (
    LogEntry,
    PasswordResetDocument,
    RefreshTokenDocument,
    RoleDocument,
    UserDocument,
    new_id,
    utc_now,
)


def _dump(model: Any) -> dict[str, Any]:
    """Modelo → documento Mongo (con `_id`)."""
    return model.model_dump(by_alias=True)


class MongoUserRepository:
    def __init__(self, db: AsyncDatabase) -> None:
        self._collection: AsyncCollection = db["users"]

    async def ensure_indexes(self) -> None:
        await self._collection.create_index("email", unique=True)
        await self._collection.create_index("role")

    async def create(self, user: UserDocument) -> UserDocument:
        user.id = user.id or new_id()
        try:
            await self._collection.insert_one(_dump(user))
        except DuplicateKeyError as error:
            raise DuplicateError("email") from error
        return user

    async def get(self, user_id: str) -> UserDocument | None:
        document = await self._collection.find_one({"_id": user_id})
        return UserDocument.model_validate(document) if document else None

    async def get_by_email(self, email: str) -> UserDocument | None:
        document = await self._collection.find_one({"email": email})
        return UserDocument.model_validate(document) if document else None

    async def update(self, user_id: str, changes: dict[str, Any]) -> UserDocument | None:
        document = await self._collection.find_one_and_update(
            {"_id": user_id},
            {"$set": {**changes, "updated_at": utc_now()}},
            return_document=ReturnDocument.AFTER,
        )
        return UserDocument.model_validate(document) if document else None

    async def delete(self, user_id: str) -> bool:
        result = await self._collection.delete_one({"_id": user_id})
        return result.deleted_count == 1

    async def list(
        self, *, query: str | None, role: str | None, status: str | None, page: int, page_size: int
    ) -> tuple[list[UserDocument], int]:
        criteria = self._criteria(query=query, role=role, status=status)
        total = await self._collection.count_documents(criteria)
        cursor = (
            self._collection.find(criteria)
            # `_id` desempata: sin un orden total la paginación podría repetir u omitir usuarios.
            .sort([("created_at", DESCENDING), ("_id", DESCENDING)])
            .skip((page - 1) * page_size)
            .limit(page_size)
        )
        return [UserDocument.model_validate(doc) async for doc in cursor], total

    async def count(self, *, role: str | None = None, status: str | None = None) -> int:
        return await self._collection.count_documents(
            self._criteria(query=None, role=role, status=status)
        )

    @staticmethod
    def _criteria(*, query: str | None, role: str | None, status: str | None) -> dict[str, Any]:
        criteria: dict[str, Any] = {}
        if role:
            criteria["role"] = role
        if status:
            criteria["status"] = status
        if query:
            # re.escape: el texto del usuario nunca se interpreta como expresión regular.
            pattern = {"$regex": re.escape(query.strip()), "$options": "i"}
            criteria["$or"] = [{"name": pattern}, {"email": pattern}]
        return criteria


class MongoRoleRepository:
    def __init__(self, db: AsyncDatabase) -> None:
        self._collection: AsyncCollection = db["roles"]

    async def ensure_indexes(self) -> None:
        """El `_id` (clave del rol) ya es único; no se necesitan índices extra."""

    async def create(self, role: RoleDocument) -> RoleDocument:
        try:
            await self._collection.insert_one(_dump(role))
        except DuplicateKeyError as error:
            raise DuplicateError("key") from error
        return role

    async def get(self, key: str) -> RoleDocument | None:
        document = await self._collection.find_one({"_id": key})
        return RoleDocument.model_validate(document) if document else None

    async def list(self) -> list[RoleDocument]:
        cursor = self._collection.find({}).sort("_id", 1)
        return [RoleDocument.model_validate(doc) async for doc in cursor]

    async def update(self, key: str, changes: dict[str, Any]) -> RoleDocument | None:
        document = await self._collection.find_one_and_update(
            {"_id": key},
            {"$set": {**changes, "updated_at": utc_now()}},
            return_document=ReturnDocument.AFTER,
        )
        return RoleDocument.model_validate(document) if document else None

    async def delete(self, key: str) -> bool:
        result = await self._collection.delete_one({"_id": key})
        return result.deleted_count == 1


class MongoRefreshTokenRepository:
    def __init__(self, db: AsyncDatabase) -> None:
        self._collection: AsyncCollection = db["refresh_tokens"]

    async def ensure_indexes(self) -> None:
        await self._collection.create_index("token_hash", unique=True)
        await self._collection.create_index("family_id")
        await self._collection.create_index("user_id")
        await self._collection.create_index("expires_at", expireAfterSeconds=0)  # TTL

    async def create(self, token: RefreshTokenDocument) -> RefreshTokenDocument:
        token.id = token.id or new_id()
        await self._collection.insert_one(_dump(token))
        return token

    async def get_by_hash(self, token_hash: str) -> RefreshTokenDocument | None:
        document = await self._collection.find_one({"token_hash": token_hash})
        return RefreshTokenDocument.model_validate(document) if document else None

    async def rotate(self, token_id: str) -> None:
        now = utc_now()
        await self._collection.update_one(
            {"_id": token_id, "revoked_at": None},
            {"$set": {"revoked_at": now, "rotated_at": now}},
        )

    async def revoke_family(self, family_id: str) -> None:
        await self._collection.update_many(
            {"family_id": family_id, "revoked_at": None}, {"$set": {"revoked_at": utc_now()}}
        )

    async def revoke_all_for_user(self, user_id: str) -> None:
        await self._collection.update_many(
            {"user_id": user_id, "revoked_at": None}, {"$set": {"revoked_at": utc_now()}}
        )


class MongoPasswordResetRepository:
    def __init__(self, db: AsyncDatabase) -> None:
        self._collection: AsyncCollection = db["password_resets"]

    async def ensure_indexes(self) -> None:
        await self._collection.create_index("token_hash", unique=True)
        await self._collection.create_index("user_id")
        await self._collection.create_index("expires_at", expireAfterSeconds=0)  # TTL

    async def create(self, reset: PasswordResetDocument) -> PasswordResetDocument:
        reset.id = reset.id or new_id()
        await self._collection.insert_one(_dump(reset))
        return reset

    async def get_by_hash(self, token_hash: str) -> PasswordResetDocument | None:
        document = await self._collection.find_one({"token_hash": token_hash})
        return PasswordResetDocument.model_validate(document) if document else None

    async def mark_used(self, reset_id: str) -> None:
        await self._collection.update_one({"_id": reset_id}, {"$set": {"used_at": utc_now()}})

    async def invalidate_for_user(self, user_id: str) -> None:
        await self._collection.update_many(
            {"user_id": user_id, "used_at": None}, {"$set": {"used_at": utc_now()}}
        )


class MongoLogRepository:
    """Bitácora en la base de datos de logs.

    Índices pensados para las consultas de la interfaz: por módulo, usuario, sesión, petición y
    nivel (siempre ordenadas por fecha). Un índice TTL borra los eventos viejos solo, así la
    bitácora no crece sin límite.
    """

    def __init__(self, db: AsyncDatabase, retention_days: int = 30) -> None:
        self._collection: AsyncCollection = db["logs"]
        self._retention_seconds = retention_days * 24 * 3600

    async def ensure_indexes(self) -> None:
        for keys in (
            [("module", 1), ("timestamp", -1)],
            [("user_id", 1), ("timestamp", -1)],
            [("session_id", 1), ("timestamp", -1)],
            [("level", 1), ("timestamp", -1)],
            [("service", 1), ("timestamp", -1)],
            [("request_id", 1)],
            [("event", 1)],
        ):
            await self._collection.create_index(keys)
        await self._collection.create_index(
            "timestamp", expireAfterSeconds=self._retention_seconds
        )  # TTL + orden por fecha

    async def insert_many(self, entries: list[LogEntry]) -> None:
        if entries:
            await self._collection.insert_many(
                [entry.model_dump(by_alias=True) for entry in entries], ordered=False
            )

    async def search(
        self, query: LogQuery, *, page: int, page_size: int
    ) -> tuple[list[LogEntry], int]:
        criteria = self._criteria(query)
        total = await self._collection.count_documents(criteria)
        cursor = (
            self._collection.find(criteria)
            .sort([("timestamp", DESCENDING), ("_id", DESCENDING)])
            .skip((page - 1) * page_size)
            .limit(page_size)
        )
        return [LogEntry.model_validate(document) async for document in cursor], total

    async def modules(self) -> list[str]:
        return sorted(await self._collection.distinct("module"))

    @staticmethod
    def _criteria(query: LogQuery) -> dict[str, Any]:
        criteria: dict[str, Any] = {}
        for field in ("module", "event", "service", "user_id", "session_id", "request_id"):
            value = getattr(query, field)
            if value:
                criteria[field] = value
        if query.levels:
            criteria["level"] = {"$in": query.levels}
        if query.since or query.until:
            window: dict[str, Any] = {}
            if query.since:
                window["$gte"] = query.since
            if query.until:
                window["$lte"] = query.until
            criteria["timestamp"] = window
        if query.text:
            criteria["message"] = {"$regex": re.escape(query.text.strip()), "$options": "i"}
        return criteria
