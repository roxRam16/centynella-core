"""Proveedores: directorio simple (con control de permisos)."""

import pytest

from tests.conftest import USER_PASSWORD, auth_headers, login

SUPPLIERS_URL = "/api/v1/suppliers"


def create_supplier(client, headers, **overrides) -> dict:
    payload = {
        "name": "Distribuidora La Central",
        "phone": "2281234567",
        "products_supplied": "Refrescos y botanas",
        **overrides,
    }
    response = client.post(SUPPLIERS_URL, json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


# ── Crear y leer ─────────────────────────────────────────────────────────────────
def test_crear_y_ver_un_proveedor(client, admin_headers):
    created = create_supplier(client, admin_headers)

    assert created["name"] == "Distribuidora La Central"
    assert created["products_supplied"] == "Refrescos y botanas"

    response = client.get(f"{SUPPLIERS_URL}/{created['id']}", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["phone"] == "2281234567"


def test_ver_un_proveedor_inexistente_da_404(client, admin_headers):
    response = client.get(f"{SUPPLIERS_URL}/no-existe", headers=admin_headers)

    assert response.status_code == 404
    assert response.json()["code"] == "supplier_not_found"


# ── Listado y búsqueda ─────────────────────────────────────────────────────────────
def test_lista_y_busca_proveedores(client, admin_headers):
    create_supplier(client, admin_headers, name="Distribuidora La Central", phone="2281111111")
    create_supplier(client, admin_headers, name="Lácteos del Valle", phone="2282222222")

    response = client.get(SUPPLIERS_URL, params={"q": "lácteos"}, headers=admin_headers)

    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "Lácteos del Valle"


def test_busca_por_lo_que_surte(client, admin_headers):
    create_supplier(client, admin_headers, name="Proveedor A", products_supplied="Abarrotes")
    create_supplier(
        client, admin_headers, name="Proveedor B", products_supplied="Limpieza y detergentes"
    )

    response = client.get(SUPPLIERS_URL, params={"q": "detergentes"}, headers=admin_headers)

    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "Proveedor B"


def test_pagina_cuando_hay_mas_de_una_pagina(client, admin_headers):
    for i in range(3):
        create_supplier(client, admin_headers, name=f"Proveedor {i}", phone=f"228000000{i}")

    primera = client.get(
        SUPPLIERS_URL, params={"page": 1, "page_size": 2}, headers=admin_headers
    ).json()

    assert primera["total"] == 3
    assert len(primera["items"]) == 2


# ── Editar y eliminar ──────────────────────────────────────────────────────────────
def test_editar_un_proveedor_cambia_solo_lo_enviado(client, admin_headers):
    created = create_supplier(client, admin_headers)

    response = client.patch(
        f"{SUPPLIERS_URL}/{created['id']}",
        json={"products_supplied": "Solo refrescos"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["products_supplied"] == "Solo refrescos"
    assert body["name"] == created["name"]


def test_editar_sin_campos_da_422(client, admin_headers):
    created = create_supplier(client, admin_headers)

    response = client.patch(f"{SUPPLIERS_URL}/{created['id']}", json={}, headers=admin_headers)

    assert response.status_code == 422


def test_eliminar_un_proveedor(client, admin_headers):
    created = create_supplier(client, admin_headers)

    response = client.delete(f"{SUPPLIERS_URL}/{created['id']}", headers=admin_headers)

    assert response.status_code == 204
    assert client.get(f"{SUPPLIERS_URL}/{created['id']}", headers=admin_headers).status_code == 404


def test_eliminar_un_proveedor_inexistente_da_404(client, admin_headers):
    response = client.delete(f"{SUPPLIERS_URL}/no-existe", headers=admin_headers)

    assert response.status_code == 404


# ── Validación ─────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", "A"),
        ("phone", "abc"),
        ("name", "<script>"),
    ],
)
def test_validacion_de_campos(client, admin_headers, field, value):
    payload = {"name": "Proveedor válido", "phone": "2281234567"}
    payload[field] = value

    response = client.post(SUPPLIERS_URL, json=payload, headers=admin_headers)

    assert response.status_code == 422


# ── Autorización ───────────────────────────────────────────────────────────────────
def test_el_gerente_administra_proveedores_pero_no_los_elimina(client, admin_headers):
    client.post(
        "/api/v1/roles",
        json={
            "key": "gerente-prueba",
            "name": "Gerente de prueba",
            "permissions": ["suppliers:read", "suppliers:create", "suppliers:update"],
        },
        headers=admin_headers,
    )
    client.post(
        "/api/v1/users",
        json={
            "name": "Gerente Uno",
            "email": "gerente@example.com",
            "password": USER_PASSWORD,
            "role": "gerente-prueba",
        },
        headers=admin_headers,
    )
    headers = auth_headers(login(client, "gerente@example.com", USER_PASSWORD)["access_token"])

    created = create_supplier(client, headers)
    editado = client.patch(
        f"{SUPPLIERS_URL}/{created['id']}", json={"notes": "Buen trato"}, headers=headers
    )
    eliminado = client.delete(f"{SUPPLIERS_URL}/{created['id']}", headers=headers)

    assert editado.status_code == 200
    assert eliminado.status_code == 403


def test_viewer_por_defecto_solo_puede_leer(client, register_user):
    register_user()
    token = login(client, "ana@example.com", USER_PASSWORD)["access_token"]

    assert client.get(SUPPLIERS_URL, headers=auth_headers(token)).status_code == 200
    response = client.post(SUPPLIERS_URL, json={"name": "X"}, headers=auth_headers(token))
    assert response.status_code == 403


def test_sin_sesion_recibe_401(client):
    assert client.get(SUPPLIERS_URL).status_code == 401
