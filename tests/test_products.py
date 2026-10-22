"""Catálogo de productos (con control de permisos)."""

import pytest

from tests.conftest import USER_PASSWORD, auth_headers, login

PRODUCTS_URL = "/api/v1/products"


def create_product(client, headers, **overrides) -> dict:
    payload = {
        "sku": "ABC-001",
        "name": "Refresco de cola 600ml",
        "category": "Bebidas",
        "unit": "pieza",
        "price": 18.5,
        "quantity": 24,
        "low_stock_threshold": 6,
        **overrides,
    }
    response = client.post(PRODUCTS_URL, json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def manager_headers(client, admin_headers) -> dict[str, str]:
    """Cabeceras de alguien con `products:*` pero sin administración de usuarios."""
    client.post(
        "/api/v1/roles",
        json={
            "key": "bodeguero",
            "name": "Bodeguero",
            "permissions": ["products:read", "products:create", "products:update"],
        },
        headers=admin_headers,
    )
    client.post(
        "/api/v1/users",
        json={
            "name": "Beto Bodega",
            "email": "beto@example.com",
            "password": USER_PASSWORD,
            "role": "bodeguero",
        },
        headers=admin_headers,
    )
    return auth_headers(login(client, "beto@example.com", USER_PASSWORD)["access_token"])


# ── Crear y leer ─────────────────────────────────────────────────────────────────
def test_crear_y_ver_un_producto(client, admin_headers):
    created = create_product(client, admin_headers)

    assert created["sku"] == "ABC-001"
    assert created["status"] == "active"
    assert created["quantity"] == 24

    response = client.get(f"{PRODUCTS_URL}/{created['id']}", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["name"] == "Refresco de cola 600ml"


def test_el_sku_se_normaliza_a_mayusculas(client, admin_headers):
    created = create_product(client, admin_headers, sku="abc-002")

    assert created["sku"] == "ABC-002"


def test_sku_duplicado_da_conflicto(client, admin_headers):
    create_product(client, admin_headers)

    response = client.post(
        PRODUCTS_URL,
        json={"sku": "ABC-001", "name": "Otro producto", "price": 10, "quantity": 1},
        headers=admin_headers,
    )

    assert response.status_code == 409
    assert response.json()["code"] == "sku_taken"


def test_ver_un_producto_inexistente_da_404(client, admin_headers):
    response = client.get(f"{PRODUCTS_URL}/no-existe", headers=admin_headers)

    assert response.status_code == 404
    assert response.json()["code"] == "product_not_found"


# ── Listado, búsqueda y filtros ───────────────────────────────────────────────────
def test_lista_y_busca_productos(client, admin_headers):
    create_product(
        client, admin_headers, sku="ABC-001", name="Refresco de cola", category="Bebidas"
    )
    create_product(client, admin_headers, sku="XYZ-002", name="Jabón en barra", category="Limpieza")

    response = client.get(PRODUCTS_URL, params={"q": "jabón"}, headers=admin_headers)

    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["sku"] == "XYZ-002"


def test_filtra_por_categoria_y_estado(client, admin_headers):
    create_product(client, admin_headers, sku="A-1", category="Bebidas")
    create_product(client, admin_headers, sku="A-2", category="Limpieza")
    discontinuado = create_product(client, admin_headers, sku="A-3", category="Bebidas")
    client.patch(
        f"{PRODUCTS_URL}/{discontinuado['id']}",
        json={"status": "discontinued"},
        headers=admin_headers,
    )

    por_categoria = client.get(
        PRODUCTS_URL, params={"category": "Bebidas"}, headers=admin_headers
    ).json()
    assert por_categoria["total"] == 2

    activos = client.get(PRODUCTS_URL, params={"status": "active"}, headers=admin_headers).json()
    assert activos["total"] == 2


def test_pagina_cuando_hay_mas_de_una_pagina(client, admin_headers):
    for i in range(3):
        create_product(client, admin_headers, sku=f"PAG-{i}", name=f"Producto {i}")

    primera = client.get(
        PRODUCTS_URL, params={"page": 1, "page_size": 2}, headers=admin_headers
    ).json()
    segunda = client.get(
        PRODUCTS_URL, params={"page": 2, "page_size": 2}, headers=admin_headers
    ).json()

    assert primera["total"] == 3
    assert len(primera["items"]) == 2
    assert len(segunda["items"]) == 1


# ── Editar y eliminar ──────────────────────────────────────────────────────────────
def test_editar_un_producto_cambia_solo_lo_enviado(client, admin_headers):
    created = create_product(client, admin_headers)

    response = client.patch(
        f"{PRODUCTS_URL}/{created['id']}", json={"quantity": 5}, headers=admin_headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["quantity"] == 5
    assert body["name"] == created["name"]  # no cambió


def test_editar_sin_campos_da_422(client, admin_headers):
    created = create_product(client, admin_headers)

    response = client.patch(f"{PRODUCTS_URL}/{created['id']}", json={}, headers=admin_headers)

    assert response.status_code == 422


def test_eliminar_un_producto(client, admin_headers):
    created = create_product(client, admin_headers)

    response = client.delete(f"{PRODUCTS_URL}/{created['id']}", headers=admin_headers)
    assert response.status_code == 204
    assert client.get(f"{PRODUCTS_URL}/{created['id']}", headers=admin_headers).status_code == 404


def test_eliminar_un_producto_inexistente_da_404(client, admin_headers):
    response = client.delete(f"{PRODUCTS_URL}/no-existe", headers=admin_headers)

    assert response.status_code == 404


# ── Validación ─────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("sku", ""),
        ("sku", "con espacios"),
        ("name", "A"),
        ("price", -1),
        ("quantity", -1),
    ],
)
def test_validacion_de_campos(client, admin_headers, field, value):
    payload = {"sku": "VAL-1", "name": "Producto válido", "price": 10, "quantity": 1}
    payload[field] = value

    response = client.post(PRODUCTS_URL, json=payload, headers=admin_headers)

    assert response.status_code == 422


# ── Autorización ───────────────────────────────────────────────────────────────────
def test_sin_permiso_products_read_recibe_403(client, register_user):
    register_user()
    token = login(client, "ana@example.com", USER_PASSWORD)["access_token"]
    # El rol por defecto (viewer) SÍ puede leer el catálogo (pensado para un cajero).
    assert client.get(PRODUCTS_URL, headers=auth_headers(token)).status_code == 200
    # Pero no puede crear.
    response = client.post(
        PRODUCTS_URL,
        json={"sku": "X-1", "name": "Producto", "price": 1, "quantity": 1},
        headers=auth_headers(token),
    )
    assert response.status_code == 403


def test_bodeguero_puede_crear_y_editar_pero_no_eliminar(client, admin_headers):
    headers = manager_headers(client, admin_headers)

    created = create_product(client, headers, sku="BOD-1")
    edited = client.patch(f"{PRODUCTS_URL}/{created['id']}", json={"quantity": 2}, headers=headers)
    deleted = client.delete(f"{PRODUCTS_URL}/{created['id']}", headers=headers)

    assert edited.status_code == 200
    assert deleted.status_code == 403


def test_sin_sesion_recibe_401(client):
    assert client.get(PRODUCTS_URL).status_code == 401
