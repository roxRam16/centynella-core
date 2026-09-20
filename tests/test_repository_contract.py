"""Contrato de los repositorios: la MISMA batería contra memoria y contra MongoDB real.

· `memory`: siempre corre (es el doble que usan las demás pruebas).
· `mongo`: marca `integration`; requiere MongoDB local
  (`docker compose --profile local up -d mongo`). Usa una base temporal
  `centynella_test_<uuid>` que se elimina al terminar. Otra URI: `TEST_MONGODB_URI`.
"""

import os
from datetime import timedelta
from uuid import uuid4

import pytest
from pymongo import AsyncMongoClient

from src.database import DuplicateError, Repositories, build_mongo_repositories
from src.models import (
    PasswordResetDocument,
    RefreshTokenDocument,
    RoleDocument,
    UserDocument,
    utc_now,
)
from tests.fakes import build_in_memory_repositories

pytestmark = pytest.mark.anyio

BACKENDS = ["memory", pytest.param("mongo", marks=pytest.mark.integration)]


@pytest.fixture(params=BACKENDS)
async def repos(request) -> Repositories:
    if request.param == "memory":
        yield build_in_memory_repositories()
        return

    uri = os.getenv("TEST_MONGODB_URI", "mongodb://localhost:27017")
    client: AsyncMongoClient = AsyncMongoClient(uri, tz_aware=True, serverSelectionTimeoutMS=2000)
    db_name = f"centynella_test_{uuid4().hex[:10]}"
    repositories = build_mongo_repositories(client[db_name])
    await repositories.ensure_indexes()
    yield repositories
    await client.drop_database(db_name)
    await client.close()


def make_user(email: str = "ana@example.com", **overrides) -> UserDocument:
    return UserDocument(
        **{"email": email, "name": "Ana", "password_hash": "hash", "role": "viewer", **overrides}
    )


# ── Usuarios ────────────────────────────────────────────────────────────────────
async def test_usuario_crear_y_leer(repos):
    created = await repos.users.create(make_user())

    assert created.id
    by_id = await repos.users.get(created.id)
    by_email = await repos.users.get_by_email("ana@example.com")
    assert by_id and by_id.email == "ana@example.com"
    assert by_email and by_email.id == created.id
    assert by_id.created_at.tzinfo is not None  # las fechas conservan la zona horaria
    assert by_id.providers[0].provider == "password"


async def test_usuario_lectura_de_inexistente(repos):
    assert await repos.users.get("no-existe") is None
    assert await repos.users.get_by_email("nadie@example.com") is None


async def test_usuario_correo_unico(repos):
    await repos.users.create(make_user())

    with pytest.raises(DuplicateError) as error:
        await repos.users.create(make_user())

    assert error.value.field == "email"


async def test_usuario_actualizar(repos):
    user = await repos.users.create(make_user())

    updated = await repos.users.update(user.id, {"name": "Ana María", "role": "manager"})

    assert updated.name == "Ana María" and updated.role == "manager"
    assert updated.updated_at >= user.updated_at
    assert (await repos.users.get(user.id)).name == "Ana María"


async def test_usuario_actualizar_inexistente(repos):
    assert await repos.users.update("no-existe", {"name": "X"}) is None


async def test_usuario_actualizar_campos_opcionales_a_none(repos):
    user = await repos.users.create(make_user(locked_until=utc_now() + timedelta(minutes=5)))

    updated = await repos.users.update(user.id, {"locked_until": None})

    assert updated.locked_until is None


async def test_usuario_eliminar(repos):
    user = await repos.users.create(make_user())

    assert await repos.users.delete(user.id) is True
    assert await repos.users.delete(user.id) is False
    assert await repos.users.get(user.id) is None


async def test_usuario_listado_paginado_y_ordenado(repos):
    start = utc_now()
    for index in range(5):
        created_at = start + timedelta(seconds=index)  # fechas explícitas: el reloj puede empatar
        await repos.users.create(make_user(f"u{index}@example.com", created_at=created_at))

    page1, total = await repos.users.list(query=None, role=None, status=None, page=1, page_size=2)
    page3, _ = await repos.users.list(query=None, role=None, status=None, page=3, page_size=2)

    assert total == 5
    assert [u.email for u in page1] == ["u4@example.com", "u3@example.com"]  # recientes primero
    assert [u.email for u in page3] == ["u0@example.com"]


async def test_usuario_listado_con_filtros(repos):
    await repos.users.create(make_user("carla@example.com", name="Carla Ruiz", role="manager"))
    await repos.users.create(make_user("diego@example.com", name="Diego Paz", status="disabled"))
    everything = {"role": None, "status": None, "page": 1, "page_size": 10}

    by_text, _ = await repos.users.list(query="RUIZ", **everything)
    by_email, _ = await repos.users.list(query="diego@", **everything)
    by_role, _ = await repos.users.list(query=None, **{**everything, "role": "manager"})
    by_status, _ = await repos.users.list(query=None, **{**everything, "status": "disabled"})

    assert [u.email for u in by_text] == ["carla@example.com"]  # sin distinguir mayúsculas
    assert [u.email for u in by_email] == ["diego@example.com"]
    assert [u.email for u in by_role] == ["carla@example.com"]
    assert [u.email for u in by_status] == ["diego@example.com"]


async def test_usuario_busqueda_trata_el_texto_como_literal_no_como_regex(repos):
    await repos.users.create(make_user("a@example.com", name="Ana"))

    found, total = await repos.users.list(query=".*", role=None, status=None, page=1, page_size=10)

    assert (found, total) == ([], 0)  # `.*` NO es un comodín


