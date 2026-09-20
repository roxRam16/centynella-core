from src.config import Settings, get_settings, resolve_env_file


def test_valores_por_defecto(monkeypatch):
    for variable in ("APP_ENV", "MONGODB_URI", "CORS_ORIGINS"):
        monkeypatch.delenv(variable, raising=False)

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.app_env == "sandbox"
    assert settings.mongodb_uri == "mongodb://localhost:27017"
    assert settings.cors_origins == ["http://localhost:5173"]


def test_lee_el_archivo_env(tmp_path, monkeypatch):
    monkeypatch.delenv("MONGODB_DB", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    env_file = tmp_path / ".env.sandbox"
    env_file.write_text("MONGODB_DB=otra_db\nAPP_ENV=production\n", encoding="utf-8")

    settings = Settings(_env_file=env_file)  # type: ignore[call-arg]

    assert settings.mongodb_db == "otra_db"
    assert settings.app_env == "production"


def test_cors_origins_acepta_lista_separada_por_comas(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test, http://b.test ,")

    assert Settings(_env_file=None).cors_origins == [  # type: ignore[call-arg]
        "http://a.test",
        "http://b.test",
    ]


def test_variables_del_sistema_tienen_prioridad_sobre_el_archivo(monkeypatch, tmp_path):
    env_file = tmp_path / ".env.sandbox"
    env_file.write_text("MONGODB_DB=desde_archivo\n", encoding="utf-8")
    monkeypatch.setenv("MONGODB_DB", "desde_sistema")

    assert Settings(_env_file=env_file).mongodb_db == "desde_sistema"  # type: ignore[call-arg]


def test_resolve_env_file_usa_app_env(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")

    assert resolve_env_file().name == ".env.production"
    assert resolve_env_file("sandbox").name == ".env.sandbox"


def test_get_settings_es_singleton():
    get_settings.cache_clear()

    assert get_settings() is get_settings()
