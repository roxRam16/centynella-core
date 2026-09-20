def test_get_greeting(client):
    response = client.get("/api/v1/greeting")

    assert response.status_code == 200
    assert response.json() == {
        "message": "¡Hola Mundo!",
        "service": "CENTYNELLA-CORE",
        "environment": "sandbox",
    }


def test_greeting_solo_acepta_get(client):
    response = client.post("/api/v1/greeting")

    assert response.status_code == 405
    assert "GET" in response.headers["allow"]
