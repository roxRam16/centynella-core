"""La bitácora de punta a punta: qué se registra, con qué usuario/sesión y qué NUNCA se registra."""

import json

from fastapi import HTTPException
from fastapi.testclient import TestClient

from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, USER_PASSWORD, auth_headers, login

LOGS = "/api/v1/logs"


def session_of(client, token: str) -> str:
    return client.app.state.services.tokens.decode_access_token(token).session_id


def events_named(log_repository, flush_logs, name: str):
    flush_logs()
    return log_repository.by_event(name)


# ── Arranque: "desde que Mongo se conecta" ──────────────────────────────────────
def test_el_arranque_deja_rastro_de_la_conexion_los_indices_y_los_datos_iniciales(
    client, log_repository, flush_logs
):
    flush_logs()
    events = [entry.event for entry in log_repository.items]

    assert events.index("system.startup") < events.index("database.connected")
    assert "database.indexes_ready" in events
    assert events.count("roles.seeded") == 3  # admin, manager, viewer
    assert "system.bootstrap_admin_created" in events
    connected = log_repository.by_event("database.connected")[0]
    assert connected.module == "database" and connected.level == "INFO"
    assert "logs_database" in connected.details


def test_si_mongo_no_responde_al_arrancar_se_registra_como_error(make_app, log_repository):
    from tests.fakes import FakeDatabase

    with TestClient(make_app(database=FakeDatabase(up=False))) as client:
        client.portal.call(client.app.state.events.flush)

    (entry,) = log_repository.by_event("database.unreachable")
    assert entry.level == "ERROR" and entry.module == "database"


# ── Autenticación por sesión ────────────────────────────────────────────────────
def test_login_exitoso_queda_ligado_a_usuario_y_sesion(client, log_repository, flush_logs):
    body = login(client, ADMIN_EMAIL, ADMIN_PASSWORD)

    (entry,) = events_named(log_repository, flush_logs, "auth.login.success")
    assert entry.module == "auth" and entry.level == "INFO"
    assert entry.user_id == body["user"]["id"]
    assert entry.session_id == session_of(client, body["access_token"])
    assert entry.request_id and entry.ip


def test_la_misma_sesion_atraviesa_login_refresh_y_logout(client, log_repository, flush_logs):
    token = login(client, ADMIN_EMAIL, ADMIN_PASSWORD)["access_token"]
    sid = session_of(client, token)
    refreshed = client.post("/api/v1/auth/refresh").json()["access_token"]
    client.get("/api/v1/users/me", headers=auth_headers(refreshed))
    client.post("/api/v1/auth/logout")

    flush_logs()
    of_session = [e for e in log_repository.items if e.session_id == sid]
    names = {e.event for e in of_session}
    assert session_of(client, refreshed) == sid  # el refresh conserva la sesión
    assert {"auth.login.success", "auth.logout"} <= names
    assert "http.request" in names  # también sus peticiones autenticadas


def test_login_fallido_no_guarda_el_correo_completo_ni_la_contrasena(
    client, log_repository, flush_logs
):
    client.post(
        "/api/v1/auth/login", json={"email": "victima@example.com", "password": "Intento#Secreto1"}
    )

    (entry,) = events_named(log_repository, flush_logs, "auth.login.failed")
    assert entry.level == "WARNING" and entry.details["reason"] == "unknown_user"
    assert entry.details["email"] == "v***@example.com"
    assert "Intento#Secreto1" not in entry.model_dump_json()
    assert "victima@" not in entry.model_dump_json()


def test_contrasena_incorrecta_registra_el_usuario_y_el_motivo(
    client, log_repository, flush_logs, register_user
):
    user = register_user()

    client.post(
        "/api/v1/auth/login", json={"email": "ana@example.com", "password": "Otra#Clave123"}
    )

    (entry,) = events_named(log_repository, flush_logs, "auth.login.failed")
    assert entry.user_id == user["id"] and entry.details["reason"] == "bad_password"


def test_el_bloqueo_por_intentos_es_un_evento_de_seguridad(
    client, log_repository, flush_logs, register_user
):
    register_user()
    for _ in range(5):
        client.post(
            "/api/v1/auth/login", json={"email": "ana@example.com", "password": "Mala#12345"}
        )
    client.post("/api/v1/auth/login", json={"email": "ana@example.com", "password": USER_PASSWORD})

    flush_logs()
    (locked,) = log_repository.by_event("auth.login.locked_out")
    assert locked.module == "security" and locked.level == "WARNING"
    assert log_repository.by_event("auth.login.rejected_locked")


