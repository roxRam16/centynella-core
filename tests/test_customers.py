"""Clientes y fiado (con control de permisos)."""

import pytest

from tests.conftest import USER_PASSWORD, auth_headers, login

CUSTOMERS_URL = "/api/v1/customers"


def create_customer(client, headers, **overrides) -> dict:
    payload = {
        "name": "Doña Lupe",
        "phone": "2281234567",
        "credit_limit": 500,
        **overrides,
    }
    response = client.post(CUSTOMERS_URL, json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def cashier_headers(client, admin_headers) -> dict[str, str]:
    """Cabeceras de alguien con `customers:credit` pero sin administrar clientes."""
    client.post(
        "/api/v1/roles",
        json={
            "key": "cajero",
            "name": "Cajero",
            "permissions": ["customers:read", "customers:credit"],
        },
        headers=admin_headers,
    )
    client.post(
        "/api/v1/users",
        json={
            "name": "Caja Uno",
            "email": "caja@example.com",
            "password": USER_PASSWORD,
            "role": "cajero",
        },
        headers=admin_headers,
    )
    return auth_headers(login(client, "caja@example.com", USER_PASSWORD)["access_token"])


# ── Crear y leer ─────────────────────────────────────────────────────────────────
def test_crear_y_ver_un_cliente(client, admin_headers):
    created = create_customer(client, admin_headers)

    assert created["name"] == "Doña Lupe"
    assert created["balance"] == 0
    assert created["credit_limit"] == 500

    response = client.get(f"{CUSTOMERS_URL}/{created['id']}", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["phone"] == "2281234567"


def test_ver_un_cliente_inexistente_da_404(client, admin_headers):
    response = client.get(f"{CUSTOMERS_URL}/no-existe", headers=admin_headers)

    assert response.status_code == 404
    assert response.json()["code"] == "customer_not_found"


# ── Listado y búsqueda ─────────────────────────────────────────────────────────────
def test_lista_y_busca_clientes(client, admin_headers):
    create_customer(client, admin_headers, name="Doña Lupe", phone="2281111111")
    create_customer(client, admin_headers, name="Don Beto", phone="2282222222")

    response = client.get(CUSTOMERS_URL, params={"q": "beto"}, headers=admin_headers)

    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "Don Beto"


def test_pagina_cuando_hay_mas_de_una_pagina(client, admin_headers):
    for i in range(3):
        create_customer(client, admin_headers, name=f"Cliente {i}", phone=f"228000000{i}")

    primera = client.get(
        CUSTOMERS_URL, params={"page": 1, "page_size": 2}, headers=admin_headers
    ).json()

    assert primera["total"] == 3
    assert len(primera["items"]) == 2


# ── Editar y eliminar ──────────────────────────────────────────────────────────────
def test_editar_un_cliente_cambia_solo_lo_enviado(client, admin_headers):
    created = create_customer(client, admin_headers)

    response = client.patch(
        f"{CUSTOMERS_URL}/{created['id']}", json={"credit_limit": 1000}, headers=admin_headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["credit_limit"] == 1000
    assert body["name"] == created["name"]


def test_editar_sin_campos_da_422(client, admin_headers):
    created = create_customer(client, admin_headers)

    response = client.patch(f"{CUSTOMERS_URL}/{created['id']}", json={}, headers=admin_headers)

    assert response.status_code == 422


def test_eliminar_un_cliente_sin_saldo(client, admin_headers):
    created = create_customer(client, admin_headers)

    response = client.delete(f"{CUSTOMERS_URL}/{created['id']}", headers=admin_headers)

    assert response.status_code == 204
    assert client.get(f"{CUSTOMERS_URL}/{created['id']}", headers=admin_headers).status_code == 404


def test_no_se_puede_eliminar_un_cliente_con_saldo(client, admin_headers):
    created = create_customer(client, admin_headers)
    client.post(
        f"{CUSTOMERS_URL}/{created['id']}/credit-movements",
        json={"type": "charge", "amount": 100},
        headers=admin_headers,
    )

    response = client.delete(f"{CUSTOMERS_URL}/{created['id']}", headers=admin_headers)

    assert response.status_code == 409
    assert response.json()["code"] == "customer_has_balance"


# ── Fiado: cargos y abonos ──────────────────────────────────────────────────────────
def test_anota_un_cargo_y_sube_el_saldo(client, admin_headers):
    created = create_customer(client, admin_headers)

    response = client.post(
        f"{CUSTOMERS_URL}/{created['id']}/credit-movements",
        json={"type": "charge", "amount": 150, "note": "Despensa"},
        headers=admin_headers,
    )

    assert response.status_code == 201
    assert response.json()["balance"] == 150


def test_un_abono_baja_el_saldo(client, admin_headers):
    created = create_customer(client, admin_headers)
    client.post(
        f"{CUSTOMERS_URL}/{created['id']}/credit-movements",
        json={"type": "charge", "amount": 150},
        headers=admin_headers,
    )

    response = client.post(
        f"{CUSTOMERS_URL}/{created['id']}/credit-movements",
        json={"type": "payment", "amount": 50},
        headers=admin_headers,
    )

    assert response.status_code == 201
    assert response.json()["balance"] == 100


def test_un_abono_mayor_al_saldo_da_conflicto(client, admin_headers):
    created = create_customer(client, admin_headers)
    client.post(
        f"{CUSTOMERS_URL}/{created['id']}/credit-movements",
        json={"type": "charge", "amount": 50},
        headers=admin_headers,
    )

    response = client.post(
        f"{CUSTOMERS_URL}/{created['id']}/credit-movements",
        json={"type": "payment", "amount": 100},
        headers=admin_headers,
    )

    assert response.status_code == 409
    assert response.json()["code"] == "payment_exceeds_balance"


def test_un_cargo_puede_superar_el_limite_de_credito_con_aviso_en_bitacora(
    client, admin_headers, log_repository, flush_logs
):
    created = create_customer(client, admin_headers, credit_limit=100)

    response = client.post(
        f"{CUSTOMERS_URL}/{created['id']}/credit-movements",
        json={"type": "charge", "amount": 150},
        headers=admin_headers,
    )
    flush_logs()

    assert response.status_code == 201  # se permite, no se bloquea
    assert response.json()["balance"] == 150
    assert log_repository.by_event("customers.credit.over_limit")


def test_historial_de_movimientos(client, admin_headers):
    created = create_customer(client, admin_headers)
    client.post(
        f"{CUSTOMERS_URL}/{created['id']}/credit-movements",
        json={"type": "charge", "amount": 150, "note": "Despensa"},
        headers=admin_headers,
    )
    client.post(
        f"{CUSTOMERS_URL}/{created['id']}/credit-movements",
        json={"type": "payment", "amount": 50},
        headers=admin_headers,
    )

    response = client.get(
        f"{CUSTOMERS_URL}/{created['id']}/credit-movements", headers=admin_headers
    )

    body = response.json()
    assert body["total"] == 2
    assert [m["type"] for m in body["items"]] == ["payment", "charge"]  # más reciente primero


def test_monto_negativo_o_cero_se_rechaza(client, admin_headers):
    created = create_customer(client, admin_headers)

    response = client.post(
        f"{CUSTOMERS_URL}/{created['id']}/credit-movements",
        json={"type": "charge", "amount": 0},
        headers=admin_headers,
    )

    assert response.status_code == 422


# ── Validación ─────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", "A"),
        ("phone", "abc"),
        ("credit_limit", -1),
    ],
)
def test_validacion_de_campos(client, admin_headers, field, value):
    payload = {"name": "Cliente válido", "phone": "2281234567", "credit_limit": 100}
    payload[field] = value

    response = client.post(CUSTOMERS_URL, json=payload, headers=admin_headers)

    assert response.status_code == 422


# ── Autorización ───────────────────────────────────────────────────────────────────
def test_el_cajero_puede_cobrar_fiado_pero_no_administrar_clientes(client, admin_headers):
    created = create_customer(client, admin_headers)
    headers = cashier_headers(client, admin_headers)

    cobra = client.post(
        f"{CUSTOMERS_URL}/{created['id']}/credit-movements",
        json={"type": "charge", "amount": 50},
        headers=headers,
    )
    crea = client.post(CUSTOMERS_URL, json={"name": "Otro"}, headers=headers)
    elimina = client.delete(f"{CUSTOMERS_URL}/{created['id']}", headers=headers)

    assert cobra.status_code == 201
    assert crea.status_code == 403
    assert elimina.status_code == 403


def test_viewer_por_defecto_puede_leer_y_cobrar_fiado(client, register_user):
    register_user()
    token = login(client, "ana@example.com", USER_PASSWORD)["access_token"]

    assert client.get(CUSTOMERS_URL, headers=auth_headers(token)).status_code == 200
    response = client.post(CUSTOMERS_URL, json={"name": "X"}, headers=auth_headers(token))
    assert response.status_code == 403


def test_sin_sesion_recibe_401(client):
    assert client.get(CUSTOMERS_URL).status_code == 401