async def test_usuario_conteo(repos):
    await repos.users.create(make_user("a@example.com", role="admin"))
    await repos.users.create(make_user("b@example.com", role="admin", status="disabled"))
    await repos.users.create(make_user("c@example.com"))

    assert await repos.users.count() == 3
    assert await repos.users.count(role="admin") == 2
    assert await repos.users.count(role="admin", status="active") == 1


# ── Roles ───────────────────────────────────────────────────────────────────────
async def test_rol_crear_leer_listar(repos):
    await repos.roles.create(RoleDocument(id="b-rol", name="B", permissions=["users:read"]))
    await repos.roles.create(RoleDocument(id="a-rol", name="A", is_system=True))

    role = await repos.roles.get("b-rol")
    assert role.key == "b-rol" and role.permissions == ["users:read"]
    assert [r.key for r in await repos.roles.list()] == ["a-rol", "b-rol"]
    assert await repos.roles.get("fantasma") is None


async def test_rol_clave_unica(repos):
    await repos.roles.create(RoleDocument(id="rol", name="Uno"))

    with pytest.raises(DuplicateError) as error:
        await repos.roles.create(RoleDocument(id="rol", name="Dos"))

    assert error.value.field == "key"


async def test_rol_actualizar_y_eliminar(repos):
    await repos.roles.create(RoleDocument(id="rol", name="Uno"))

    updated = await repos.roles.update("rol", {"permissions": ["roles:read"]})

    assert updated.permissions == ["roles:read"]
    assert await repos.roles.update("fantasma", {"name": "X"}) is None
    assert await repos.roles.delete("rol") is True
    assert await repos.roles.delete("rol") is False


# ── Refresh tokens ──────────────────────────────────────────────────────────────
def make_refresh(token_hash: str, *, user_id: str = "u1", family: str = "f1"):
    return RefreshTokenDocument(
        user_id=user_id,
        token_hash=token_hash,
        family_id=family,
        expires_at=utc_now() + timedelta(days=1),
    )


async def test_refresh_crear_y_buscar_por_hash(repos):
    created = await repos.refresh_tokens.create(make_refresh("h1"))

    found = await repos.refresh_tokens.get_by_hash("h1")

    assert found.id == created.id and found.revoked_at is None
    assert await repos.refresh_tokens.get_by_hash("otro") is None


async def test_refresh_rotar_marca_revocado_y_rotado(repos):
    token = await repos.refresh_tokens.create(make_refresh("h1"))

    await repos.refresh_tokens.rotate(token.id)
    first = await repos.refresh_tokens.get_by_hash("h1")
    await repos.refresh_tokens.rotate(token.id)  # idempotente: no cambia las fechas
    second = await repos.refresh_tokens.get_by_hash("h1")

    assert first.revoked_at is not None and first.rotated_at is not None
    assert second.revoked_at == first.revoked_at


async def test_refresh_revocar_familia_no_marca_rotado(repos):
    await repos.refresh_tokens.create(make_refresh("h1", family="fam"))
    await repos.refresh_tokens.create(make_refresh("h2", family="fam"))
    await repos.refresh_tokens.create(make_refresh("h3", family="otra"))

    await repos.refresh_tokens.revoke_family("fam")

    h1 = await repos.refresh_tokens.get_by_hash("h1")
    assert h1.revoked_at is not None
    assert h1.rotated_at is None  # cerrado por logout/robo, no por rotación
    assert (await repos.refresh_tokens.get_by_hash("h2")).revoked_at is not None
    assert (await repos.refresh_tokens.get_by_hash("h3")).revoked_at is None


async def test_refresh_revocar_todos_los_del_usuario(repos):
    await repos.refresh_tokens.create(make_refresh("h1", user_id="u1", family="a"))
    await repos.refresh_tokens.create(make_refresh("h2", user_id="u1", family="b"))
    await repos.refresh_tokens.create(make_refresh("h3", user_id="u2", family="c"))

    await repos.refresh_tokens.revoke_all_for_user("u1")

    assert (await repos.refresh_tokens.get_by_hash("h1")).revoked_at is not None
    assert (await repos.refresh_tokens.get_by_hash("h2")).revoked_at is not None
    assert (await repos.refresh_tokens.get_by_hash("h3")).revoked_at is None


# ── Recuperación de contraseña ──────────────────────────────────────────────────
def make_reset(token_hash: str, user_id: str = "u1") -> PasswordResetDocument:
    return PasswordResetDocument(
        user_id=user_id, token_hash=token_hash, expires_at=utc_now() + timedelta(hours=1)
    )


async def test_reset_crear_buscar_y_marcar_usado(repos):
    reset = await repos.password_resets.create(make_reset("r1"))

    assert (await repos.password_resets.get_by_hash("r1")).used_at is None
    await repos.password_resets.mark_used(reset.id)

    assert (await repos.password_resets.get_by_hash("r1")).used_at is not None
    assert await repos.password_resets.get_by_hash("otro") is None


async def test_reset_invalidar_pendientes_del_usuario(repos):
    await repos.password_resets.create(make_reset("r1", "u1"))
    await repos.password_resets.create(make_reset("r2", "u1"))
    await repos.password_resets.create(make_reset("r3", "u2"))

    await repos.password_resets.invalidate_for_user("u1")

    assert (await repos.password_resets.get_by_hash("r1")).used_at is not None
    assert (await repos.password_resets.get_by_hash("r2")).used_at is not None
    assert (await repos.password_resets.get_by_hash("r3")).used_at is None
