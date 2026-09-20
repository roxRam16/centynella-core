"""Roles, permisos y el arranque (seed) de los roles de sistema."""

import pytest

from src.models import ADMIN_ROLE, SYSTEM_ROLES, Permission
from src.services import bootstrap_admin, seed_roles
from src.services.password_hasher import PasswordHasher
from tests.conftest import USER_PASSWORD, auth_headers, login
from tests.fakes import build_in_memory_repositories

ROLES_URL = "/api/v1/roles"


# ── Seed / arranque ─────────────────────────────────────────────────────────────
@pytest.mark.anyio
async def test_seed_crea_los_roles_de_sistema_y_es_idempotente():
    repositories = build_in_memory_repositories()

    await seed_roles(repositories)
    await seed_roles(repositories)

    keys = [role.key for role in await repositories.roles.list()]
    assert keys == sorted(r.key for r in SYSTEM_ROLES)
    assert all(role.is_system for role in await repositories.roles.list())


@pytest.mark.anyio
async def test_seed_no_pisa_los_cambios_de_un_rol_pero_si_sincroniza_admin():
    repositories = build_in_memory_repositories()
    await seed_roles(repositories)
    await repositories.roles.update("manager", {"permissions": ["users:read"]})
    await repositories.roles.update(
        ADMIN_ROLE, {"permissions": ["users:read"]}
    )  # admin "desactualizado"

    await seed_roles(repositories)

    manager = await repositories.roles.get("manager")
    admin = await repositories.roles.get(ADMIN_ROLE)
    assert manager.permissions == ["users:read"]  # ajuste del administrador respetado
    assert sorted(admin.permissions) == sorted(
        p.value for p in Permission
    )  # admin siempre completo


@pytest.mark.anyio
async def test_bootstrap_crea_el_primer_admin_solo_con_la_base_vacia(settings):
    repositories = build_in_memory_repositories()
    hasher = PasswordHasher()

    assert await bootstrap_admin(settings, repositories, hasher) is True
    assert await bootstrap_admin(settings, repositories, hasher) is False  # ya hay usuarios

    admin = await repositories.users.get_by_email("admin@example.com")
    assert admin.role == ADMIN_ROLE
    assert admin.password_hash != "Admin#12345"  # se guarda el hash, no la contraseña


@pytest.mark.anyio
async def test_bootstrap_no_hace_nada_sin_credenciales(settings):
    repositories = build_in_memory_repositories()
    sin_credenciales = settings.model_copy(update={"bootstrap_admin_email": None})

    assert await bootstrap_admin(sin_credenciales, repositories, PasswordHasher()) is False
    assert await repositories.users.count() == 0


# ── Catálogo y lectura ──────────────────────────────────────────────────────────
def test_catalogo_de_permisos(client, admin_headers):
    response = client.get("/api/v1/permissions", headers=admin_headers)

    assert response.status_code == 200
    keys = {item["key"] for item in response.json()}
    assert keys == {p.value for p in Permission}
    assert all(item["description"] for item in response.json())


def test_listar_y_ver_roles(client, admin_headers):
    roles = client.get(ROLES_URL, headers=admin_headers).json()

    assert {r["key"] for r in roles} == {"admin", "manager", "viewer"}
    admin = client.get(f"{ROLES_URL}/admin", headers=admin_headers).json()
    assert admin["is_system"] is True
    assert client.get(f"{ROLES_URL}/fantasma", headers=admin_headers).status_code == 404


# ── Crear / editar / eliminar ───────────────────────────────────────────────────
def test_crear_un_rol_personalizado(client, admin_headers):
    response = client.post(
        ROLES_URL,
        json={"key": "auditor", "name": "Auditor", "permissions": ["users:read", "users:read"]},
        headers=admin_headers,
    )

    assert response.status_code == 201
    assert response.json()["permissions"] == ["users:read"]  # sin duplicados
    assert response.json()["is_system"] is False
    assert response.headers["location"] == f"{ROLES_URL}/auditor"


