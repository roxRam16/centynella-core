"""Recuperación de contraseña por correo y cambio de contraseña autenticado."""

from datetime import timedelta

from src.models import utc_now
from tests.conftest import USER_PASSWORD, auth_headers, login

REQUEST_URL = "/api/v1/auth/password-reset-requests"
RESET_URL = "/api/v1/auth/password-resets"
NEW_PASSWORD = "NuevaClave987"


def test_solicitud_envia_el_enlace_al_correo(client, outbox, register_user):
    register_user()

    response = client.post(REQUEST_URL, json={"email": "ana@example.com"})

    assert response.status_code == 202
    assert response.content == b""
    assert len(outbox.sent) == 1
    assert outbox.sent[0]["to"] == "ana@example.com"
    assert "http://localhost:5173/reset-password?token=" in outbox.sent[0]["body"]


def test_solicitud_responde_igual_si_el_correo_no_existe(client, outbox):
    response = client.post(REQUEST_URL, json={"email": "nadie@example.com"})

    assert response.status_code == 202  # no revela qué correos están registrados
    assert outbox.sent == []


def test_solicitud_no_falla_si_el_correo_no_se_puede_enviar(client, outbox, register_user):
    register_user()
    outbox.fail = True

    assert client.post(REQUEST_URL, json={"email": "ana@example.com"}).status_code == 202


def test_no_se_guarda_el_token_en_claro(client, outbox, repositories, register_user):
    register_user()
    client.post(REQUEST_URL, json={"email": "ana@example.com"})
    token = outbox.last_reset_token()

    assert all(
        token not in reset.token_hash for reset in repositories.password_resets.items.values()
    )


def test_restablecer_cambia_la_contrasena_y_cierra_sesiones(client, outbox, register_user):
    register_user()
    login(client, "ana@example.com", USER_PASSWORD)  # sesión abierta antes del reset
    client.post(REQUEST_URL, json={"email": "ana@example.com"})

    response = client.post(
        RESET_URL, json={"token": outbox.last_reset_token(), "password": NEW_PASSWORD}
    )

    assert response.status_code == 204
    assert client.post("/api/v1/auth/refresh").status_code == 401  # sesiones revocadas
    old = client.post(
        "/api/v1/auth/login", json={"email": "ana@example.com", "password": USER_PASSWORD}
    )
    assert old.status_code == 401
    assert login(client, "ana@example.com", NEW_PASSWORD)["user"]["email"] == "ana@example.com"


def test_el_token_es_de_un_solo_uso(client, outbox, register_user):
    register_user()
    client.post(REQUEST_URL, json={"email": "ana@example.com"})
    token = outbox.last_reset_token()
    client.post(RESET_URL, json={"token": token, "password": NEW_PASSWORD})

    response = client.post(RESET_URL, json={"token": token, "password": "OtraClave12345"})

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_reset_token"


def test_una_nueva_solicitud_invalida_la_anterior(client, outbox, register_user):
    register_user()
    client.post(REQUEST_URL, json={"email": "ana@example.com"})
    first = outbox.last_reset_token()
    client.post(REQUEST_URL, json={"email": "ana@example.com"})

    response = client.post(RESET_URL, json={"token": first, "password": NEW_PASSWORD})

    assert response.status_code == 400


def test_token_vencido(client, outbox, repositories, register_user):
    register_user()
    client.post(REQUEST_URL, json={"email": "ana@example.com"})
    for reset in repositories.password_resets.items.values():
        reset.expires_at = utc_now() - timedelta(minutes=1)

    response = client.post(
        RESET_URL, json={"token": outbox.last_reset_token(), "password": NEW_PASSWORD}
    )

    assert response.status_code == 400


def test_token_inexistente(client):
    response = client.post(RESET_URL, json={"token": "x" * 40, "password": NEW_PASSWORD})

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_reset_token"


def test_restablecer_valida_la_politica_de_contrasena(client, outbox, register_user):
    register_user()
    client.post(REQUEST_URL, json={"email": "ana@example.com"})

    response = client.post(
        RESET_URL, json={"token": outbox.last_reset_token(), "password": "corta"}
    )

    assert response.status_code == 422


def test_restablecer_desbloquea_la_cuenta(client, outbox, repositories, register_user):
    user = register_user()
    for _ in range(5):
        client.post(
            "/api/v1/auth/login", json={"email": "ana@example.com", "password": "Mala12345"}
        )
    client.post(REQUEST_URL, json={"email": "ana@example.com"})
    client.post(RESET_URL, json={"token": outbox.last_reset_token(), "password": NEW_PASSWORD})

    assert repositories.users.items[user["id"]].locked_until is None
    assert login(client, "ana@example.com", NEW_PASSWORD)


# ── Cambio de contraseña autenticado ────────────────────────────────────────────
def test_cambiar_contrasena_exige_la_actual(client, register_user):
    register_user()
    token = login(client, "ana@example.com", USER_PASSWORD)["access_token"]

    response = client.put(
        "/api/v1/users/me/password",
        json={"current_password": "Incorrecta123", "new_password": NEW_PASSWORD},
        headers=auth_headers(token),
    )

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_current_password"


def test_cambiar_contrasena_cierra_otras_sesiones_y_conserva_esta(client, register_user):
    register_user()
    token = login(client, "ana@example.com", USER_PASSWORD)["access_token"]
    other_device_cookie = client.cookies.get("centynella_refresh")

    response = client.put(
        "/api/v1/users/me/password",
        json={"current_password": USER_PASSWORD, "new_password": NEW_PASSWORD},
        headers=auth_headers(token),
    )

    assert response.status_code == 200
    assert response.json()["access_token"]  # sesión nueva para este dispositivo
    assert client.post("/api/v1/auth/refresh").status_code == 200  # la cookie nueva funciona
    client.cookies.set("centynella_refresh", other_device_cookie, path="/api/v1")
    assert client.post("/api/v1/auth/refresh").status_code == 401  # la vieja fue revocada
    assert login(client, "ana@example.com", NEW_PASSWORD)


def test_cambiar_contrasena_valida_la_politica(client, register_user):
    register_user()
    token = login(client, "ana@example.com", USER_PASSWORD)["access_token"]

    response = client.put(
        "/api/v1/users/me/password",
        json={"current_password": USER_PASSWORD, "new_password": "corta"},
        headers=auth_headers(token),
    )

    assert response.status_code == 422
