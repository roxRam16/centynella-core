"""Autenticación: registro, login, sesiones (refresh), recuperación y cambio de contraseña."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from src.config import Settings
from src.database import DuplicateError, Repositories
from src.middlewares.context import bind_user
from src.models import (
    PasswordResetDocument,
    RefreshTokenDocument,
    UserDocument,
    new_id,
    utc_now,
)
from src.services.email_sender import EmailSender, build_password_reset_email
from src.services.errors import (
    AuthenticationError,
    BadRequestError,
    ConflictError,
    FeatureNotAvailableError,
    NotFoundError,
    PermissionDeniedError,
    TooManyAttemptsError,
)
from src.services.event_logger import EventLogger, mask_email
from src.services.password_hasher import PasswordHasher
from src.services.token_service import TokenService

logger = logging.getLogger(__name__)

_INVALID_CREDENTIALS = "Correo o contraseña incorrectos."


@dataclass
class AuthSession:
    """Resultado de iniciar/renovar sesión."""

    user: UserDocument
    access_token: str
    expires_in: int
    refresh_token: str  # en claro: la ruta lo pone en la cookie HttpOnly
    session_id: str  # identifica la sesión de este dispositivo (bitácora)


class AuthService:
    def __init__(
        self,
        settings: Settings,
        repositories: Repositories,
        hasher: PasswordHasher,
        tokens: TokenService,
        email_sender: EmailSender,
        events: EventLogger,
    ) -> None:
        self._settings = settings
        self._events = events
        self._users = repositories.users
        self._roles = repositories.roles
        self._refresh_tokens = repositories.refresh_tokens
        self._resets = repositories.password_resets
        self._hasher = hasher
        self._tokens = tokens
        self._email = email_sender

    # ── Registro ─────────────────────────────────────────────────────────────
    async def register(self, name: str, email: str, password: str) -> UserDocument:
        """Registro público: el usuario siempre recibe el rol por defecto (sin privilegios)."""
        if not self._settings.registration_enabled:
            raise PermissionDeniedError(
                "El registro de usuarios está deshabilitado.", code="registration_disabled"
            )
        if await self._roles.get(self._settings.default_role) is None:
            raise NotFoundError("El rol por defecto no existe.", code="default_role_missing")

        user = UserDocument(
            email=email,
            name=name,
            password_hash=await self._hasher.hash(password),
            role=self._settings.default_role,
        )
        try:
            created = await self._users.create(user)
        except DuplicateError as error:
            self._events.warning(
                "auth",
                "auth.register.duplicate",
                "Registro con un correo ya usado",
                email=mask_email(email),
            )
            raise ConflictError(
                "Ya existe una cuenta con ese correo.", code="email_taken"
            ) from error
        self._events.info(
            "auth",
            "auth.register.success",
            "Cuenta registrada",
            user_id=created.id,
            role=created.role,
        )
        return created

    # ── Login / sesión ───────────────────────────────────────────────────────
    async def login(self, email: str, password: str, user_agent: str | None = None) -> AuthSession:
        user = await self._users.get_by_email(email)
        if user is None or user.password_hash is None:
            await self._hasher.verify_dummy(password)
            self._events.warning(
                "auth",
                "auth.login.failed",
                "Intento de login fallido",
                reason="unknown_user",
                email=mask_email(email),
            )
            raise AuthenticationError(_INVALID_CREDENTIALS, code="invalid_credentials")

        now = utc_now()
        if user.locked_until and user.locked_until > now:
            retry_after = int((user.locked_until - now).total_seconds()) + 1
            self._events.warning(
                "auth",
                "auth.login.rejected_locked",
                "Login rechazado: cuenta bloqueada",
                user_id=user.id,
                retry_after=retry_after,
            )
            raise TooManyAttemptsError(
                "Demasiados intentos fallidos. Intenta de nuevo más tarde.",
                code="account_locked",
                headers={"Retry-After": str(retry_after)},
            )

        if not await self._hasher.verify(user.password_hash, password):
            await self._register_failed_login(user, now)
            self._events.warning(
                "auth",
                "auth.login.failed",
                "Intento de login fallido",
                reason="bad_password",
                user_id=user.id,
                email=mask_email(email),
            )
            raise AuthenticationError(_INVALID_CREDENTIALS, code="invalid_credentials")

        if user.status != "active":
            self._events.warning(
                "auth",
                "auth.login.rejected_disabled",
                "Login rechazado: cuenta deshabilitada",
                user_id=user.id,
            )
            raise PermissionDeniedError("Tu cuenta está deshabilitada.", code="account_disabled")

        changes: dict = {"failed_login_attempts": 0, "locked_until": None, "last_login_at": now}
        if self._hasher.needs_rehash(user.password_hash):
            changes["password_hash"] = await self._hasher.hash(password)
        user = await self._users.update(user.id or "", changes) or user
        session = await self._open_session(user, family_id=new_id(), user_agent=user_agent)
        self._events.info(
            "auth",
            "auth.login.success",
            "Sesión iniciada",
            user_id=user.id,
            session_id=session.session_id,
        )
        return session

    async def refresh(self, refresh_token: str, user_agent: str | None = None) -> AuthSession:
        """Rota el refresh token: entrega uno nuevo y revoca el usado."""
        stored = await self._refresh_tokens.get_by_hash(self._tokens.hash_token(refresh_token))
        if stored is None:
            self._events.warning("auth", "auth.session.invalid", "Refresh con un token desconocido")
            raise AuthenticationError("Sesión inválida.", code="invalid_session")

        now = utc_now()
        if stored.revoked_at is not None and not self._within_reuse_leeway(stored, now):
            # Token revocado o rotado hace tiempo reutilizado: posible robo → se cierra la familia.
            await self._refresh_tokens.revoke_family(stored.family_id)
            self._events.warning(
                "security",
                "auth.session.reuse_detected",
                "Reutilización de un refresh token: posible robo, sesión revocada",
                user_id=stored.user_id,
                session_id=stored.family_id,
            )
            raise AuthenticationError("Sesión inválida.", code="invalid_session")
        if stored.expires_at <= now:
            raise AuthenticationError("La sesión expiró.", code="session_expired")

        user = await self._users.get(stored.user_id)
        if user is None or user.status != "active":
            await self._refresh_tokens.revoke_family(stored.family_id)
            raise AuthenticationError("Sesión inválida.", code="invalid_session")

        await self._refresh_tokens.rotate(stored.id or "")
        session = await self._open_session(user, family_id=stored.family_id, user_agent=user_agent)
        self._events.debug(
            "auth",
            "auth.session.refreshed",
            "Sesión renovada",
            user_id=user.id,
            session_id=session.session_id,
        )
        return session

    async def logout(self, refresh_token: str | None) -> None:
        """Cierra la sesión del dispositivo. Es idempotente: nunca falla."""
        if not refresh_token:
            return
        stored = await self._refresh_tokens.get_by_hash(self._tokens.hash_token(refresh_token))
        if stored is not None:
            await self._refresh_tokens.revoke_family(stored.family_id)
            self._events.info(
                "auth",
                "auth.logout",
                "Sesión cerrada",
                user_id=stored.user_id,
                session_id=stored.family_id,
            )

    async def login_with_google(self, id_token: str) -> AuthSession:
        """PREPARADO, aún sin implementar.

        Para completarlo: verificar `id_token` con la librería `google-auth` contra
        `settings.google_client_id`, buscar/crear el usuario por `AuthProviderLink(
        provider="google", subject=<sub>)` (rol por defecto) y llamar a `_open_session`.
        """
        raise FeatureNotAvailableError(
            "El inicio de sesión con Google todavía no está disponible.",
            code="google_not_available",
        )

    # ── Contraseña ───────────────────────────────────────────────────────────
    async def request_password_reset(self, email: str) -> None:
        """Genera y envía el enlace de recuperación. SIEMPRE termina igual exista o no el correo
        (así no se puede averiguar qué correos están registrados)."""
        user = await self._users.get_by_email(email)
        if user is None or user.status != "active":
            self._events.info(
                "auth",
                "auth.password.reset_requested",
                "Recuperación solicitada",
                known=False,
                email=mask_email(email),
            )
            return

        self._events.info(
            "auth",
            "auth.password.reset_requested",
            "Recuperación solicitada",
            known=True,
            user_id=user.id,
        )
        await self._resets.invalidate_for_user(user.id or "")
        raw, token_hash = self._tokens.generate_opaque_token()
        ttl = self._settings.password_reset_ttl_minutes
        await self._resets.create(
            PasswordResetDocument(
                user_id=user.id or "",
                token_hash=token_hash,
                expires_at=utc_now() + timedelta(minutes=ttl),
            )
        )
        link = f"{self._settings.frontend_url.rstrip('/')}/reset-password?token={raw}"
        subject, body = build_password_reset_email(user.name, link, ttl)
        try:
            await self._email.send(user.email, subject, body)
        except Exception:
            # Un fallo del proveedor de correo no debe revelar si el usuario existe.
            logger.exception("No se pudo enviar el correo de recuperación")

    async def reset_password(self, token: str, new_password: str) -> None:
        reset = await self._resets.get_by_hash(self._tokens.hash_token(token))
        if reset is None or reset.used_at is not None or reset.expires_at <= utc_now():
            self._events.warning(
                "auth", "auth.password.reset_invalid", "Restablecimiento con un token inválido"
            )
            raise BadRequestError(
                "El enlace no es válido o ya expiró. Solicita uno nuevo.",
                code="invalid_reset_token",
            )
        user = await self._users.get(reset.user_id)
        if user is None:
            raise BadRequestError("El enlace no es válido.", code="invalid_reset_token")

        await self._users.update(
            user.id or "",
            {
                "password_hash": await self._hasher.hash(new_password),
                "failed_login_attempts": 0,
                "locked_until": None,
            },
        )
        await self._resets.mark_used(reset.id or "")
        await self._refresh_tokens.revoke_all_for_user(user.id or "")
        self._events.info(
            "auth", "auth.password.reset_completed", "Contraseña restablecida", user_id=user.id
        )

    async def change_password(
        self, user: UserDocument, current_password: str, new_password: str
    ) -> AuthSession:
        """Cambia la contraseña, cierra las demás sesiones y abre una nueva en este dispositivo."""
        if user.password_hash is None or not await self._hasher.verify(
            user.password_hash, current_password
        ):
            self._events.warning(
                "auth",
                "auth.password.change_failed",
                "Cambio de contraseña: clave actual errónea",
                user_id=user.id,
            )
            raise AuthenticationError(
                "La contraseña actual es incorrecta.", code="invalid_current_password"
            )
        updated = await self._users.update(
            user.id or "", {"password_hash": await self._hasher.hash(new_password)}
        )
        await self._refresh_tokens.revoke_all_for_user(user.id or "")
        self._events.info("auth", "auth.password.changed", "Contraseña cambiada", user_id=user.id)
        return await self._open_session(updated or user, family_id=new_id(), user_agent=None)

    # ── Internos ─────────────────────────────────────────────────────────────
    async def _open_session(
        self, user: UserDocument, *, family_id: str, user_agent: str | None
    ) -> AuthSession:
        access_token, expires_in = self._tokens.create_access_token(user.id or "", family_id)
        bind_user(user.id, family_id)  # el log de acceso de esta petición ya lleva usuario y sesión
        raw, token_hash = self._tokens.generate_opaque_token()
        await self._refresh_tokens.create(
            RefreshTokenDocument(
                user_id=user.id or "",
                token_hash=token_hash,
                family_id=family_id,
                expires_at=utc_now() + timedelta(days=self._settings.refresh_token_ttl_days),
                user_agent=(user_agent or "")[:255] or None,
            )
        )
        return AuthSession(user, access_token, expires_in, raw, session_id=family_id)

    async def _register_failed_login(self, user: UserDocument, now: datetime) -> None:
        attempts = user.failed_login_attempts + 1
        changes: dict = {"failed_login_attempts": attempts}
        if attempts >= self._settings.max_failed_logins:
            changes["failed_login_attempts"] = 0
            changes["locked_until"] = now + timedelta(minutes=self._settings.lockout_minutes)
            self._events.warning(
                "security",
                "auth.login.locked_out",
                f"Cuenta bloqueada tras {attempts} intentos fallidos",
                user_id=user.id,
                lockout_minutes=self._settings.lockout_minutes,
            )
        await self._users.update(user.id or "", changes)

    def _within_reuse_leeway(self, token: RefreshTokenDocument, now: datetime) -> bool:
        """Solo un token ROTADO hace instantes cuenta como carrera legítima (dos pestañas).
        Uno revocado por logout, cambio de contraseña o robo detectado nunca se perdona."""
        leeway = timedelta(seconds=self._settings.refresh_reuse_leeway_seconds)
        return token.rotated_at is not None and now - token.rotated_at <= leeway
