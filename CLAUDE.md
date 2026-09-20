# CENTYNELLA-CORE (backend)

Backend FastAPI + MongoDB de la plataforma de inventarios CENTYNELLA. Su frontend es otro repo (`C:\github\centynella-mfe`). **Nunca mezclar código de frontend aquí.**

## Comandos (Windows, usar el `venv` del repo)

```bash
venv/Scripts/python.exe -m pytest --cov        # pruebas (cobertura mínima 80 %)
venv/Scripts/python.exe -m ruff check . && venv/Scripts/python.exe -m ruff format --check .
docker compose --profile local up -d mongo     # Mongo local (opcional; por defecto se usa Atlas)
python app.py                                  # API en :8000 (Swagger en /docs). NO existe `app:app`: usa `uvicorn app:create_app --factory`
```

## Estructura obligatoria

`app.py` (NO `main.py`) en la raíz · `private/` con los `.env.<sandbox|production>` · `src/` modularizado en `config`, `database`, `dtos`, `middlewares`, `models`, `routes`, `services` · `tests/` · `.github/workflows/deploy.yml` · `.gitignore` y `.dockerignore` · `Dockerfile` · `README.md`.

## Reglas

- **API RESTful estricta:** versionada en `/api/v1`, recursos en sustantivos, verbos y códigos HTTP correctos, errores `application/problem+json` (RFC 9457).
- **Swagger obligatorio:** todo endpoint con `summary`, `description`, `response_model` y respuestas de error documentadas. Endpoint de salud siempre presente.
- Rutas sin lógica de negocio: `route` → `service` → `repository` (interfaz en `src/database/repositories/interfaces.py`; implementación Mongo en `mongo.py`). Dependencias por `Depends` (`src/routes/dependencies.py`).
- **Seguridad:** los endpoints se protegen por PERMISO (`Depends(require_permission(Permission.X))`), nunca por rol. Los permisos nuevos se añaden al enum `Permission` en `src/models/permissions.py`. Errores de negocio = `DomainError` (con `code` estable) en `src/services/errors.py`.
- La sesión usa access JWT (memoria del frontend) + refresh token rotativo en cookie HttpOnly. Nunca guardar tokens/contraseñas en claro (solo hash).
- Clean code, **patrones de diseño**, docstrings, reutilización. Los modelos heredan de `BaseDocument`.
- **Patrones MongoDB** cuando se amerite: set, subset, reference, extended reference.
- Tests **antes** de desplegar; unitarias con repositorios en memoria (`tests/fakes.py`), integración con marca `integration`. Todo repositorio nuevo se cubre en `tests/test_repository_contract.py` (memoria + Mongo).
- `.env` solo en `private/` (ignorado por git y Docker). Nunca secretos en el repo ni en la imagen.
- **MongoDB Atlas** (un cluster, una base por ambiente): `centynella_sandbox` y `centynella_production`. La conexión vive SOLO en este backend; el frontend jamás se conecta a Mongo.
- **Actualizar el README en cada despliegue de cambios** (incluida la sección "Historial de cambios").
- Todo proyecto nuevo debe seguir esta misma estructura.
