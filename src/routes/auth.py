"""Endpoints de autenticación.

Sesión: el *access token* (JWT, 15 min) viaja en el cuerpo y el frontend lo guarda en memoria;
el *refresh token* viaja SOLO en una cookie HttpOnly (JavaScript no puede leerla → un XSS no
puede robar la sesión). `SameSite=Lax` impide que otros sitios la envíen (protección CSRF).
"""

from fastapi import APIRouter, Request, Response, status

from src.config import Settings
from src.dtos import (
    GoogleLoginRequest,
    LoginRequest,
    PasswordResetCreate,
    PasswordResetRequestCreate,
    ProblemDetailsDTO,
    ProfileDTO,
    RegisterRequest,
    TokenResponse,
    UserDTO,
)
from src.routes.dependencies import ServicesDep, SettingsDep
from src.services import AuthSession, Services
from src.services.errors import AuthenticationError

router = APIRouter(prefix="/auth", tags=["Authentication"])

REFRESH_COOKIE = "centynella_refresh"
_COOKIE_PATH = "/api/v1"
_NO_STORE = "no-store"

_ERR_401 = {"model": ProblemDetailsDTO, "description": "Credenciales o sesión inválidas."}


def set_refresh_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=settings.refresh_token_ttl_days * 24 * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path=_COOKIE_PATH,
    )


def clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        REFRESH_COOKIE,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path=_COOKIE_PATH,
    )


async def build_token_response(
    session: AuthSession, response: Response, services: Services, settings: Settings
) -> TokenResponse:
    """Arma la respuesta de sesión y coloca la cookie del refresh token."""
    set_refresh_cookie(response, session.refresh_token, settings)
    response.headers["Cache-Control"] = _NO_STORE
    permissions = await services.users.permissions_of(session.user)
    return TokenResponse(
        access_token=session.access_token,
        expires_in=session.expires_in,
        user=ProfileDTO.from_user(session.user, permissions),
    )


@router.post(
    "/register",
    response_model=UserDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar una cuenta",
    description="Registro público. La cuenta se crea con el rol por defecto (sin privilegios). "
    "Después hay que iniciar sesión con `POST /auth/login`.",
    responses={
        409: {"model": ProblemDetailsDTO, "description": "El correo ya está registrado."},
        403: {"model": ProblemDetailsDTO, "description": "El registro está deshabilitado."},
    },
)
async def register(body: RegisterRequest, response: Response, services: ServicesDep) -> UserDTO:
    user = await services.auth.register(body.name, body.email, body.password)
    response.headers["Location"] = f"/api/v1/users/{user.id}"
    return UserDTO.from_document(user)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Iniciar sesión",
    description="Devuelve el access token y deja el refresh token en una cookie HttpOnly. "
    "Tras 5 intentos fallidos la cuenta se bloquea 15 minutos (429).",
    responses={
        401: _ERR_401,
        403: {"model": ProblemDetailsDTO, "description": "Cuenta deshabilitada."},
        429: {"model": ProblemDetailsDTO, "description": "Cuenta bloqueada temporalmente."},
    },
)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    services: ServicesDep,
    settings: SettingsDep,
) -> TokenResponse:
    session = await services.auth.login(
        body.email, body.password, request.headers.get("user-agent")
    )
    return await build_token_response(session, response, services, settings)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Renovar la sesión",
    description="Usa la cookie del refresh token (que rota en cada uso) para emitir un nuevo "
    "access token. El frontend lo llama al abrir la app para **restaurar la sesión**.",
    responses={401: _ERR_401},
)
async def refresh(
    request: Request, response: Response, services: ServicesDep, settings: SettingsDep
) -> TokenResponse:
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise AuthenticationError("No hay una sesión activa.", code="no_session")
    session = await services.auth.refresh(token, request.headers.get("user-agent"))
    return await build_token_response(session, response, services, settings)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cerrar sesión",
    description="Revoca la sesión del dispositivo y borra la cookie. Es idempotente.",
)
async def logout(
    request: Request, response: Response, services: ServicesDep, settings: SettingsDep
) -> None:
    await services.auth.logout(request.cookies.get(REFRESH_COOKIE))
    clear_refresh_cookie(response, settings)


@router.post(
    "/password-reset-requests",
    status_code=status.HTTP_202_ACCEPTED,
    response_class=Response,  # cuerpo vacío
    summary="Solicitar recuperación de contraseña",
    description="Envía un enlace de recuperación al correo. **Siempre responde 202**, exista o no "
    "la cuenta, para no revelar qué correos están registrados.",
)
async def request_password_reset(body: PasswordResetRequestCreate, services: ServicesDep) -> None:
    await services.auth.request_password_reset(body.email)


@router.post(
    "/password-resets",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Restablecer la contraseña",
    description="Cambia la contraseña con el token del correo (un solo uso, vence en 60 min) "
    "y cierra todas las sesiones de la cuenta.",
    responses={400: {"model": ProblemDetailsDTO, "description": "Token inválido o vencido."}},
)
async def reset_password(body: PasswordResetCreate, services: ServicesDep) -> None:
    await services.auth.reset_password(body.token, body.password)


@router.post(
    "/oauth/google",
    response_model=TokenResponse,
    summary="Iniciar sesión con Google (preparado)",
    description="**Aún no disponible** (501). El contrato ya está definido para cuando se active.",
    responses={501: {"model": ProblemDetailsDTO, "description": "Todavía no implementado."}},
)
async def login_with_google(body: GoogleLoginRequest, services: ServicesDep) -> TokenResponse:
    await services.auth.login_with_google(body.id_token)
    raise AssertionError("unreachable")  # pragma: no cover - el servicio siempre lanza 501
