"""Dobles de prueba: repositorios en memoria y un remitente de correo que guarda lo enviado.

Implementan los mismos `Protocol` que los repositorios de MongoDB.
`tests/test_repository_contract.py` ejecuta la MISMA batería contra ambos, así se garantiza
que el doble se comporta como la base real.
"""

from typing import Any

from src.database import DuplicateError, LogQuery, Repositories
from src.models import (
    CreditMovementDocument,
    CustomerDocument,
    LogEntry,
    PasswordResetDocument,
    ProductDocument,
    RefreshTokenDocument,
    RoleDocument,
    UserDocument,
    new_id,
    utc_now,
)


class InMemoryUserRepository:
    def __init__(self) -> None:
        self.items: dict[str, UserDocument] = {}

    async def create(self, user: UserDocument) -> UserDocument:
        if any(existing.email == user.email for existing in self.items.values()):
            raise DuplicateError("email")
        user.id = user.id or new_id()
        self.items[user.id] = user.model_copy(deep=True)
        return user

    async def get(self, user_id: str) -> UserDocument | None:
        user = self.items.get(user_id)
        return user.model_copy(deep=True) if user else None

    async def get_by_email(self, email: str) -> UserDocument | None:
        for user in self.items.values():
            if user.email == email:
                return user.model_copy(deep=True)
        return None

    async def update(self, user_id: str, changes: dict[str, Any]) -> UserDocument | None:
        user = self.items.get(user_id)
        if user is None:
            return None
        self.items[user_id] = user.model_copy(update={**changes, "updated_at": utc_now()})
        return self.items[user_id].model_copy(deep=True)

    async def delete(self, user_id: str) -> bool:
        return self.items.pop(user_id, None) is not None

    async def list(
        self, *, query: str | None, role: str | None, status: str | None, page: int, page_size: int
    ) -> tuple[list[UserDocument], int]:
        matches = [u for u in self.items.values() if self._matches(u, query, role, status)]
        matches.sort(key=lambda u: (u.created_at, u.id), reverse=True)
        start = (page - 1) * page_size
        return [u.model_copy(deep=True) for u in matches[start : start + page_size]], len(matches)

    async def count(self, *, role: str | None = None, status: str | None = None) -> int:
        return sum(1 for u in self.items.values() if self._matches(u, None, role, status))

    @staticmethod
    def _matches(user: UserDocument, query: str | None, role: str | None, status: str | None):
        if role and user.role != role:
            return False
        if status and user.status != status:
            return False
        if query:
            needle = query.strip().lower()
            return needle in user.name.lower() or needle in user.email.lower()
        return True


class InMemoryProductRepository:
    def __init__(self) -> None:
        self.items: dict[str, ProductDocument] = {}

    async def create(self, product: ProductDocument) -> ProductDocument:
        if any(existing.sku == product.sku for existing in self.items.values()):
            raise DuplicateError("sku")
        product.id = product.id or new_id()
        self.items[product.id] = product.model_copy(deep=True)
        return product

    async def get(self, product_id: str) -> ProductDocument | None:
        product = self.items.get(product_id)
        return product.model_copy(deep=True) if product else None

    async def update(self, product_id: str, changes: dict[str, Any]) -> ProductDocument | None:
        product = self.items.get(product_id)
        if product is None:
            return None
        self.items[product_id] = product.model_copy(update={**changes, "updated_at": utc_now()})
        return self.items[product_id].model_copy(deep=True)

    async def delete(self, product_id: str) -> bool:
        return self.items.pop(product_id, None) is not None

    async def list(
        self,
        *,
        query: str | None,
        category: str | None,
        status: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[ProductDocument], int]:
        matches = [p for p in self.items.values() if self._matches(p, query, category, status)]
        matches.sort(key=lambda p: (p.created_at, p.id), reverse=True)
        start = (page - 1) * page_size
        return [p.model_copy(deep=True) for p in matches[start : start + page_size]], len(matches)

    @staticmethod
    def _matches(
        product: ProductDocument, query: str | None, category: str | None, status: str | None
    ):
        if category and product.category != category:
            return False
        if status and product.status != status:
            return False
        if query:
            needle = query.strip().lower()
            return needle in product.name.lower() or needle in product.sku.lower()
        return True


