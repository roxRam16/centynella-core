"""Ventas (punto de venta): cobrar un carrito, descontar existencia y, si es a crédito,
anotar el cargo en el fiado del cliente (con control de permisos)."""

from tests.conftest import USER_PASSWORD, auth_headers, login

SALES_URL = "/api/v1/sales"
PRODUCTS_URL = "/api/v1/products"
CUSTOMERS_URL = "/api/v1/customers"


def create_product(client, headers, **overrides) -> dict:
    payload = {
        "sku": "ABC-001",
        "name": "Refresco de cola 600ml",
        "unit": "pieza",
        "price": 18.5,
        "quantity": 24,
        **overrides,
    }
    response = client.post(PRODUCTS_URL, json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def create_customer(client, headers, **overrides) -> dict:
    payload = {"name": "Doña Lupe", "credit_limit": 500, **overrides}
    response = client.post(CUSTOMERS_URL, json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def no_sales_headers(client, admin_headers) -> dict[str, str]:
    """Cabeceras de alguien sin `sales:create` (p. ej. solo ve el catálogo)."""
    client.post(
        "/api/v1/roles",
        json={"key": "solo-ve", "name": "Solo consulta", "permissions": ["products:read"]},
        headers=admin_headers,
    )
    client.post(
        "/api/v1/users",
        json={
            "name": "Vero Visor",
            "email": "vero@example.com",
            "password": USER_PASSWORD,
            "role": "solo-ve",
        },
        headers=admin_headers,
    )
    return auth_headers(login(client, "vero@example.com", USER_PASSWORD)["access_token"])


# ── Cobrar ────────────────────────────────────────────────────────────────────────
def test_cobra_en_efectivo_calcula_el_cambio_y_descuenta_existencia(client, admin_headers):
    product = create_product(client, admin_headers)

    response = client.post(
        SALES_URL,
        json={
            "items": [{"product_id": product["id"], "quantity": 3}],
            "payment_method": "cash",
            "amount_tendered": 100,
        },
        headers=admin_headers,
    )

    assert response.status_code == 201, response.text
    sale = response.json()
    assert sale["total"] == 55.5
    assert sale["change_due"] == 44.5
    assert sale["items"][0]["name"] == "Refresco de cola 600ml"

    restocked = client.get(f"{PRODUCTS_URL}/{product['id']}", headers=admin_headers).json()
    assert restocked["quantity"] == 21


def test_cobra_con_tarjeta_sin_efectivo_no_pide_cambio(client, admin_headers):
    product = create_product(client, admin_headers)

    response = client.post(
        SALES_URL,
        json={
            "items": [{"product_id": product["id"], "quantity": 1}],
            "payment_method": "credit_card",
        },
        headers=admin_headers,
    )

    assert response.status_code == 201, response.text
    sale = response.json()
    assert sale["amount_tendered"] is None
    assert sale["change_due"] is None


def test_una_venta_con_varios_productos_suma_bien_el_total(client, admin_headers):
    soda = create_product(client, admin_headers, sku="SODA-1", price=18.5, quantity=10)
    chips = create_product(
        client, admin_headers, sku="CHIPS-1", name="Papas fritas", price=22, quantity=10
    )

    response = client.post(
        SALES_URL,
        json={
            "items": [
                {"product_id": soda["id"], "quantity": 2},
                {"product_id": chips["id"], "quantity": 1},
            ],
            "payment_method": "transfer",
        },
        headers=admin_headers,
    )

    assert response.status_code == 201, response.text
    assert response.json()["total"] == 59.0


# ── A crédito (fiado) ───────────────────────────────────────────────────────────────
def test_cobra_a_credito_anota_el_cargo_en_el_fiado_del_cliente(client, admin_headers):
    product = create_product(client, admin_headers)
    customer = create_customer(client, admin_headers)

    response = client.post(
        SALES_URL,
        json={
            "customer_id": customer["id"],
            "items": [{"product_id": product["id"], "quantity": 2}],
            "payment_method": "store_credit",
        },
        headers=admin_headers,
    )

    assert response.status_code == 201, response.text
    sale = response.json()
    assert sale["total"] == 37.0

    updated_customer = client.get(f"{CUSTOMERS_URL}/{customer['id']}", headers=admin_headers).json()
    assert updated_customer["balance"] == 37.0


def test_a_credito_sin_cliente_da_400(client, admin_headers):
    product = create_product(client, admin_headers)

    response = client.post(
        SALES_URL,
        json={
            "items": [{"product_id": product["id"], "quantity": 1}],
            "payment_method": "store_credit",
        },
        headers=admin_headers,
    )

    assert response.status_code == 400
    assert response.json()["code"] == "customer_required"


# ── Casos de error (y que no dejen a medias el inventario) ─────────────────────────
def test_efectivo_insuficiente_da_400_y_no_descuenta_existencia(client, admin_headers):
    product = create_product(client, admin_headers, quantity=10)

    response = client.post(
        SALES_URL,
        json={
            "items": [{"product_id": product["id"], "quantity": 1}],
            "payment_method": "cash",
            "amount_tendered": 5,
        },
        headers=admin_headers,
    )

    assert response.status_code == 400
    assert response.json()["code"] == "insufficient_cash"
    unchanged = client.get(f"{PRODUCTS_URL}/{product['id']}", headers=admin_headers).json()
    assert unchanged["quantity"] == 10


def test_existencia_insuficiente_da_409_y_no_descuenta_nada(client, admin_headers):
    low_stock = create_product(client, admin_headers, sku="LOW-1", quantity=2)
    plenty = create_product(client, admin_headers, sku="PLENTY-1", name="Agua", quantity=50)

    response = client.post(
        SALES_URL,
        json={
            "items": [
                {"product_id": plenty["id"], "quantity": 1},
                {"product_id": low_stock["id"], "quantity": 5},
            ],
            "payment_method": "cash",
            "amount_tendered": 1000,
        },
        headers=admin_headers,
    )

    assert response.status_code == 409
    assert response.json()["code"] == "insufficient_stock"
    # Ninguna línea se descontó, ni siquiera la que sí alcanzaba.
    assert (
        client.get(f"{PRODUCTS_URL}/{plenty['id']}", headers=admin_headers).json()["quantity"] == 50
    )


def test_producto_inexistente_da_404(client, admin_headers):
    response = client.post(
        SALES_URL,
        json={
            "items": [{"product_id": "no-existe", "quantity": 1}],
            "payment_method": "cash",
            "amount_tendered": 100,
        },
        headers=admin_headers,
    )

    assert response.status_code == 404
    assert response.json()["code"] == "product_not_found"


# ── Consultar ────────────────────────────────────────────────────────────────────
def test_lista_y_ve_el_detalle_de_una_venta(client, admin_headers):
    product = create_product(client, admin_headers)
    created = client.post(
        SALES_URL,
        json={
            "items": [{"product_id": product["id"], "quantity": 1}],
            "payment_method": "debit_card",
        },
        headers=admin_headers,
    ).json()

    listing = client.get(SALES_URL, headers=admin_headers)
    assert listing.status_code == 200
    assert listing.json()["total"] == 1

    detail = client.get(f"{SALES_URL}/{created['id']}", headers=admin_headers)
    assert detail.status_code == 200
    assert detail.json()["payment_method"] == "debit_card"


def test_filtra_ventas_por_cliente(client, admin_headers):
    product = create_product(client, admin_headers, quantity=10)
    customer = create_customer(client, admin_headers)
    client.post(
        SALES_URL,
        json={
            "customer_id": customer["id"],
            "items": [{"product_id": product["id"], "quantity": 1}],
            "payment_method": "store_credit",
        },
        headers=admin_headers,
    )
    client.post(
        SALES_URL,
        json={
            "items": [{"product_id": product["id"], "quantity": 1}],
            "payment_method": "cash",
            "amount_tendered": 100,
        },
        headers=admin_headers,
    )

    response = client.get(SALES_URL, params={"customer_id": customer["id"]}, headers=admin_headers)
    assert response.json()["total"] == 1


# ── Permisos ─────────────────────────────────────────────────────────────────────
def test_un_cajero_recien_registrado_puede_cobrar(client, admin_headers, register_user):
    """El rol "viewer" (por defecto al registrarse) ya incluye `sales:create`."""
    product = create_product(client, admin_headers)
    register_user()
    headers = auth_headers(login(client, "ana@example.com", USER_PASSWORD)["access_token"])

    response = client.post(
        SALES_URL,
        json={
            "items": [{"product_id": product["id"], "quantity": 1}],
            "payment_method": "cash",
            "amount_tendered": 100,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text


def test_sin_permiso_sales_create_da_403(client, admin_headers):
    product = create_product(client, admin_headers)
    headers = no_sales_headers(client, admin_headers)

    response = client.post(
        SALES_URL,
        json={
            "items": [{"product_id": product["id"], "quantity": 1}],
            "payment_method": "cash",
            "amount_tendered": 100,
        },
        headers=headers,
    )
    assert response.status_code == 403
