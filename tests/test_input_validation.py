"""Validación de entradas: correos, contraseñas, nombres, textos y ataques de inyección."""

import pytest

from tests.conftest import ADMIN_EMAIL, USER_PASSWORD, auth_headers, login

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"


def register(client, **overrides):
    payload = {"name": "Ana Pérez", "email": "ana@example.com", "password": USER_PASSWORD}
    return client.post(REGISTER, json={**payload, **overrides})


def error_fields(response) -> set[str]:
    return {".".join(str(part) for part in err["loc"][1:]) for err in response.json()["errors"]}


# ── Correo ──────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "email",
    [
        "sin-arroba.com",
        "@example.com",
        "ana@",
        "ana@example",  # sin dominio de nivel superior
        "ana @example.com",
        "ana@exa mple.com",
        "<script>@example.com",
        "ana<b>@example.com",
        '"ana"@example.com',
        "o'brien@example.com",
        "ana@example..com",
        "a" * 65 + "@example.com",
    ],
)
def test_correos_no_permitidos_se_rechazan(client, email):
    response = register(client, email=email)

    assert response.status_code == 422
    assert "email" in error_fields(response)


@pytest.mark.parametrize("email", ["ana@example.com", "ana.perez+inv@mail.example.co", "A@B.CO"])
def test_correos_validos_se_aceptan_y_normalizan(client, email):
    response = register(client, email=email)

    assert response.status_code == 201
    assert response.json()["email"] == email.lower()


# ── Contraseña ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("password", "fragmento"),
    [
        ("Sinsimbolo123", "un símbolo"),
        ("sinmayuscula#123", "una mayúscula"),
        ("SINMINUSCULA#123", "una minúscula"),
        ("SinNumero#Aqui", "un número"),
        ("Con Espacio#123", "espacios"),
        ("Tab\tulador#123", "espacios"),
        ("Ab#1", "at least 8"),  # demasiado corta (mensaje de Pydantic)
        ("Aa#1" + "x" * 130, "at most 128"),
    ],
)
def test_contrasenas_debiles_se_rechazan_con_el_motivo(client, password, fragmento):
    response = register(client, password=password)

    assert response.status_code == 422
    assert fragmento in str(response.json()["errors"])


def test_contrasena_fuerte_se_acepta_incluso_con_caracteres_raros(client):
    # Se guarda solo como hash y nunca se muestra: cualquier símbolo es inofensivo.
    assert register(client, password="<Sc#ript>alert(1)Aa9").status_code == 201


def test_las_politicas_tambien_aplican_al_cambio_y_al_restablecimiento(client, register_user):
    register_user()
    token = login(client, "ana@example.com", USER_PASSWORD)["access_token"]

    change = client.put(
        "/api/v1/users/me/password",
        json={"current_password": USER_PASSWORD, "new_password": "SinSimbolo123"},
        headers=auth_headers(token),
    )
    reset = client.post(
        "/api/v1/auth/password-resets", json={"token": "x" * 40, "password": "corta"}
    )

    assert change.status_code == 422
    assert reset.status_code == 422


# ── Nombres y textos libres: sin HTML ni scripts ────────────────────────────────
@pytest.mark.parametrize(
    "name",
    [
        "<script>alert(1)</script>",
        "Ana<b>",
        'Ana" onmouseover="alert(1)',
        "Ana; DROP TABLE users",
        "{{7*7}}",
        "$(whoami)",
        "Ana\x00Pérez",
        "123 Ana",
        "A",
        "x" * 81,
    ],
)
def test_nombres_con_marcado_o_simbolos_peligrosos_se_rechazan(client, name):
    response = register(client, name=name)

    assert response.status_code == 422
    assert "name" in error_fields(response)


@pytest.mark.parametrize(
    "name", ["José Núñez", "Ana-María O'Brien", "Dr. Ana Pérez", "李小龍", "Zoë"]
)
def test_nombres_reales_de_cualquier_idioma_se_aceptan(client, name):
    assert register(client, name=name).status_code == 201


@pytest.mark.parametrize("field", ["name", "description"])
def test_los_roles_rechazan_marcado_html(client, admin_headers, field):
    payload = {
        "key": "riesgoso",
        "name": "Rol Seguro",
        "description": "ok",
        field: "<img src=x onerror=alert(1)>",
    }

    response = client.post("/api/v1/roles", json=payload, headers=admin_headers)

    assert response.status_code == 422
    assert field in error_fields(response)


def test_el_rol_referenciado_por_un_usuario_debe_tener_formato_de_clave(client, admin_headers):
    response = client.post(
        "/api/v1/users",
        json={
            "name": "Luis",
            "email": "luis@example.com",
            "password": USER_PASSWORD,
            "role": "admin' || '1'=='1",
        },
        headers=admin_headers,
    )

    assert response.status_code == 422
    assert "role" in error_fields(response)


# ── Inyección NoSQL ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "payload",
    [
        {"email": {"$ne": ""}, "password": {"$ne": ""}},
        {"email": {"$gt": ""}, "password": "x"},
        {"email": ADMIN_EMAIL, "password": {"$regex": ".*"}},
        {"email": ["admin@example.com"], "password": "x"},
    ],
)
def test_login_rechaza_operadores_de_mongo_como_entrada(client, payload):
    response = client.post(LOGIN, json=payload)

    assert response.status_code == 422  # tipos estrictos: nunca llegan a la consulta


def test_el_buscador_de_usuarios_no_interpreta_regex_ni_operadores(client, admin_headers):
    for texto in (".*", "^", "$ne", '{"$gt": ""}', "(", "[a-"):
        response = client.get("/api/v1/users", params={"q": texto}, headers=admin_headers)

        assert response.status_code == 200
        assert response.json()["total"] == 0


def test_los_filtros_de_la_bitacora_son_texto_literal(client, admin_headers):
    response = client.get(
        "/api/v1/logs", params={"module": "auth' || 1==1", "q": ".*"}, headers=admin_headers
    )

    assert response.status_code == 200
    assert response.json()["total"] == 0


# ── Tamaño y cabeceras ──────────────────────────────────────────────────────────
def test_un_cuerpo_demasiado_grande_se_rechaza_con_413(client):
    response = client.post(
        REGISTER, content=b"x" * 2_000_000, headers={"Content-Type": "application/json"}
    )

    assert response.status_code == 413
    assert response.json()["code"] == "payload_too_large"
    assert response.headers["x-request-id"]


def test_un_cuerpo_enviado_por_trozos_tambien_se_limita(client):
    def trozos():
        for _ in range(30):
            yield b"x" * 50_000

    response = client.post(REGISTER, content=trozos(), headers={"Content-Type": "application/json"})

    assert response.status_code == 413


def test_la_api_envia_cabeceras_de_seguridad(client):
    response = client.get("/api/v1/greeting")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert (
        response.headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"
    )
    assert response.headers["cache-control"] == "no-store"
    assert "strict-transport-security" not in response.headers  # solo en producción


def test_swagger_no_recibe_la_csp_estricta_para_poder_cargar(client):
    response = client.get("/docs")

    assert response.status_code == 200
    assert "content-security-policy" not in response.headers
    assert response.headers["x-content-type-options"] == "nosniff"


def test_en_produccion_se_activa_hsts(make_app, settings):
    from fastapi.testclient import TestClient

    production = settings.model_copy(update={"app_env": "production"})
    with TestClient(make_app(settings=production), base_url="https://testserver") as client:
        response = client.get("/health")

    assert "max-age=31536000" in response.headers["strict-transport-security"]