class InMemoryCustomerRepository:
    def __init__(self) -> None:
        self.items: dict[str, CustomerDocument] = {}

    async def create(self, customer: CustomerDocument) -> CustomerDocument:
        customer.id = customer.id or new_id()
        self.items[customer.id] = customer.model_copy(deep=True)
        return customer

    async def get(self, customer_id: str) -> CustomerDocument | None:
        customer = self.items.get(customer_id)
        return customer.model_copy(deep=True) if customer else None

    async def update(self, customer_id: str, changes: dict[str, Any]) -> CustomerDocument | None:
        customer = self.items.get(customer_id)
        if customer is None:
            return None
        self.items[customer_id] = customer.model_copy(update={**changes, "updated_at": utc_now()})
        return self.items[customer_id].model_copy(deep=True)

    async def adjust_balance(self, customer_id: str, delta: float) -> CustomerDocument | None:
        customer = self.items.get(customer_id)
        if customer is None:
            return None
        self.items[customer_id] = customer.model_copy(
            update={"balance": customer.balance + delta, "updated_at": utc_now()}
        )
        return self.items[customer_id].model_copy(deep=True)

    async def delete(self, customer_id: str) -> bool:
        return self.items.pop(customer_id, None) is not None

    async def list(
        self, *, query: str | None, page: int, page_size: int
    ) -> tuple[list[CustomerDocument], int]:
        matches = [c for c in self.items.values() if self._matches(c, query)]
        matches.sort(key=lambda c: (c.created_at, c.id), reverse=True)
        start = (page - 1) * page_size
        return [c.model_copy(deep=True) for c in matches[start : start + page_size]], len(matches)

    @staticmethod
    def _matches(customer: CustomerDocument, query: str | None) -> bool:
        if not query:
            return True
        needle = query.strip().lower()
        return needle in customer.name.lower() or needle in (customer.phone or "").lower()


class InMemoryCreditMovementRepository:
    def __init__(self) -> None:
        self.items: dict[str, CreditMovementDocument] = {}

    async def create(self, movement: CreditMovementDocument) -> CreditMovementDocument:
        movement.id = movement.id or new_id()
        self.items[movement.id] = movement.model_copy(deep=True)
        return movement

    async def list_for_customer(
        self, customer_id: str, *, page: int, page_size: int
    ) -> tuple[list[CreditMovementDocument], int]:
        matches = [m for m in self.items.values() if m.customer_id == customer_id]
        matches.sort(key=lambda m: (m.created_at, m.id), reverse=True)
        start = (page - 1) * page_size
        return [m.model_copy(deep=True) for m in matches[start : start + page_size]], len(matches)


class InMemoryRoleRepository:
    def __init__(self) -> None:
        self.items: dict[str, RoleDocument] = {}

    async def create(self, role: RoleDocument) -> RoleDocument:
        if role.id in self.items:
            raise DuplicateError("key")
        self.items[role.key] = role.model_copy(deep=True)
        return role

    async def get(self, key: str) -> RoleDocument | None:
        role = self.items.get(key)
        return role.model_copy(deep=True) if role else None

    async def list(self) -> list[RoleDocument]:
        return [self.items[key].model_copy(deep=True) for key in sorted(self.items)]

    async def update(self, key: str, changes: dict[str, Any]) -> RoleDocument | None:
        role = self.items.get(key)
        if role is None:
            return None
        self.items[key] = role.model_copy(update={**changes, "updated_at": utc_now()})
        return self.items[key].model_copy(deep=True)

    async def delete(self, key: str) -> bool:
        return self.items.pop(key, None) is not None


class InMemoryRefreshTokenRepository:
    def __init__(self) -> None:
        self.items: dict[str, RefreshTokenDocument] = {}

    async def create(self, token: RefreshTokenDocument) -> RefreshTokenDocument:
        token.id = token.id or new_id()
        self.items[token.id] = token.model_copy(deep=True)
        return token

    async def get_by_hash(self, token_hash: str) -> RefreshTokenDocument | None:
        for token in self.items.values():
            if token.token_hash == token_hash:
                return token.model_copy(deep=True)
        return None

    async def rotate(self, token_id: str) -> None:
        token = self.items.get(token_id)
        if token and token.revoked_at is None:
            token.revoked_at = token.rotated_at = utc_now()

    async def revoke_family(self, family_id: str) -> None:
        for token in self.items.values():
            if token.family_id == family_id and token.revoked_at is None:
                token.revoked_at = utc_now()

    async def revoke_all_for_user(self, user_id: str) -> None:
        for token in self.items.values():
            if token.user_id == user_id and token.revoked_at is None:
                token.revoked_at = utc_now()


