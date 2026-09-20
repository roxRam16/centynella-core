"""Perfil propio y administración de usuarios (con control de permisos)."""

import pytest

from tests.conftest import ADMIN_EMAIL, USER_PASSWORD, auth_headers, login

USERS_URL = "/api/v1/users"


def create_user(client, headers, **overrides) -> dict:
    payload = {
        "name": "Luis Gómez",
        "email": "luis@example.com",
        "password": USER_PASSWORD,
        "role": "viewer",
        **overrides,
    }
    response = client.post(USERS_URL, json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def user_manager_headers(client, admin_headers) -> dict[str, str]:
    """Cabeceras de un usuario que puede editar/eliminar usuarios pero NO es administrador."""
    client.post(
        "/api/v1/roles",
        json={
            "key": "gestor",
            "name": "Gestor de usuarios",
            "permissions": ["users:read", "users:update", "users:delete"],
        },
        headers=admin_headers,
    )
    create_user(client, admin_headers, name="Gestor", email="gestor@example.com", role="gestor")
    return auth_headers(login(client, "gestor@example.com", USER_PASSWORD)["access_token"])


# ── Perfil propio ───────────────────────────────────────────────────────────────
def test_mi_perfil_incluye_permisos(client, admin_headers):
    response = client.get(f"{USERS_URL}/me", headers=admin_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == ADMIN_EMAIL
    assert body["role"] == "admin"
    assert "users:delete" in body["permissions"]


def test_usuario_sin_privilegios_no_tiene_permisos(client, register_user):
    register_user()
    token = login(client, "ana@example.com", USER_PASSWORD)["access_token"]

    body = client.get(f"{USERS_URL}/me", headers=auth_headers(token)).json()

    assert body["role"] == "viewer"
    assert body["permissions"] == []


def test_editar_mi_perfil_solo_cambia_el_nombre(client, register_user):
    register_user()
    token = login(client, "ana@example.com", USER_PASSWORD)["access_token"]

    response = client.patch(
        f"{USERS_URL}/me",
        json={"name": "  Ana María  ", "role": "admin"},  # el rol enviado se ignora
        headers=auth_headers(token),
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Ana María"
    assert response.json()["role"] == "viewer"


def test_editar_mi_perfil_valida_el_nombre(client, admin_headers):
    response = client.patch(f"{USERS_URL}/me", json={"name": "A"}, headers=admin_headers)

    assert response.status_code == 422


# ── Autorización ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", USERS_URL),
        ("get", f"{USERS_URL}/x"),
        ("delete", f"{USERS_URL}/x"),
        ("get", "/api/v1/roles"),
    ],
)
def test_usuario_sin_permisos_recibe_403(client, register_user, method, path):
    register_user()
    token = login(client, "ana@example.com", USER_PASSWORD)["access_token"]

    response = getattr(client, method)(path, headers=auth_headers(token))

    assert response.status_code == 403
    assert response.json()["code"] == "insufficient_permissions"


def test_sin_token_recibe_401(client):
    assert client.get(USERS_URL).status_code == 401


def test_gerente_puede_ver_pero_no_modificar(client, admin_headers, register_user):
    target = register_user(email="ana@example.com")
    create_user(client, admin_headers, email="gerente@example.com", role="manager")
    token = login(client, "gerente@example.com", USER_PASSWORD)["access_token"]
    headers = auth_headers(token)

    assert client.get(USERS_URL, headers=headers).status_code == 200
    assert client.get(f"{USERS_URL}/{target['id']}", headers=headers).status_code == 200
    assert client.post(USERS_URL, json={}, headers=headers).status_code == 403
    assert (
        client.patch(
            f"{USERS_URL}/{target['id']}", json={"name": "X X"}, headers=headers
        ).status_code
        == 403
    )
    assert client.delete(f"{USERS_URL}/{target['id']}", headers=headers).status_code == 403


# ── Listado ─────────────────────────────────────────────────────────────────────
def test_listado_paginado(client, admin_headers):
    for index in range(4):
        create_user(client, admin_headers, name=f"Usuario {index}", email=f"u{index}@example.com")

    page1 = client.get(USERS_URL, params={"page": 1, "page_size": 3}, headers=admin_headers).json()
    page2 = client.get(USERS_URL, params={"page": 2, "page_size": 3}, headers=admin_headers).json()

    assert page1["total"] == 5  # 4 + el administrador
    assert len(page1["items"]) == 3
    assert len(page2["items"]) == 2
    assert page1["page"] == 1 and page1["page_size"] == 3
    assert "password_hash" not in page1["items"][0]


def test_listado_filtra_por_texto_rol_y_estado(client, admin_headers):
    create_user(client, admin_headers, name="Carla Ruiz", email="carla@example.com", role="manager")
    create_user(
        client, admin_headers, name="Diego Paz", email="diego@example.com", status="disabled"
    )

    by_text = client.get(USERS_URL, params={"q": "carla"}, headers=admin_headers).json()
    by_role = client.get(USERS_URL, params={"role": "manager"}, headers=admin_headers).json()
    by_status = client.get(USERS_URL, params={"status": "disabled"}, headers=admin_headers).json()

    assert [u["email"] for u in by_text["items"]] == ["carla@example.com"]
    assert [u["email"] for u in by_role["items"]] == ["carla@example.com"]
    assert [u["email"] for u in by_status["items"]] == ["diego@example.com"]


@pytest.mark.parametrize(
    "params", [{"page": 0}, {"page_size": 0}, {"page_size": 101}, {"status": "raro"}]
)
def test_listado_valida_parametros(client, admin_headers, params):
    assert client.get(USERS_URL, params=params, headers=admin_headers).status_code == 422


# ── Crear / ver ─────────────────────────────────────────────────────────────────
def test_admin_crea_un_usuario_con_rol(client, admin_headers):
    response = client.post(
        USERS_URL,
        json={
            "name": "Marta",
            "email": "marta@example.com",
            "password": USER_PASSWORD,
            "role": "manager",
        },
        headers=admin_headers,
    )

    assert response.status_code == 201
    assert response.json()["role"] == "manager"
    assert response.headers["location"] == f"{USERS_URL}/{response.json()['id']}"
    assert login(client, "marta@example.com", USER_PASSWORD)["user"]["role"] == "manager"


def test_crear_usuario_con_rol_inexistente(client, admin_headers):
    response = client.post(
        USERS_URL,
        json={
            "name": "Marta",
            "email": "marta@example.com",
            "password": USER_PASSWORD,
            "role": "fantasma",
        },
        headers=admin_headers,
    )

    assert response.status_code == 422
    assert response.json()["code"] == "role_not_found"


def test_crear_usuario_con_correo_repetido(client, admin_headers):
    create_user(client, admin_headers)

    response = client.post(
        USERS_URL,
        json={
            "name": "Otro",
            "email": "LUIS@example.com",
            "password": USER_PASSWORD,
            "role": "viewer",
        },
        headers=admin_headers,
    )

    assert response.status_code == 409


def test_ver_un_usuario_y_404(client, admin_headers):
    user = create_user(client, admin_headers)

    assert (
        client.get(f"{USERS_URL}/{user['id']}", headers=admin_headers).json()["email"]
        == "luis@example.com"
    )
    missing = client.get(f"{USERS_URL}/no-existe", headers=admin_headers)
    assert missing.status_code == 404
    assert missing.json()["code"] == "user_not_found"


# ── Editar ──────────────────────────────────────────────────────────────────────
def test_admin_edita_nombre_y_rol(client, admin_headers):
    user = create_user(client, admin_headers)

    response = client.patch(
        f"{USERS_URL}/{user['id']}",
        json={"name": "Luis Editado", "role": "manager"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Luis Editado"
    assert response.json()["role"] == "manager"


def test_editar_exige_al_menos_un_campo(client, admin_headers):
    user = create_user(client, admin_headers)

    assert (
        client.patch(f"{USERS_URL}/{user['id']}", json={}, headers=admin_headers).status_code == 422
    )


def test_editar_a_un_rol_inexistente(client, admin_headers):
    user = create_user(client, admin_headers)

    response = client.patch(
        f"{USERS_URL}/{user['id']}", json={"role": "fantasma"}, headers=admin_headers
    )

    assert response.status_code == 422


def test_deshabilitar_cierra_las_sesiones_del_usuario(client, admin_headers):
    user = create_user(client, admin_headers)
    login(client, "luis@example.com", USER_PASSWORD)
    client.patch(f"{USERS_URL}/{user['id']}", json={"status": "disabled"}, headers=admin_headers)

    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_no_puedes_cambiar_tu_propio_rol_ni_estado(client, admin_headers):
    me = client.get(f"{USERS_URL}/me", headers=admin_headers).json()

    response = client.patch(
        f"{USERS_URL}/{me['id']}", json={"role": "viewer"}, headers=admin_headers
    )

    assert response.status_code == 409
    assert response.json()["code"] == "self_modification"


# ── Regla del último administrador activo ───────────────────────────────────────
def admin_id(client, admin_headers) -> str:
    return client.get(f"{USERS_URL}/me", headers=admin_headers).json()["id"]


@pytest.mark.parametrize("changes", [{"role": "viewer"}, {"status": "disabled"}])
def test_no_se_puede_degradar_ni_deshabilitar_al_ultimo_administrador(
    client, admin_headers, changes
):
    gestor = user_manager_headers(client, admin_headers)

    response = client.patch(
        f"{USERS_URL}/{admin_id(client, admin_headers)}", json=changes, headers=gestor
    )

    assert response.status_code == 409
    assert response.json()["code"] == "last_admin"


def test_no_se_puede_eliminar_al_ultimo_administrador(client, admin_headers):
    gestor = user_manager_headers(client, admin_headers)

    response = client.delete(f"{USERS_URL}/{admin_id(client, admin_headers)}", headers=gestor)

    assert response.status_code == 409
    assert response.json()["code"] == "last_admin"


def test_si_hay_otro_administrador_activo_si_se_puede(client, admin_headers):
    gestor = user_manager_headers(client, admin_headers)
    create_user(
        client, admin_headers, name="Segundo Admin", email="segundo@example.com", role="admin"
    )

    response = client.patch(
        f"{USERS_URL}/{admin_id(client, admin_headers)}", json={"role": "viewer"}, headers=gestor
    )

    assert response.status_code == 200
    assert response.json()["role"] == "viewer"


def test_un_administrador_deshabilitado_no_cuenta_como_activo(client, admin_headers):
    """Con dos admins pero uno deshabilitado, el activo restante es "el último"."""
    gestor = user_manager_headers(client, admin_headers)
    second = create_user(
        client, admin_headers, name="Segundo Admin", email="segundo@example.com", role="admin"
    )
    client.patch(f"{USERS_URL}/{second['id']}", json={"status": "disabled"}, headers=gestor)

    response = client.delete(f"{USERS_URL}/{admin_id(client, admin_headers)}", headers=gestor)

    assert response.status_code == 409


# ── Eliminar ────────────────────────────────────────────────────────────────────
def test_admin_elimina_un_usuario_y_cierra_sus_sesiones(client, admin_headers):
    user = create_user(client, admin_headers)
    login(client, "luis@example.com", USER_PASSWORD)

    response = client.delete(f"{USERS_URL}/{user['id']}", headers=admin_headers)

    assert response.status_code == 204
    assert client.get(f"{USERS_URL}/{user['id']}", headers=admin_headers).status_code == 404
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_no_puedes_eliminarte_a_ti_mismo(client, admin_headers):
    me = client.get(f"{USERS_URL}/me", headers=admin_headers).json()

    response = client.delete(f"{USERS_URL}/{me['id']}", headers=admin_headers)

    assert response.status_code == 409
    assert response.json()["code"] == "self_modification"


def test_eliminar_un_usuario_inexistente(client, admin_headers):
    assert client.delete(f"{USERS_URL}/no-existe", headers=admin_headers).status_code == 404
