"""EventLogger: cola asíncrona, saneamiento, contexto y puente con `logging`."""

import asyncio
import logging

import pytest

from src.middlewares.context import RequestContext, reset_context, set_context
from src.services import BridgeLogHandler, EventLogger, mask_email
from src.services.event_logger import sanitize
from tests.fakes import InMemoryLogRepository

pytestmark = pytest.mark.anyio


def make_logger(repository=None, **overrides) -> tuple[EventLogger, InMemoryLogRepository]:
    repository = repository or InMemoryLogRepository()
    options = {"service": "core", "environment": "sandbox", "flush_interval": 0, "retry_delay": 0}
    return EventLogger(repository, **{**options, **overrides}), repository


# ── Saneamiento ─────────────────────────────────────────────────────────────────
def test_mask_email():
    assert mask_email("ana@example.com") == "a***@example.com"
    assert mask_email("sin-arroba") == "sin-arroba"
    assert mask_email(None) is None


def test_sanitize_oculta_secretos_a_cualquier_nivel():
    clean = sanitize(
        {
            "password": "Secreta#1",
            "nuevo_password": "x",
            "Authorization": "Bearer abc",
            "refresh_token": "t",
            "anidado": {"api_key": "k", "ok": 1},
            "cookie": "c",
            "normal": "visible",
        }
    )

    assert clean["password"] == clean["nuevo_password"] == clean["Authorization"] == "[oculto]"
    assert clean["refresh_token"] == clean["cookie"] == clean["anidado"]["api_key"] == "[oculto]"
    assert clean["normal"] == "visible" and clean["anidado"]["ok"] == 1


def test_sanitize_recorta_textos_y_listas_enormes():
    clean = sanitize({"texto": "x" * 5000, "lista": list(range(500))})

    assert len(clean["texto"]) == 2001 and clean["texto"].endswith("…")
    assert len(clean["lista"]) == 50


def test_sanitize_hace_las_claves_compatibles_con_mongo():
    assert sanitize({"a.b": 1, "$peligro": 2}) == {"a_b": 1, "peligro": 2}


def test_sanitize_convierte_tipos_no_json_y_limita_la_profundidad():
    class Raro:
        def __str__(self) -> str:
            return "raro"

    profundo: dict = {}
    cursor = profundo
    for _ in range(10):
        cursor["x"] = {}
        cursor = cursor["x"]

    assert sanitize({"obj": Raro()}) == {"obj": "raro"}
    assert "[demasiado anidado]" in str(sanitize(profundo))


# ── Registro y cola ─────────────────────────────────────────────────────────────
async def test_los_eventos_se_guardan_por_el_trabajador():
    events, repository = make_logger()
    await events.start()

    events.info(
        "auth", "auth.login.success", "Sesión iniciada", user_id="u1", session_id="s1", extra=1
    )
    await events.flush()

    (entry,) = repository.items
    assert (entry.level, entry.service, entry.module, entry.event) == (
        "INFO",
        "core",
        "auth",
        "auth.login.success",
    )
    assert (entry.user_id, entry.session_id, entry.environment) == ("u1", "s1", "sandbox")
    assert entry.details == {"extra": 1}
    await events.stop()


async def test_log_no_bloquea_ni_espera_a_la_base():
    events, repository = make_logger()  # sin start(): nada consume la cola

    events.info("system", "x", "y")

    assert repository.items == []  # encolado, no guardado (y `log` volvió al instante)


async def test_filtra_por_nivel_minimo():
    events, repository = make_logger(min_level="WARNING")
    await events.start()

    events.debug("m", "e.debug", "no")
    events.info("m", "e.info", "no")
    events.warning("m", "e.warning", "sí")
    events.error("m", "e.error", "sí")
    events.critical("m", "e.critical", "sí")
    await events.flush()

    assert [e.event for e in repository.items] == ["e.warning", "e.error", "e.critical"]
    await events.stop()


async def test_toma_usuario_sesion_ip_y_request_id_del_contexto():
    events, repository = make_logger()
    await events.start()
    token = set_context(
        RequestContext(request_id="req-1", user_id="u9", session_id="s9", ip="10.0.0.5")
    )

    events.info("users", "users.updated", "x")
    reset_context(token)
    await events.flush()

    entry = repository.items[0]
    assert (entry.request_id, entry.user_id, entry.session_id, entry.ip) == (
        "req-1",
        "u9",
        "s9",
        "10.0.0.5",
    )
    await events.stop()


