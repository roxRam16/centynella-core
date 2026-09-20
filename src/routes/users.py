"""Endpoints de usuarios: perfil propio (`/users/me`) y administración."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from src.dtos import (
    PasswordChangeRequest,
    ProblemDetailsDTO,
    ProfileDTO,
    ProfileUpdateRequest,
    TokenResponse,
    UserCreateRequest,
    UserDTO,
    UserPageDTO,
    UserUpdateRequest,
)
from src.models import Permission, UserStatus
from src.routes.auth import build_token_response
from src.routes.dependencies import (
    CurrentUser,
    CurrentUserDep,
    ServicesDep,
    SettingsDep,
    require_permission,
)

router = APIRouter(prefix="/users", tags=["Users"])

_E401 = {"model": ProblemDetailsDTO, "description": "No autenticado."}
_E403 = {"model": ProblemDetailsDTO, "description": "Sin permiso para esta acción."}
_E404 = {"model": ProblemDetailsDTO, "description": "Usuario no encontrado."}
_E409 = {"model": ProblemDetailsDTO, "description": "Conflicto con una regla de negocio."}


# ── Perfil propio (debe declararse ANTES de `/{user_id}`) ───────────────────────
@router.get(
    "/me",
    response_model=ProfileDTO,
    summary="Ver mi perfil",
    responses={401: _E401},
)
async def get_my_profile(current: CurrentUserDep) -> ProfileDTO:
    return ProfileDTO.from_user(current.user, current.permissions)


@router.patch(
    "/me",
    response_model=ProfileDTO,
    summary="Editar mi perfil",
    description="Solo datos personales (nombre). El rol y el estado los cambia un administrador.",
    responses={401: _E401},
)
async def update_my_profile(
    body: ProfileUpdateRequest, current: CurrentUserDep, services: ServicesDep
) -> ProfileDTO:
    user = await services.users.update_profile(current.id, name=body.name)
    return ProfileDTO.from_user(user, current.permissions)


@router.put(
    "/me/password",
    response_model=TokenResponse,
    summary="Cambiar mi contraseña",
    description="Exige la contraseña actual. Cierra las demás sesiones y devuelve una nueva "
    "para este dispositivo.",
    responses={401: _E401},
)
async def change_my_password(
    body: PasswordChangeRequest,
    current: CurrentUserDep,
    response: Response,
    services: ServicesDep,
    settings: SettingsDep,
) -> TokenResponse:
    session = await services.auth.change_password(
        current.user, body.current_password, body.new_password
    )
    return await build_token_response(session, response, services, settings)


# ── Administración de usuarios ──────────────────────────────────────────────────
@router.get(
    "",
    response_model=UserPageDTO,
    summary="Listar usuarios",
    description="Paginado, con búsqueda por nombre o correo y filtros por rol y estado. "
    "Requiere `users:read`.",
    dependencies=[Depends(require_permission(Permission.USERS_READ))],
    responses={401: _E401, 403: _E403},
)
async def list_users(
    services: ServicesDep,
    q: Annotated[str | None, Query(max_length=100, description="Busca en nombre y correo.")] = None,
    role: Annotated[str | None, Query(description="Filtra por clave de rol.")] = None,
    status_: Annotated[UserStatus | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> UserPageDTO:
    users, total = await services.users.list(
        query=q, role=role, status=status_, page=page, page_size=page_size
    )
    return UserPageDTO(
        items=[UserDTO.from_document(u) for u in users], total=total, page=page, page_size=page_size
    )


@router.post(
    "",
    response_model=UserDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un usuario",
    description="Un administrador crea la cuenta y le asigna rol. Requiere `users:create`.",
    responses={401: _E401, 403: _E403, 409: _E409},
)
async def create_user(
    body: UserCreateRequest,
    response: Response,
    services: ServicesDep,
    _: Annotated[CurrentUser, Depends(require_permission(Permission.USERS_CREATE))],
) -> UserDTO:
    user = await services.users.create(
        name=body.name,
        email=body.email,
        password=body.password,
        role=body.role,
        status=body.status,
    )
    response.headers["Location"] = f"/api/v1/users/{user.id}"
    return UserDTO.from_document(user)


@router.get(
    "/{user_id}",
    response_model=UserDTO,
    summary="Ver un usuario",
    dependencies=[Depends(require_permission(Permission.USERS_READ))],
    responses={401: _E401, 403: _E403, 404: _E404},
)
async def get_user(user_id: str, services: ServicesDep) -> UserDTO:
    return UserDTO.from_document(await services.users.get(user_id))


@router.patch(
    "/{user_id}",
    response_model=UserDTO,
    summary="Editar un usuario",
    description="Nombre, rol o estado. No puedes cambiar tu propio rol/estado ni dejar el "
    "sistema sin administradores activos. Deshabilitar a alguien cierra sus sesiones. "
    "Requiere `users:update`.",
    responses={401: _E401, 403: _E403, 404: _E404, 409: _E409},
)
async def update_user(
    user_id: str,
    body: UserUpdateRequest,
    services: ServicesDep,
    current: Annotated[CurrentUser, Depends(require_permission(Permission.USERS_UPDATE))],
) -> UserDTO:
    user = await services.users.update(
        current.id, user_id, name=body.name, role=body.role, status=body.status
    )
    return UserDTO.from_document(user)


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar un usuario",
    description="No puedes eliminarte a ti mismo ni al último administrador activo. "
    "Requiere `users:delete`.",
    responses={401: _E401, 403: _E403, 404: _E404, 409: _E409},
)
async def delete_user(
    user_id: str,
    services: ServicesDep,
    current: Annotated[CurrentUser, Depends(require_permission(Permission.USERS_DELETE))],
) -> None:
    await services.users.delete(current.id, user_id)