class InMemoryPasswordResetRepository:
    def __init__(self) -> None:
        self.items: dict[str, PasswordResetDocument] = {}

    async def create(self, reset: PasswordResetDocument) -> PasswordResetDocument:
        reset.id = reset.id or new_id()
        self.items[reset.id] = reset.model_copy(deep=True)
        return reset

    async def get_by_hash(self, token_hash: str) -> PasswordResetDocument | None:
        for reset in self.items.values():
            if reset.token_hash == token_hash:
                return reset.model_copy(deep=True)
        return None

    async def mark_used(self, reset_id: str) -> None:
        if reset_id in self.items:
            self.items[reset_id].used_at = utc_now()

    async def invalidate_for_user(self, user_id: str) -> None:
        for reset in self.items.values():
            if reset.user_id == user_id and reset.used_at is None:
                reset.used_at = utc_now()


def build_in_memory_repositories() -> Repositories:
    return Repositories(
        users=InMemoryUserRepository(),
        roles=InMemoryRoleRepository(),
        refresh_tokens=InMemoryRefreshTokenRepository(),
        password_resets=InMemoryPasswordResetRepository(),
        products=InMemoryProductRepository(),
        customers=InMemoryCustomerRepository(),
        credit_movements=InMemoryCreditMovementRepository(),
    )


class OutboxEmailSender:
    """Guarda los correos "enviados" para poder leer el enlace de recuperación en las pruebas."""

    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []
        self.fail = False

    async def send(self, to: str, subject: str, body: str) -> None:
        if self.fail:
            raise RuntimeError("SMTP caído")
        self.sent.append({"to": to, "subject": subject, "body": body})

    def last_reset_token(self) -> str:
        """Extrae el token del último enlace `.../reset-password?token=XXXX`."""
        body = self.sent[-1]["body"]
        return body.split("token=")[1].split()[0]


class FakeDatabase:
    """Doble de `DatabaseManager`: permite simular Mongo arriba o caído."""

    def __init__(self, up: bool = True) -> None:
        self.up = up
        self.closed = False

    async def ping(self) -> bool:
        return self.up

    async def close(self) -> None:
        self.closed = True


class InMemoryLogRepository:
    """Bitácora en memoria con las mismas reglas de búsqueda que la de MongoDB."""

    def __init__(self) -> None:
        self.items: list[LogEntry] = []
        self.fail = False

    async def insert_many(self, entries: list[LogEntry]) -> None:
        if self.fail:
            raise RuntimeError("base de logs caída")
        self.items.extend(entry.model_copy(deep=True) for entry in entries)

    async def search(self, query: LogQuery, *, page: int, page_size: int):
        matches = [entry for entry in self.items if self._matches(entry, query)]
        matches.sort(key=lambda entry: (entry.timestamp, entry.id), reverse=True)
        start = (page - 1) * page_size
        return [e.model_copy(deep=True) for e in matches[start : start + page_size]], len(matches)

    async def modules(self) -> list[str]:
        return sorted({entry.module for entry in self.items})

    def by_event(self, event: str) -> list[LogEntry]:
        """Atajo para las pruebas: eventos con ese código."""
        return [entry for entry in self.items if entry.event == event]

    @staticmethod
    def _matches(entry: LogEntry, query: LogQuery) -> bool:
        for field in ("module", "event", "service", "user_id", "session_id", "request_id"):
            wanted = getattr(query, field)
            if wanted and getattr(entry, field) != wanted:
                return False
        if query.levels and entry.level not in query.levels:
            return False
        if query.since and entry.timestamp < query.since:
            return False
        if query.until and entry.timestamp > query.until:
            return False
        return not (query.text and query.text.strip().lower() not in entry.message.lower())