def test_un_rol_nuevo_aplica_a_sus_usuarios_de_inmediato(client, admin_headers):
    client.post(
        ROLES_URL,
        json={"key": "auditor", "name": "Auditor", "permissions": ["users:read"]},
        headers=admin_headers,
    )
    client.post(
        "/api/v1/users",
        json={
            "name": "Aida",
            "email": "aida@example.com",
            "password": USER_PASSWORD,
            "role": "auditor",
        },
        headers=admin_headers,
    )
    token = login(client, "aida@example.com", USER_PASSWORD)["access_token"]
    headers = auth_headers(token)

    assert client.get("/api/v1/users", headers=headers).status_code == 200
    assert client.get("/api/v1/roles", headers=headers).status_code == 403

    # Se le añade un permiso al rol: efecto inmediato, sin volver a iniciar sesión.
    client.patch(
        f"{ROLES_URL}/auditor",
        json={"permissions": ["users:read", "roles:read"]},
        headers=admin_headers,
    )
    assert client.get("/api/v1/roles", headers=headers).status_code == 200


@pytest.mark.parametrize("key", ["Auditor", "1auditor", "a", "con espacio", "x" * 40])
def test_crear_rol_valida_la_clave(client, admin_headers, key):
    response = client.post(ROLES_URL, json={"key": key, "name": "Rol"}, headers=admin_headers)

    assert response.status_code == 422


def test_crear_rol_con_permiso_desconocido(client, admin_headers):
    response = client.post(
        ROLES_URL,
        json={"key": "raro", "name": "Raro", "permissions": ["cohetes:lanzar"]},
        headers=admin_headers,
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_permission"


def test_crear_rol_duplicado(client, admin_headers):
    response = client.post(
        ROLES_URL, json={"key": "manager", "name": "Otro"}, headers=admin_headers
    )

    assert response.status_code == 409
    assert response.json()["code"] == "role_exists"


def test_los_permisos_del_admin_no_se_pueden_modificar(client, admin_headers):
    response = client.patch(f"{ROLES_URL}/admin", json={"permissions": []}, headers=admin_headers)

    assert response.status_code == 403
    assert response.json()["code"] == "admin_role_locked"


def test_editar_nombre_de_un_rol_de_sistema(client, admin_headers):
    response = client.patch(f"{ROLES_URL}/manager", json={"name": "Jefe"}, headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["name"] == "Jefe"


def test_editar_exige_al_menos_un_campo(client, admin_headers):
    assert client.patch(f"{ROLES_URL}/manager", json={}, headers=admin_headers).status_code == 422


def test_eliminar_un_rol_personalizado(client, admin_headers):
    client.post(ROLES_URL, json={"key": "temporal", "name": "Temporal"}, headers=admin_headers)

    assert client.delete(f"{ROLES_URL}/temporal", headers=admin_headers).status_code == 204
    assert client.get(f"{ROLES_URL}/temporal", headers=admin_headers).status_code == 404


def test_no_se_eliminan_roles_de_sistema(client, admin_headers):
    response = client.delete(f"{ROLES_URL}/viewer", headers=admin_headers)

    assert response.status_code == 403
    assert response.json()["code"] == "system_role"


def test_no_se_elimina_un_rol_con_usuarios(client, admin_headers):
    client.post(ROLES_URL, json={"key": "temporal", "name": "Temporal"}, headers=admin_headers)
    client.post(
        "/api/v1/users",
        json={
            "name": "Tomás",
            "email": "tomas@example.com",
            "password": USER_PASSWORD,
            "role": "temporal",
        },
        headers=admin_headers,
    )

    response = client.delete(f"{ROLES_URL}/temporal", headers=admin_headers)

    assert response.status_code == 409
    assert response.json()["code"] == "role_in_use"


def test_gerente_no_puede_gestionar_roles(client, admin_headers):
    client.post(
        "/api/v1/users",
        json={
            "name": "Gina",
            "email": "gina@example.com",
            "password": USER_PASSWORD,
            "role": "manager",
        },
        headers=admin_headers,
    )
    headers = auth_headers(login(client, "gina@example.com", USER_PASSWORD)["access_token"])

    assert client.get(ROLES_URL, headers=headers).status_code == 200  # roles:read
    assert (
        client.post(ROLES_URL, json={"key": "nuevo", "name": "Nuevo"}, headers=headers).status_code
        == 403
    )
    assert client.delete(f"{ROLES_URL}/viewer", headers=headers).status_code == 403