def test_reutilizar_un_refresh_token_rotado_es_un_evento_de_seguridad(
    client, settings, make_app, log_repository
):
    strict = settings.model_copy(update={"refresh_reuse_leeway_seconds": 0})
    with TestClient(make_app(settings=strict)) as strict_client:
        login(strict_client, ADMIN_EMAIL, ADMIN_PASSWORD)
        stolen = strict_client.cookies.get("centynella_refresh")
        strict_client.post("/api/v1/auth/refresh")
        strict_client.cookies.set("centynella_refresh", stolen, path="/api/v1")
        strict_client.post("/api/v1/auth/refresh")
        strict_client.portal.call(strict_client.app.state.events.flush)

    (entry,) = log_repository.by_event("auth.session.reuse_detected")
    assert entry.module == "security" and entry.level == "WARNING" and entry.session_id


def test_recuperacion_y_cambio_de_contrasena_se_registran(
    client, log_repository, flush_logs, outbox, register_user
):
    user = register_user()
    client.post("/api/v1/auth/password-reset-requests", json={"email": "ana@example.com"})
    client.post(
        "/api/v1/auth/password-resets",
        json={"token": outbox.last_reset_token(), "password": "Nueva#Clave987"},
    )
    token = login(client, "ana@example.com", "Nueva#Clave987")["access_token"]
    client.put(
        "/api/v1/users/me/password",
        json={"current_password": "Nueva#Clave987", "new_password": "Otra#Clave654"},
        headers=auth_headers(token),
    )

    flush_logs()
    names = [e.event for e in log_repository.items if e.user_id == user["id"]]
    assert {
        "auth.register.success",
        "auth.password.reset_requested",
        "auth.password.reset_completed",
        "auth.password.changed",
    } <= set(names)


# ── Administración ──────────────────────────────────────────────────────────────
def test_las_acciones_de_administracion_registran_actor_y_objetivo(
    client, admin_headers, log_repository, flush_logs
):
    admin_id = client.get("/api/v1/users/me", headers=admin_headers).json()["id"]
    created = client.post(
        "/api/v1/users",
        json={
            "name": "Luis",
            "email": "luis@example.com",
            "password": USER_PASSWORD,
            "role": "viewer",
        },
        headers=admin_headers,
    ).json()
    client.patch(f"/api/v1/users/{created['id']}", json={"role": "manager"}, headers=admin_headers)
    client.delete(f"/api/v1/users/{created['id']}", headers=admin_headers)
    client.post("/api/v1/roles", json={"key": "auditor", "name": "Auditor"}, headers=admin_headers)

    flush_logs()
    for name in ("users.created", "users.updated", "users.deleted"):
        (entry,) = log_repository.by_event(name)
        assert entry.module == "users"
        assert entry.user_id == admin_id  # el ACTOR (quien hizo la acción)
        assert entry.details["target_user_id"] == created["id"]  # el OBJETIVO
    assert log_repository.by_event("users.updated")[0].details["new_role"] == "manager"
    assert log_repository.by_event("roles.created")[0].details["role_key"] == "auditor"


def test_un_acceso_denegado_queda_como_evento_de_seguridad(
    client, register_user, log_repository, flush_logs
):
    register_user()
    token = login(client, "ana@example.com", USER_PASSWORD)["access_token"]

    client.get("/api/v1/users", headers=auth_headers(token))

    (entry,) = events_named(log_repository, flush_logs, "security.permission_denied")
    assert entry.module == "security" and entry.details["missing"] == ["users:read"]


def test_un_token_invalido_queda_registrado(client, log_repository, flush_logs):
    client.get("/api/v1/users/me", headers=auth_headers("no.es.un.jwt"))

    (entry,) = events_named(log_repository, flush_logs, "security.token_rejected")
    assert entry.details["reason"] == "invalid_token"


# ── Log de acceso ───────────────────────────────────────────────────────────────
def test_cada_peticion_deja_un_evento_http_con_usuario_sesion_y_duracion(
    client, admin_headers, log_repository, flush_logs
):
    response = client.get("/api/v1/users/me", headers=admin_headers)

    flush_logs()
    access = [
        e
        for e in log_repository.by_event("http.request")
        if e.details["path"] == "/api/v1/users/me"
    ]
    (entry,) = access
    assert entry.request_id == response.headers["x-request-id"]  # enlazado con la respuesta
    assert entry.user_id and entry.session_id
    assert entry.details["method"] == "GET" and entry.details["status"] == 200
    assert entry.details["duration_ms"] >= 0


