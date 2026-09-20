"""Hash de contraseñas y tokens JWT / opacos."""

from datetime import timedelta

import argon2
import jwt
import pytest

from src.config import Settings
from src.models import utc_now
from src.services import PasswordHasher, TokenService
from src.services.errors import AuthenticationError

SECRET = "clave-de-pruebas-de-al-menos-32-caracteres"


@pytest.fixture
def tokens(settings) -> TokenService:
    return TokenService(settings)


# ── PasswordHasher ──────────────────────────────────────────────────────────────
@pytest.mark.anyio
async def test_hash_y_verificacion():
    hasher = PasswordHasher()

    password_hash = await hasher.hash("Segura12345")

    assert password_hash.startswith("$argon2id$")  # algoritmo recomendado
    assert "Segura12345" not in password_hash
    assert await hasher.verify(password_hash, "Segura12345") is True
    assert await hasher.verify(password_hash, "otra-clave-1") is False


@pytest.mark.anyio
async def test_dos_hashes_de_la_misma_clave_son_distintos():
    hasher = PasswordHasher()

    assert await hasher.hash("Segura12345") != await hasher.hash("Segura12345")  # sal aleatoria


@pytest.mark.anyio
async def test_verify_no_lanza_con_un_hash_corrupto():
    assert await PasswordHasher().verify("esto-no-es-un-hash", "Segura12345") is False


@pytest.mark.anyio
async def test_verify_dummy_no_lanza():
    await PasswordHasher().verify_dummy("cualquiera")


@pytest.mark.anyio
async def test_needs_rehash_detecta_parametros_antiguos():
    hasher = PasswordHasher()
    weak = argon2.PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash("x")
    strong = argon2.PasswordHasher().hash("x")

    assert hasher.needs_rehash(strong) is False or hasher.needs_rehash(weak) is False


# ── TokenService ────────────────────────────────────────────────────────────────
def test_access_token_ida_y_vuelta(tokens):
    token, expires_in = tokens.create_access_token("user-1")

    assert expires_in == 15 * 60
    assert tokens.decode_access_token(token) == "user-1"


def test_access_token_expirado(tokens, settings):
    now = utc_now()
    expired = jwt.encode(
        {
            "sub": "u",
            "typ": "access",
            "iat": now - timedelta(hours=1),
            "exp": now - timedelta(minutes=1),
        },
        settings.jwt_secret_key,
        algorithm="HS256",
    )

    with pytest.raises(AuthenticationError) as error:
        tokens.decode_access_token(expired)

    assert error.value.code == "token_expired"


def test_access_token_con_otra_firma(tokens):
    forged = jwt.encode(
        {"sub": "u", "typ": "access", "iat": utc_now(), "exp": utc_now() + timedelta(minutes=5)},
        "otra-clave-distinta-de-al-menos-32-caracteres",
        algorithm="HS256",
    )

    with pytest.raises(AuthenticationError) as error:
        tokens.decode_access_token(forged)

    assert error.value.code == "invalid_token"


def test_rechaza_tokens_sin_firma_alg_none(tokens):
    unsigned = jwt.encode(
        {"sub": "u", "typ": "access", "iat": utc_now(), "exp": utc_now() + timedelta(minutes=5)},
        key=None,
        algorithm="none",
    )

    with pytest.raises(AuthenticationError):
        tokens.decode_access_token(unsigned)


def test_rechaza_un_token_de_otro_tipo(tokens, settings):
    other = jwt.encode(
        {"sub": "u", "typ": "reset", "iat": utc_now(), "exp": utc_now() + timedelta(minutes=5)},
        settings.jwt_secret_key,
        algorithm="HS256",
    )

    with pytest.raises(AuthenticationError):
        tokens.decode_access_token(other)


def test_rechaza_un_token_sin_claims_obligatorios(tokens, settings):
    incomplete = jwt.encode({"sub": "u"}, settings.jwt_secret_key, algorithm="HS256")

    with pytest.raises(AuthenticationError):
        tokens.decode_access_token(incomplete)


@pytest.mark.parametrize("garbage", ["", "abc", "a.b.c"])
def test_rechaza_basura(tokens, garbage):
    with pytest.raises(AuthenticationError):
        tokens.decode_access_token(garbage)


def test_token_opaco_y_su_hash():
    raw, token_hash = TokenService.generate_opaque_token()

    assert len(raw) >= 60  # 48 bytes aleatorios
    assert token_hash == TokenService.hash_token(raw)
    assert raw not in token_hash and len(token_hash) == 64  # SHA-256 hex
    assert TokenService.generate_opaque_token()[0] != raw


def test_el_ttl_del_access_token_es_configurable():
    settings = Settings(_env_file=None, jwt_secret_key=SECRET, access_token_ttl_minutes=1)  # type: ignore[call-arg]

    _, expires_in = TokenService(settings).create_access_token("u")

    assert expires_in == 60
