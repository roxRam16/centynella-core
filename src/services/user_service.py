"""Gestión de usuarios: perfil propio y administración."""

from src.database import DuplicateError, Repositories
from src.models import ADMIN_ROLE, UserDocument, UserStatus
from src.services.errors import ConflictError, NotFoundError, ValidationFailedError
from src.services.password_hasher import PasswordHasher


class UserService:
    def __init__(self, repositories: Repositories, hasher: PasswordHasher) -> None:
        self._users = repositories.users
        self._roles = repositories.roles
        self._refresh_tokens = repositories.refresh_tokens
        self._hasher = hasher

    async def permissions_of(self, user: UserDocument) -> list[str]:
        """Permisos efectivos del usuario = los de su rol (se leen en cada petición)."""
        role = await self._roles.get(user.role)
        return sorted(role.permissions) if role else []

    async def get(self, user_id: str) -> UserDocument:
        user = await self._users.get(user_id)
        if user is None:
            raise NotFoundError("Usuario no encontrado.", code="user_not_found")
        return user

    async def list(
        self, *, query: str | None, role: str | None, status: str | None, page: int, page_size: int
    ) -> tuple[list[UserDocument], int]:
        return await self._users.list(
            query=query, role=role, status=status, page=page, page_size=page_size
        )

    async def create(
        self, *, name: str, email: str, password: str, role: str, status: UserStatus
    ) -> UserDocument:
        await self._require_role(role)
        user = UserDocument(
            email=email,
            name=name,
            password_hash=await self._hasher.hash(password),
            role=role,
            status=status,
        )
        try:
            return await self._users.create(user)
        except DuplicateError as error:
            raise ConflictError(
                "Ya existe una cuenta con ese correo.", code="email_taken"
            ) from error

    async def update_profile(self, user_id: str, *, name: str) -> UserDocument:
        """El propio usuario solo puede cambiar datos personales (nunca rol ni estado)."""
        updated = await self._users.update(user_id, {"name": name})
        if updated is None:
            raise NotFoundError("Usuario no encontrado.", code="user_not_found")
        return updated

    async def update(
        self,
        actor_id: str,
        user_id: str,
        *,
        name: str | None,
        role: str | None,
        status: UserStatus | None,
    ) -> UserDocument:
        target = await self.get(user_id)
        changes: dict = {}
        if name is not None:
            changes["name"] = name
        if role is not None and role != target.role:
            await self._require_role(role)
            changes["role"] = role
        if status is not None and status != target.status:
            changes["status"] = status

        if user_id == actor_id and ("role" in changes or "status" in changes):
            raise ConflictError(
                "No puedes cambiar tu propio rol ni tu estado.", code="self_modification"
            )
        if ("role" in changes or "status" in changes) and await self._is_last_active_admin(target):
            raise ConflictError("Debe existir al menos un administrador activo.", code="last_admin")

        updated = await self._users.update(user_id, changes) if changes else target
        if updated is None:
            raise NotFoundError("Usuario no encontrado.", code="user_not_found")
        if changes.get("status") == "disabled":
            await self._refresh_tokens.revoke_all_for_user(user_id)  # cierra sus sesiones
        return updated

    async def delete(self, actor_id: str, user_id: str) -> None:
        target = await self.get(user_id)
        if user_id == actor_id:
            raise ConflictError("No puedes eliminar tu propia cuenta.", code="self_modification")
        if await self._is_last_active_admin(target):
            raise ConflictError("Debe existir al menos un administrador activo.", code="last_admin")
        await self._users.delete(user_id)
        await self._refresh_tokens.revoke_all_for_user(user_id)

    async def _require_role(self, role_key: str) -> None:
        if await self._roles.get(role_key) is None:
            raise ValidationFailedError(f"El rol '{role_key}' no existe.", code="role_not_found")

    async def _is_last_active_admin(self, user: UserDocument) -> bool:
        if user.role != ADMIN_ROLE or user.status != "active":
            return False
        return await self._users.count(role=ADMIN_ROLE, status="active") <= 1
