"""Registro, login, sesión persistente (refresh), logout y bloqueo por intentos fallidos."""

from datetime import timedelta

import pytest

from src.models import utc_now
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, USER_PASSWORD, auth_headers, login

REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
REFRESH_URL = "/api/v1/auth/refresh"
LOGOUT_URL = "/api/v1/auth/logout"


# ── Registro ────────────────────────────────────────────────────────────────────
def test_registro_crea_la_cuenta_con_el_rol_por_defecto(client):
    response = client.post(
        REGISTER_URL,
        json={"name": "Ana Pérez", "email": "Ana@Example.com", "password": USER_PASSWORD},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "ana@example.com"  # normalizado a minúsculas
    assert body["role"] == "viewer"  # nunca se puede auto-asignar un rol
    assert body["status"] == "active"
    assert "password" not in body and "password_hash" not in body
    assert response.headers["location"] == f"/api/v1/users/{body['id']}"


def test_registro_ignora_un_rol_enviado_por_el_cliente(client):
    response = client.post(
        REGISTER_URL,
        json={
            "name": "Mal Actor",
            "email": "mal@example.com",
            "password": USER_PASSWORD,
            "role": "admin",
        },
    )

    assert response.status_code == 201
    assert response.json()["role"] == "viewer"


def test_registro_rechaza_correo_duplicado(client, register_user):
    register_user(email="ana@example.com")

    response = client.post(
        REGISTER_URL,
        json={"name": "Otra Ana", "email": "ANA@example.com", "password": USER_PASSWORD},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "email_taken"


@pytest.mark.parametrize(
    ("password", "motivo"),
    [("corta1", "menos de 8"), ("sololetrasaqui", "sin número"), ("12345678901", "sin letra")],
)
def test_registro_aplica_la_politica_de_contrasena(client, password, motivo):
    response = client.post(
        REGISTER_URL, json={"name": "Ana", "email": "ana@example.com", "password": password}
    )

    assert response.status_code == 422, motivo
    assert response.json()["errors"][0]["loc"] == ["body", "password"]


def test_registro_valida_el_formato_del_correo(client):
    response = client.post(
        REGISTER_URL, json={"name": "Ana", "email": "no-es-un-correo", "password": USER_PASSWORD}
    )

    assert response.status_code == 422


def test_registro_deshabilitado(make_app, settings):
    from fastapi.testclient import TestClient

    app = make_app(settings=settings.model_copy(update={"registration_enabled": False}))
    with TestClient(app) as client:
        response = client.post(
            REGISTER_URL,
            json={"name": "Ana", "email": "ana@example.com", "password": USER_PASSWORD},
        )

    assert response.status_code == 403
    assert response.json()["code"] == "registration_disabled"


# ── Login ───────────────────────────────────────────────────────────────────────
def test_login_devuelve_token_perfil_y_cookie_httponly(client):
    response = client.post(LOGIN_URL, json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 15 * 60
    assert body["user"]["email"] == ADMIN_EMAIL
    assert "users:read" in body["user"]["permissions"]
    assert "refresh" not in response.text.lower().replace("refresh token", "")  # no va en el cuerpo
    assert response.headers["cache-control"] == "no-store"

    cookie = response.headers["set-cookie"]
    assert "centynella_refresh=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Secure" not in cookie  # sandbox sobre http


def test_login_marca_la_cookie_secure_en_produccion(make_app, settings):
    from fastapi.testclient import TestClient

    prod = settings.model_copy(update={"app_env": "production"})
    with TestClient(make_app(settings=prod), base_url="https://testserver") as client:
        response = client.post(LOGIN_URL, json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})

    assert "Secure" in response.headers["set-cookie"]


def test_login_no_distingue_mayusculas_en_el_correo(client):
    response = client.post(
        LOGIN_URL, json={"email": "  ADMIN@Example.COM ", "password": ADMIN_PASSWORD}
    )

    assert response.status_code == 200


@pytest.mark.parametrize(
    ("email", "password"),
    [(ADMIN_EMAIL, "ClaveIncorrecta1"), ("nadie@example.com", ADMIN_PASSWORD)],
)
def test_login_con_credenciales_invalidas_da_el_mismo_error(client, email, password):
    response = client.post(LOGIN_URL, json={"email": email, "password": password})

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_credentials"  # no revela si el correo existe


def test_login_actualiza_last_login(client):
    body = login(client, ADMIN_EMAIL, ADMIN_PASSWORD)

    assert body["user"]["last_login_at"] is not None


def test_login_de_cuenta_deshabilitada(client, admin_headers, register_user):
    user = register_user()
    client.patch(f"/api/v1/users/{user['id']}", json={"status": "disabled"}, headers=admin_headers)

    response = client.post(LOGIN_URL, json={"email": "ana@example.com", "password": USER_PASSWORD})

    assert response.status_code == 403
    assert response.json()["code"] == "account_disabled"


def test_bloqueo_tras_demasiados_intentos_fallidos(client, register_user):
    register_user()
    for _ in range(5):
        response = client.post(
            LOGIN_URL, json={"email": "ana@example.com", "password": "Mala12345"}
        )
        assert response.status_code == 401

    # Ya bloqueada: incluso la contraseña CORRECTA se rechaza.
    response = client.post(LOGIN_URL, json={"email": "ana@example.com", "password": USER_PASSWORD})

    assert response.status_code == 429
    assert response.json()["code"] == "account_locked"
    assert int(response.headers["retry-after"]) > 0


def test_el_bloqueo_expira(client, repositories, register_user):
    user = register_user()
    for _ in range(5):
        client.post(LOGIN_URL, json={"email": "ana@example.com", "password": "Mala12345"})
    stored = repositories.users.items[user["id"]]
    stored.locked_until = utc_now() - timedelta(seconds=1)

    response = client.post(LOGIN_URL, json={"email": "ana@example.com", "password": USER_PASSWORD})

    assert response.status_code == 200


def test_un_login_correcto_reinicia_el_contador(client, repositories, register_user):
    user = register_user()
    for _ in range(3):
        client.post(LOGIN_URL, json={"email": "ana@example.com", "password": "Mala12345"})
    assert repositories.users.items[user["id"]].failed_login_attempts == 3

    login(client, "ana@example.com", USER_PASSWORD)

    assert repositories.users.items[user["id"]].failed_login_attempts == 0


# ── Sesión persistente: refresh ─────────────────────────────────────────────────
def test_refresh_restaura_la_sesion_desde_la_cookie(client):
    first = login(client, ADMIN_EMAIL, ADMIN_PASSWORD)

    response = client.post(REFRESH_URL)  # solo la cookie, sin Authorization

    assert response.status_code == 200
    assert response.json()["user"]["email"] == ADMIN_EMAIL
    assert response.json()["access_token"] != first["access_token"]


def test_refresh_sin_cookie_es_401(client):
    response = client.post(REFRESH_URL)

    assert response.status_code == 401
    assert response.json()["code"] == "no_session"


def test_refresh_con_cookie_desconocida_es_401(client):
    client.cookies.set("centynella_refresh", "token-que-no-existe", path="/api/v1")

    assert client.post(REFRESH_URL).status_code == 401


def test_refresh_rota_el_token(client):
    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    old_cookie = client.cookies.get("centynella_refresh")

    client.post(REFRESH_URL)

    assert client.cookies.get("centynella_refresh") != old_cookie


def test_reutilizar_un_token_rotado_revoca_toda_la_familia(client, settings, make_app):
    from fastapi.testclient import TestClient

    strict = settings.model_copy(update={"refresh_reuse_leeway_seconds": 0})
    with TestClient(make_app(settings=strict)) as strict_client:
        login(strict_client, ADMIN_EMAIL, ADMIN_PASSWORD)
        stolen = strict_client.cookies.get("centynella_refresh")
        strict_client.post(REFRESH_URL)  # el usuario legítimo rota el token
        current = strict_client.cookies.get("centynella_refresh")

        strict_client.cookies.set("centynella_refresh", stolen, path="/api/v1")
        assert strict_client.post(REFRESH_URL).status_code == 401  # el ladrón reusa el viejo

        strict_client.cookies.set("centynella_refresh", current, path="/api/v1")
        assert strict_client.post(REFRESH_URL).status_code == 401  # y la familia entera cayó


def test_dos_refresh_simultaneos_no_se_toman_por_robo(client):
    """Dos pestañas refrescando a la vez con la misma cookie: ambas deben funcionar (leeway)."""
    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    shared_cookie = client.cookies.get("centynella_refresh")

    assert client.post(REFRESH_URL).status_code == 200
    client.cookies.set("centynella_refresh", shared_cookie, path="/api/v1")

    assert client.post(REFRESH_URL).status_code == 200


def test_refresh_con_sesion_vencida(client, repositories):
    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    for token in repositories.refresh_tokens.items.values():
        token.expires_at = utc_now() - timedelta(seconds=1)

    response = client.post(REFRESH_URL)

    assert response.status_code == 401
    assert response.json()["code"] == "session_expired"


def test_refresh_falla_si_la_cuenta_fue_deshabilitada(client, repositories):
    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    admin = next(iter(repositories.users.items.values()))
    admin.status = "disabled"

    assert client.post(REFRESH_URL).status_code == 401


# ── Logout ──────────────────────────────────────────────────────────────────────
def test_logout_revoca_la_sesion_y_borra_la_cookie(client):
    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    cookie = client.cookies.get("centynella_refresh")

    response = client.post(LOGOUT_URL)

    assert response.status_code == 204
    assert "centynella_refresh=" in response.headers["set-cookie"]
    client.cookies.set("centynella_refresh", cookie, path="/api/v1")
    assert client.post(REFRESH_URL).status_code == 401  # el token ya no sirve


def test_logout_sin_sesion_no_falla(client):
    assert client.post(LOGOUT_URL).status_code == 204


# ── Access token ────────────────────────────────────────────────────────────────
def test_endpoint_protegido_sin_token(client):
    response = client.get("/api/v1/users/me")

    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"
    assert response.headers["www-authenticate"] == "Bearer"


def test_endpoint_protegido_con_token_invalido(client):
    response = client.get("/api/v1/users/me", headers=auth_headers("no.es.un.jwt"))

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_token"


def test_token_de_usuario_eliminado_deja_de_servir(client, admin_headers, register_user):
    user = register_user()
    token = login(client, "ana@example.com", USER_PASSWORD)["access_token"]
    client.delete(f"/api/v1/users/{user['id']}", headers=admin_headers)

    assert client.get("/api/v1/users/me", headers=auth_headers(token)).status_code == 401


def test_cuenta_deshabilitada_pierde_acceso_de_inmediato(client, admin_headers, register_user):
    user = register_user()
    token = login(client, "ana@example.com", USER_PASSWORD)["access_token"]
    client.patch(f"/api/v1/users/{user['id']}", json={"status": "disabled"}, headers=admin_headers)

    response = client.get("/api/v1/users/me", headers=auth_headers(token))

    assert response.status_code == 401
    assert response.json()["code"] == "account_disabled"


# ── Google (preparado) ──────────────────────────────────────────────────────────
def test_google_esta_preparado_pero_no_disponible(client):
    response = client.post("/api/v1/auth/oauth/google", json={"id_token": "token-de-google-falso"})

    assert response.status_code == 501
    assert response.json()["code"] == "google_not_available"