def test_los_niveles_dependen_del_estado_http(
    client, admin_headers, log_repository, flush_logs, make_app
):
    client.get("/api/v1/no-existe")  # 404
    app = make_app()

    @app.get("/_boom")
    async def boom() -> None:
        raise RuntimeError("fallo interno")

    @app.get("/_conflict")
    async def conflict() -> None:
        raise HTTPException(status_code=409, detail="x")

    with TestClient(app, raise_server_exceptions=False) as other:
        other.get("/_boom")
        other.get("/_conflict")
        other.portal.call(other.app.state.events.flush)
    flush_logs()

    by_status = {e.details["status"]: e.level for e in log_repository.by_event("http.request")}
    assert by_status[404] == by_status[409] == "WARNING"
    assert by_status[500] == "ERROR"


def test_no_se_registran_las_sondas_la_documentacion_ni_la_consulta_de_la_bitacora(
    client, admin_headers, log_repository, flush_logs
):
    client.get("/health")
    client.get("/health/ready")
    client.get("/docs")
    client.get(LOGS, headers=admin_headers)
    client.get(f"{LOGS}/modules", headers=admin_headers)

    flush_logs()
    paths = {e.details["path"] for e in log_repository.by_event("http.request")}
    assert not any(path.startswith(("/health", "/docs", LOGS)) for path in paths)


def test_las_excepciones_no_controladas_llegan_a_la_bitacora_por_el_puente_de_python(
    make_app, log_repository
):
    app = make_app()

    @app.get("/_boom")
    async def boom() -> None:
        raise RuntimeError("fallo interno")

    with TestClient(app, raise_server_exceptions=False) as client:
        client.get("/_boom")
        client.portal.call(client.app.state.events.flush)

    python_errors = [
        e for e in log_repository.items if e.event.startswith("python.") and e.level == "ERROR"
    ]
    assert any(e.details.get("exception") == "RuntimeError: fallo interno" for e in python_errors)


# ── Nunca se registran secretos ─────────────────────────────────────────────────
def test_ningun_evento_contiene_contrasenas_ni_tokens(
    client, log_repository, flush_logs, outbox, register_user
):
    secretos = ["Segura#12345", "Nueva#Clave987", "Mala#12345", "Admin#12345"]
    user = register_user(password="Segura#12345")
    client.post("/api/v1/auth/login", json={"email": "ana@example.com", "password": "Mala#12345"})
    login_body = login(client, "ana@example.com", "Segura#12345")
    client.post("/api/v1/auth/password-reset-requests", json={"email": "ana@example.com"})
    reset_token = outbox.last_reset_token()
    client.post(
        "/api/v1/auth/password-resets", json={"token": reset_token, "password": "Nueva#Clave987"}
    )
    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    refresh_cookie = client.cookies.get("centynella_refresh")

    flush_logs()
    everything = json.dumps([entry.model_dump(mode="json") for entry in log_repository.items])
    for secreto in [*secretos, reset_token, login_body["access_token"], refresh_cookie]:
        assert secreto not in everything
    assert user["id"] in everything  # sí queda el identificador, que no es secreto


# ── Consulta de la bitácora ─────────────────────────────────────────────────────
def test_la_consulta_exige_el_permiso_logs_read(client, admin_headers, register_user):
    register_user()
    viewer = auth_headers(login(client, "ana@example.com", USER_PASSWORD)["access_token"])
    client.post(
        "/api/v1/users",
        json={
            "name": "Gina",
            "email": "gina@example.com",
            "password": USER_PASSWORD,
            "role": "manager",
        },
        headers=admin_headers,
    )
    manager = auth_headers(login(client, "gina@example.com", USER_PASSWORD)["access_token"])

    assert client.get(LOGS).status_code == 401
    assert client.get(LOGS, headers=viewer).status_code == 403
    assert client.get(LOGS, headers=manager).status_code == 403  # manager no tiene logs:read
    assert client.get(LOGS, headers=admin_headers).status_code == 200
    assert client.get(f"{LOGS}/modules", headers=viewer).status_code == 403


