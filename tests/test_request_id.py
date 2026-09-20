def test_genera_request_id_si_no_viene(client):
    response = client.get("/health")

    assert len(response.headers["x-request-id"]) == 32


def test_respeta_el_request_id_del_cliente(client):
    response = client.get("/health", headers={"X-Request-ID": "trace-abc.123"})

    assert response.headers["x-request-id"] == "trace-abc.123"


def test_descarta_request_id_inseguro(client):
    response = client.get("/health", headers={"X-Request-ID": "malo id con espacios!"})

    assert response.headers["x-request-id"] != "malo id con espacios!"
    assert len(response.headers["x-request-id"]) == 32
