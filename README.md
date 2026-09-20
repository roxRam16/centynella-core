# CENTYNELLA-CORE

Backend de **CENTYNELLA**, plataforma de administración y gestión de inventarios.
API RESTful construida con **FastAPI (Python 3.12)** y **MongoDB**, contenerizada con Docker y desplegada en AWS.

> El frontend vive en otro repositorio: [centynella-mfe](https://github.com/roxRam16/centynella-mfe) (shell de microfrontends). **Este repo no contiene código de frontend.**

## Stack

| Capa | Tecnología |
| --- | --- |
| API | FastAPI · Uvicorn · Pydantic v2 |
| Base de datos | MongoDB (driver oficial `pymongo` asíncrono) |
| Pruebas / calidad | pytest · pytest-cov · Ruff |
| Contenedores | Docker · Docker Compose |
| CI/CD | GitHub Actions → Amazon ECR + ECS |

## Estructura

```
centynella-core/
├── app.py                 # Punto de entrada (Application Factory: create_app)
├── src/
│   ├── config/            # Settings tipadas (pydantic-settings) leídas de private/.env.<ambiente>
│   ├── database/          # DatabaseManager: conexión única a MongoDB
│   ├── dtos/              # Contratos de entrada/salida de la API (Pydantic)
│   ├── middlewares/       # Request-ID y manejo de errores (RFC 9457)
│   ├── models/            # Documentos de MongoDB (BaseDocument y patrones de modelado)
│   ├── routes/            # Routers HTTP + dependencias (DI)
│   └── services/          # Lógica de negocio
├── tests/                 # Batería de pruebas
├── private/               # Variables de entorno (.env.<ambiente>) — NO versionadas
├── .github/workflows/     # deploy.yml
├── Dockerfile · docker-compose.yml · .dockerignore
├── requirements.txt       # Runtime          requirements-dev.txt → desarrollo/pruebas
└── venv/                  # Entorno virtual local (ignorado por git)
```

**Flujo de una petición:** `route` (valida con DTO) → `service` (lógica) → `database/model` (persistencia). Las rutas nunca contienen lógica de negocio.

## Puesta en marcha (local)

```bash
# 1. Entorno virtual e instalación
python -m venv venv
venv\Scripts\activate                 # Windows   (Linux/Mac: source venv/bin/activate)
pip install -r requirements-dev.txt

# 2. Variables de entorno
copy private\.env.example private\.env.sandbox     # y ajusta los valores

# 3. MongoDB: por defecto se usa Atlas (private/.env.sandbox → base centynella_sandbox).
#    Opcional, Mongo local: docker compose --profile local up -d mongo

# 4. API con recarga automática
python app.py                         # o: uvicorn app:app --reload --port 8000
```

| URL | Descripción |
| --- | --- |
| http://localhost:8000/docs | **Swagger UI** (documentación interactiva) |
| http://localhost:8000/redoc | ReDoc |
| http://localhost:8000/openapi.json | Esquema OpenAPI |
| http://localhost:8000/health | Liveness |
| http://localhost:8000/health/ready | Readiness (verifica MongoDB) |
| http://localhost:8000/api/v1/greeting | Hola Mundo |

## Endpoints

| Método | Ruta | Descripción | Respuestas |
| --- | --- | --- | --- |
| GET | `/health` | Liveness: el proceso está vivo | 200 |
| GET | `/health/ready` | Readiness: dependencias listas | 200 · 503 (`degraded`) |
| GET | `/api/v1/greeting` | Saludo *Hola Mundo* (prueba de humo) | 200 · 422 · 500 |

## Convenciones RESTful

- **Versionado en la URL:** `/api/v1/...`. Un cambio incompatible crea `/api/v2`.
- **Recursos = sustantivos** (`/products`, `/warehouses`); la acción la da el verbo HTTP: `GET` leer, `POST` crear (201 + `Location`), `PUT` reemplazar, `PATCH` modificar parcial, `DELETE` borrar (204).
- **Códigos de estado correctos:** 200, 201, 204, 400, 401, 403, 404, 409, 422, 500, 503.
- **Errores estándar** en `application/problem+json` ([RFC 9457](https://www.rfc-editor.org/rfc/rfc9457)) con `request_id` para rastrear.
- **Trazabilidad:** cada respuesta incluye `X-Request-ID` (se respeta el que envíe el cliente).
- **Documentación obligatoria:** cada endpoint lleva `summary`, `description`, `response_model` y sus respuestas de error para que Swagger quede completo.
- **Salud:** `/health` y `/health/ready` van fuera de `/api/v1` porque son infraestructura, no contrato de negocio.

## Configuración

Variables en `private/.env.<ambiente>` (elige el ambiente con `APP_ENV`, por defecto `sandbox`). Las variables del sistema **tienen prioridad** sobre el archivo — así se inyectan en contenedores/AWS. Plantilla en [private/.env.example](private/.env.example).

| Variable | Descripción | Por defecto |
| --- | --- | --- |
| `APP_ENV` | `sandbox` (developer) o `production` | `sandbox` |
| `MONGODB_URI` | Cadena de conexión (MongoDB Atlas, `mongodb+srv://…`) | `mongodb://localhost:27017` |
| `MONGODB_DB` | Base de datos del ambiente | `centynella` |
| `MONGODB_TIMEOUT_MS` | Timeout de selección de servidor | `2000` |
| `CORS_ORIGINS` | Orígenes permitidos (coma) — el shell del MFE | `http://localhost:5173` |
| `DOCS_ENABLED` | Habilita Swagger/ReDoc | `true` |

> `private/.env.*` está en `.gitignore` y `.dockerignore`: **nunca** se versiona ni entra a la imagen.

### Bases de datos por ambiente

Un mismo cluster de **MongoDB Atlas** con una base de datos separada por ambiente. La cadena de conexión solo vive en este backend (el frontend nunca se conecta a Mongo).

| Ambiente | `APP_ENV` | `MONGODB_DB` |
| --- | --- | --- |
| Developer | `sandbox` | `centynella_sandbox` |
| Producción | `production` | `centynella_production` |

Atlas debe tener tu IP (o la de AWS) en *Network Access*. En producción, inyecta `MONGODB_URI` desde AWS Secrets Manager y usa un usuario de base de datos distinto por ambiente, con permisos solo sobre su base.

## Patrones de diseño aplicados

| Patrón | Dónde |
| --- | --- |
| Application Factory | `create_app()` en `app.py` |
| Inyección de dependencias | `src/routes/dependencies.py` (`Depends`) |
| Capas (Route → Service → Persistencia) | `routes/` · `services/` · `database/` |
| Singleton | `get_settings()` (cacheada) |
| Connection Manager | `DatabaseManager` |
| DTO | `src/dtos/` |
| Chain of Responsibility (middlewares) | `RequestIdMiddleware`, CORS, handlers de error |
| Test Double | `FakeDatabase` en `tests/conftest.py` |

## Patrones de modelado en MongoDB

Se aplican **cuando el caso lo amerita** (documentado en [src/models/base.py](src/models/base.py)); todos los modelos heredan de `BaseDocument` (`_id`, `created_at`, `updated_at`).

- **Set / Subset:** embeber lo que se lee junto (p. ej. los últimos N movimientos dentro del producto) y dejar el histórico completo en su colección.
- **Reference:** guardar solo el `_id` cuando el dato relacionado cambia mucho o se consulta aparte.
- **Extended Reference:** referencia + copia de los pocos campos que siempre se muestran (`{category_id, category_name}`) para evitar `$lookup`.

## Pruebas

```bash
pytest                       # unitarias (no requieren Mongo real)
pytest --cov                 # con cobertura (mínimo 80 %)
pytest -m integration        # ping a la MongoDB del ambiente activo (APP_ENV, por defecto sandbox)
ruff check . && ruff format --check .
```

Las unitarias inyectan un `FakeDatabase`; así corren en cualquier lugar y en el CI. **Ningún despliegue corre sin pasar la batería completa.**

## Docker

```bash
docker compose up -d --build                 # API (:8000) contra MongoDB Atlas (sandbox)
docker compose --profile local up -d mongo   # opcional: Mongo local (:27017)
docker compose down                          # detiene la API

# Solo la imagen de la API
docker build -t centynella-core .
docker run --rm -p 8000:8000 --env-file private/.env.sandbox centynella-core
```

La imagen usa `python:3.12-slim`, corre como usuario sin privilegios e incluye `HEALTHCHECK` sobre `/health`.

## CI/CD

[.github/workflows/deploy.yml](.github/workflows/deploy.yml): `test` (Ruff + pytest con cobertura) → `deploy` (build → push a ECR → `ecs update-service`). Hoy se dispara **manualmente** (`workflow_dispatch`) hasta terminar la configuración de AWS.

Requiere en GitHub (por *Environment* `sandbox` / `production`): secreto `AWS_ROLE_ARN` y variables `AWS_REGION`, `ECR_REPOSITORY`, `ECS_CLUSTER`, `ECS_SERVICE`.

## Reglas del proyecto

1. **README actualizado en cada despliegue de cambios.**
2. Clean code, patrones de diseño, código documentado y reutilización.
3. Tests antes de desplegar; cobertura ≥ 80 %.
4. Nada de frontend en este repo.

## Historial de cambios

### 0.2.0 — MongoDB Atlas
- Conexión a MongoDB Atlas con una base por ambiente: `centynella_sandbox` y `centynella_production`.
- `docker compose` usa Atlas por defecto; el Mongo local pasa a ser opcional (`--profile local`).
- La prueba de integración ahora hace ping a la base del ambiente activo.
- Timeout de conexión por defecto de los `.env` sube a 5 s (resolución SRV + TLS de Atlas).

### 0.1.0 — Base del proyecto
- Estructura modular `config / database / dtos / middlewares / models / routes / services`.
- API versionada `/api/v1` con Swagger, ReDoc y OpenAPI.
- Endpoints de salud (`/health`, `/health/ready`) y *Hola Mundo* (`/api/v1/greeting`).
- Errores estándar RFC 9457, `X-Request-ID` y CORS para el shell del MFE.
- Conexión a MongoDB (local por Docker Compose).
- Dockerfile, docker-compose, batería de pruebas (30 unitarias + 1 de integración) y workflow de despliegue.