def test_filtra_por_modulo_usuario_sesion_y_peticion(
    client, admin_headers, register_user, flush_logs
):
    user = register_user()
    body = login(client, "ana@example.com", USER_PASSWORD)
    sid = session_of(client, body["access_token"])
    flush_logs()

    by_module = client.get(LOGS, params={"module": "auth"}, headers=admin_headers).json()
    by_user = client.get(LOGS, params={"user_id": user["id"]}, headers=admin_headers).json()
    by_session = client.get(LOGS, params={"session_id": sid}, headers=admin_headers).json()

    assert by_module["total"] > 0 and {i["module"] for i in by_module["items"]} == {"auth"}
    assert by_user["total"] > 0 and {i["user_id"] for i in by_user["items"]} == {user["id"]}
    assert by_session["total"] > 0 and {i["session_id"] for i in by_session["items"]} == {sid}
    request_id = by_session["items"][0]["request_id"]
    by_request = client.get(LOGS, params={"request_id": request_id}, headers=admin_headers).json()
    assert by_request["total"] >= 1 and {i["request_id"] for i in by_request["items"]} == {
        request_id
    }


def test_filtra_por_nivel_minimo_evento_y_texto(client, admin_headers, flush_logs):
    client.post("/api/v1/auth/login", json={"email": "nadie@example.com", "password": "Mala#12345"})
    flush_logs()

    warnings = client.get(LOGS, params={"level": "WARNING"}, headers=admin_headers).json()
    by_event = client.get(LOGS, params={"event": "auth.login.failed"}, headers=admin_headers).json()
    by_text = client.get(LOGS, params={"q": "LOGIN fallido"}, headers=admin_headers).json()

    assert warnings["total"] > 0 and {i["level"] for i in warnings["items"]} <= {
        "WARNING",
        "ERROR",
        "CRITICAL",
    }
    assert by_event["total"] == 1 and by_text["total"] >= 1


def test_filtra_por_rango_de_fechas(client, admin_headers, flush_logs):
    flush_logs()

    future = client.get(
        LOGS, params={"since": "2999-01-01T00:00:00Z"}, headers=admin_headers
    ).json()
    past = client.get(LOGS, params={"until": "2000-01-01T00:00:00Z"}, headers=admin_headers).json()
    everything = client.get(
        LOGS, params={"since": "2000-01-01T00:00:00Z"}, headers=admin_headers
    ).json()

    assert future["total"] == 0 and past["total"] == 0 and everything["total"] > 0


def test_pagina_los_resultados_mas_recientes_primero(client, admin_headers, flush_logs):
    for _ in range(4):
        client.post(
            "/api/v1/auth/login", json={"email": "nadie@example.com", "password": "Mala#12345"}
        )
    flush_logs()

    page1 = client.get(LOGS, params={"page": 1, "page_size": 2}, headers=admin_headers).json()
    page2 = client.get(LOGS, params={"page": 2, "page_size": 2}, headers=admin_headers).json()

    assert len(page1["items"]) == 2 and len(page2["items"]) == 2
    assert page1["total"] == page2["total"] > 4
    assert (
        page1["items"][0]["timestamp"]
        >= page1["items"][1]["timestamp"]
        >= page2["items"][0]["timestamp"]
    )
    assert {i["id"] for i in page1["items"]}.isdisjoint({i["id"] for i in page2["items"]})


def test_lista_los_modulos_que_han_registrado_eventos(client, admin_headers, flush_logs):
    flush_logs()

    modules = client.get(f"{LOGS}/modules", headers=admin_headers).json()

    assert {"auth", "database", "system"} <= set(modules)
    assert modules == sorted(modules)


def test_valida_los_parametros_de_la_consulta(client, admin_headers):
    for params in (
        {"page": 0},
        {"page_size": 101},
        {"level": "RARO"},
        {"since": "no-es-fecha"},
        {"q": "x" * 101},
    ):
        assert client.get(LOGS, params=params, headers=admin_headers).status_code == 422


def test_el_401_esperado_al_restaurar_la_sesion_no_es_una_advertencia(
    client, log_repository, flush_logs
):
    client.post("/api/v1/auth/refresh")  # visitante anónimo: sin cookie
    client.post("/api/v1/auth/login", json={"email": "nadie@example.com", "password": "Mala#12345"})

    flush_logs()
    by_path = {e.details["path"]: e for e in log_repository.by_event("http.request")}
    assert by_path["/api/v1/auth/refresh"].details["status"] == 401
    assert by_path["/api/v1/auth/refresh"].level == "INFO"  # comportamiento normal
    assert (
        by_path["/api/v1/auth/login"].level == "WARNING"
    )  # un login fallido sí es una advertencia
