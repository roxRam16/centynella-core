import pytest
from pydantic import ValidationError

from src.config import Settings, get_settings, resolve_env_file

SECRET = "clave-de-pruebas-de-al-menos-32-caracteres"


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    """Las pruebas no deben depender de variables reales del equipo."""
    for variable in ("APP_ENV", "MONGODB_URI", "MONGODB_DB", "CORS_ORIGINS", "JWT_SECRET_KEY"):
        monkeypatch.delenv(variable, raising=False)


def test_valores_por_defecto():
    settings = Settings(_env_file=None, jwt_secret_key=SECRET)  # type: ignore[call-arg]

    assert settings.app_env == "sandbox"
    assert settings.mongodb_uri == "mongodb://localhost:27017"
    assert settings.cors_origins == ["http://localhost:5173"]
    assert settings.access_token_ttl_minutes == 15
    assert settings.registration_enabled is True


def test_la_app_no_arranca_sin_secreto_jwt():
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_rechaza_un_secreto_jwt_corto():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, jwt_secret_key="corto")  # type: ignore[call-arg]


def test_lee_el_archivo_env(tmp_path):
    env_file = tmp_path / ".env.sandbox"
    env_file.write_text(
        f"MONGODB_DB=otra_db\nAPP_ENV=production\nJWT_SECRET_KEY={SECRET}\n", encoding="utf-8"
    )

    settings = Settings(_env_file=env_file)  # type: ignore[call-arg]

    assert settings.mongodb_db == "otra_db"
    assert settings.app_env == "production"


def test_cors_origins_acepta_lista_separada_por_comas(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test, http://b.test ,")

    settings = Settings(_env_file=None, jwt_secret_key=SECRET)  # type: ignore[call-arg]

    assert settings.cors_origins == ["http://a.test", "http://b.test"]


def test_el_comodin_cors_se_descarta_de_los_origenes_efectivos():
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None, jwt_secret_key=SECRET, cors_origins=["http://a.test", "*"]
    )

    assert settings.explicit_cors_origins == ["http://a.test"]


def test_produccion_rechaza_el_comodin_cors():
    with pytest.raises(ValidationError, match="CORS_ORIGINS"):
        Settings(  # type: ignore[call-arg]
            _env_file=None, jwt_secret_key=SECRET, app_env="production", cors_origins=["*"]
        )


def test_la_cookie_solo_es_secure_en_produccion():
    sandbox = Settings(_env_file=None, jwt_secret_key=SECRET)  # type: ignore[call-arg]
    production = Settings(_env_file=None, jwt_secret_key=SECRET, app_env="production")  # type: ignore[call-arg]

    assert sandbox.cookie_secure is False
    assert production.cookie_secure is True


def test_variables_del_sistema_tienen_prioridad_sobre_el_archivo(monkeypatch, tmp_path):
    env_file = tmp_path / ".env.sandbox"
    env_file.write_text(f"MONGODB_DB=desde_archivo\nJWT_SECRET_KEY={SECRET}\n", encoding="utf-8")
    monkeypatch.setenv("MONGODB_DB", "desde_sistema")

    assert Settings(_env_file=env_file).mongodb_db == "desde_sistema"  # type: ignore[call-arg]


def test_resolve_env_file_usa_app_env(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")

    assert resolve_env_file().name == ".env.production"
    assert resolve_env_file("sandbox").name == ".env.sandbox"


def test_get_settings_es_singleton(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", SECRET)
    get_settings.cache_clear()

    assert get_settings() is get_settings()
    get_settings.cache_clear()