async def test_los_parametros_explicitos_ganan_al_contexto():
    events, repository = make_logger()
    await events.start()
    token = set_context(RequestContext(user_id="del-contexto"))

    events.info("auth", "e", "m", user_id="explicito")
    reset_context(token)
    await events.flush()

    assert repository.items[0].user_id == "explicito"
    await events.stop()


async def test_descarta_y_cuenta_cuando_la_cola_esta_llena():
    events, repository = make_logger(queue_size=2)

    for index in range(5):
        events.info("m", f"e.{index}", "x")

    assert events.dropped == 3
    await events.start()
    await events.flush()
    assert len(repository.items) == 2
    await events.stop()


async def test_guarda_por_lotes():
    class CountingRepository(InMemoryLogRepository):
        def __init__(self) -> None:
            super().__init__()
            self.batches: list[int] = []

        async def insert_many(self, entries):
            self.batches.append(len(entries))
            await super().insert_many(entries)

    repository = CountingRepository()
    events, _ = make_logger(repository, batch_size=3)
    for index in range(7):
        events.info("m", f"e.{index}", "x")
    await events.start()
    await events.flush()

    assert repository.batches == [3, 3, 1]
    await events.stop()


async def test_reintenta_y_si_la_base_sigue_caida_descarta_sin_romper(caplog):
    repository = InMemoryLogRepository()
    repository.fail = True
    events, _ = make_logger(repository)
    await events.start()

    with caplog.at_level(logging.ERROR):
        events.info("m", "e", "x")
        await events.flush()

    assert events.dropped == 1
    assert "Se perdieron 1 eventos" in caplog.text
    # La app sigue viva: cuando la base vuelve, se sigue registrando.
    repository.fail = False
    events.info("m", "e2", "y")
    await events.flush()
    assert [e.event for e in repository.items] == ["e2"]
    await events.stop()


async def test_se_recupera_de_un_fallo_transitorio():
    class Flaky(InMemoryLogRepository):
        calls = 0

        async def insert_many(self, entries):
            Flaky.calls += 1
            if Flaky.calls == 1:
                raise RuntimeError("timeout")
            await super().insert_many(entries)

    repository = Flaky()
    events, _ = make_logger(repository)
    await events.start()

    events.info("m", "e", "x")
    await events.flush()

    assert len(repository.items) == 1 and events.dropped == 0
    await events.stop()


async def test_stop_guarda_lo_pendiente_y_es_idempotente():
    events, repository = make_logger()
    await events.start()
    await events.start()  # idempotente

    events.info("m", "e", "x")
    await events.stop()
    await events.stop()

    assert len(repository.items) == 1


async def test_stop_no_se_cuelga_si_no_se_pudo_guardar(caplog):
    class Slow(InMemoryLogRepository):
        async def insert_many(self, entries):
            await asyncio.sleep(10)

    events, _ = make_logger(Slow())
    await events.start()
    events.info("m", "e", "x")

    with caplog.at_level(logging.WARNING):
        await events.stop(timeout=0.05)

    assert "sin guardar" in caplog.text


# ── Puente con logging ──────────────────────────────────────────────────────────
async def test_el_puente_reenvia_avisos_y_errores_de_python():
    events, repository = make_logger()
    await events.start()
    logger = logging.getLogger("src.database.mongo")
    handler = BridgeLogHandler(events)
    logger.addHandler(handler)
    try:
        logger.warning("MongoDB no responde")
        try:
            raise ValueError("boom")
        except ValueError:
            logging.getLogger("src.otra").addHandler(handler)
            logging.getLogger("src.otra").exception("Falló algo")
        logger.info("esto es INFO: no se reenvía")
        await events.flush()
    finally:
        logger.removeHandler(handler)
        logging.getLogger("src.otra").removeHandler(handler)

    by_module = {e.event: e for e in repository.items}
    assert by_module["python.src.database.mongo"].module == "database"
    assert by_module["python.src.database.mongo"].level == "WARNING"
    assert by_module["python.src.otra"].level == "ERROR"
    assert by_module["python.src.otra"].details["exception"] == "ValueError: boom"
    assert len(repository.items) == 2
    await events.stop()


async def test_el_puente_ignora_pymongo_y_su_propio_modulo_para_evitar_bucles():
    events, repository = make_logger()
    await events.start()
    handler = BridgeLogHandler(events)
    for name in ("pymongo.topology", "src.services.event_logger"):
        logging.getLogger(name).addHandler(handler)
        logging.getLogger(name).warning("ruido")
        logging.getLogger(name).removeHandler(handler)
    await events.flush()

    assert repository.items == []
    await events.stop()
