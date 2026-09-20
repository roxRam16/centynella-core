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
├── app.py                 # Punto de entrada (Application Factory: `create_app`)
├── src/
│   ├── config/            # Settings tipadas (pydantic-settings) leídas de private/.env.<ambiente>
│   ├── database/          # DatabaseManager + repositorios (interfaces y MongoDB)
│   ├── dtos/              # Contratos de entrada/salida de la API (Pydantic)
│   ├── middlewares/       # Request-ID/contexto, log de acceso, seguridad HTTP y errores (RFC 9457)
│   ├── models/            # Documentos de MongoDB, permisos y roles de sistema
│   ├── routes/            # Routers HTTP + dependencias (DI)
│   └── services/          # Lógica de negocio: auth, usuarios, roles, tokens, correo
├── tests/                 # Batería de pruebas
├── private/               # Variables de entorno (.env.<ambiente>) — NO versionadas
├── .github/workflows/     # deploy.yml
├── Dockerfile · docker-compose.yml · .dockerignore
├── requirements.txt       # Runtime          requirements-dev.txt → desarrollo/pruebas
└── venv/                  # Entorno virtual local (ignorado por git)
```

**Flujo de una petición:** `route` (valida con DTO) → `service` (lógica) → `repository` (persistencia). Las rutas nunca contienen lógica de negocio y los servicios dependen de *interfaces* de repositorio, no de MongoDB.

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
python app.py                         # o: uvicorn app:create_app --factory --reload --port 8000
```

| URL | Descripción |
| --- | --- |
| http://localhost:8000/docs | **Swagger UI** (documentación interactiva) |
| http://localhost:8000/redoc | ReDoc |
| http://localhost:8000/openapi.json | Esquema OpenAPI |
| http://localhost:8000/health | Liveness |
| http://localhost:8000/health/ready | Readiness (verifica MongoDB) |
| http://localhost:8000/api/v1/greeting | Hola Mundo |

> ⚠ `app.py` es una *factory*: ya no existe el objeto `app`, así que `uvicorn app:app` **no funciona**. Usa `python app.py` o `uvicorn app:create_app --factory`.

## Endpoints

Todos bajo `/api/v1` salvo salud. 🔓 = pública · 🔑 = requiere sesión · 🛡 = requiere el permiso indicado.

**Autenticación** (`/auth`)

| Método | Ruta | Descripción | Respuestas |
| --- | --- | --- | --- |
| POST | `/auth/register` 🔓 | Registrar cuenta (rol por defecto `viewer`) | 201 · 403 · 409 · 422 |
| POST | `/auth/login` 🔓 | Iniciar sesión (token + cookie de refresh) | 200 · 401 · 403 · 429 |
| POST | `/auth/refresh` 🍪 | Renovar/restaurar la sesión con la cookie | 200 · 401 |
| POST | `/auth/logout` 🍪 | Cerrar sesión (idempotente) | 204 |
| POST | `/auth/password-reset-requests` 🔓 | Pedir enlace de recuperación (siempre 202) | 202 |
| POST | `/auth/password-resets` 🔓 | Fijar contraseña nueva con el token del correo | 204 · 400 · 422 |
| POST | `/auth/oauth/google` 🔓 | **Preparado**, aún no disponible | 501 |

**Perfil y usuarios** (`/users`)

| Método | Ruta | Permiso | Descripción |
| --- | --- | --- | --- |
| GET | `/users/me` | 🔑 | Mi perfil + permisos efectivos |
| PATCH | `/users/me` | 🔑 | Editar mi nombre |
| PUT | `/users/me/password` | 🔑 | Cambiar mi contraseña (cierra otras sesiones) |
| GET | `/users` | 🛡 `users:read` | Listado paginado (`q`, `role`, `status`, `page`, `page_size`) |
| POST | `/users` | 🛡 `users:create` | Crear usuario con rol |
| GET | `/users/{id}` | 🛡 `users:read` | Ver usuario |
| PATCH | `/users/{id}` | 🛡 `users:update` | Editar nombre, rol o estado |
| DELETE | `/users/{id}` | 🛡 `users:delete` | Eliminar usuario |

**Roles y permisos**

| Método | Ruta | Permiso | Descripción |
| --- | --- | --- | --- |
| GET | `/permissions` | 🛡 `roles:read` | Catálogo de permisos |
| GET | `/roles` · `/roles/{key}` | 🛡 `roles:read` | Listar / ver roles |
| POST | `/roles` | 🛡 `roles:manage` | Crear rol personalizado |
| PATCH | `/roles/{key}` | 🛡 `roles:manage` | Editar nombre, descripción o permisos |
| DELETE | `/roles/{key}` | 🛡 `roles:manage` | Eliminar (no de sistema ni con usuarios) |

**Bitácora** (`/logs`, permiso `logs:read`): `GET /logs` (búsqueda con filtros y paginación) · `GET /logs/modules`.

**Infraestructura y prueba de humo:** `GET /health` (liveness) · `GET /health/ready` (readiness, 503 si Mongo cae) · `GET /api/v1/greeting`.

## Autenticación y autorización

**Sesión (persistente y segura).**
- `login` devuelve un **access token JWT** (15 min) en el cuerpo — el frontend lo guarda **solo en memoria** — y deja el **refresh token** en la cookie `centynella_refresh`: `HttpOnly` (JavaScript no puede leerla → un XSS no roba la sesión), `SameSite=Lax` (protección CSRF) y `Secure` en producción. Dura 14 días.
- **Restaurar sesión al abrir/recargar la app:** el frontend llama a `POST /auth/refresh`; la cookie viaja sola.
- El refresh token **rota en cada uso**. En base de datos solo se guarda su **hash SHA-256**. Reutilizar un token ya rotado (posible robo) revoca toda la familia; existe una ventana de 10 s para dos pestañas que refrescan a la vez.
- Cambiar/restablecer contraseña o deshabilitar/eliminar un usuario **cierra sus sesiones**.

**Contraseñas.** Argon2id; política: 8+ caracteres con al menos una letra y un número. Tras 5 intentos fallidos la cuenta se bloquea 15 min (429 + `Retry-After`). El login responde igual si el correo no existe (no se pueden enumerar cuentas).

**Recuperación.** `POST /auth/password-reset-requests` siempre responde 202. El enlace (`{FRONTEND_URL}/reset-password?token=…`) es de un solo uso y vence en 60 min. Hoy el correo se **simula en el log** del API (`LogEmailSender`); para producción se añade una implementación SMTP / Amazon SES detrás de la interfaz `EmailSender`.

**Autorización por permisos.** Un *permiso* es `recurso:acción` (`users:read`…), un *rol* es un conjunto de permisos y el código **protege endpoints por permiso, nunca por rol**. Los permisos se leen del rol en cada petición: cambiar un rol surte efecto de inmediato. Roles de sistema (se crean al arrancar): `admin` (todos los permisos, siempre sincronizado), `manager` (`users:read`, `roles:read`) y `viewer` (sin permisos; rol por defecto del registro). Reglas de seguridad: nunca queda el sistema sin un administrador activo, no puedes cambiarte el rol/estado ni eliminarte, y los roles de sistema no se eliminan.

**Administrador inicial.** Si la base no tiene usuarios y defines `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD`, se crea al arrancar.

**Google (preparado).** El contrato (`POST /auth/oauth/google`), el modelo (`users.providers[]`) y `GOOGLE_CLIENT_ID` están listos; falta verificar el `id_token` con `google-auth` en `AuthService.login_with_google`.

## Bitácora (logs por módulo, usuario y sesión)

Todo lo que ocurre queda registrado en una **base de datos aparte** (`MONGODB_LOGS_DB`: `centynella_logs_sandbox` / `centynella_logs_production`, mismo cluster), así el volumen, la retención y los permisos de los logs no afectan a los datos de negocio.

**Cada evento** (`LogEntry`) lleva: fecha, **nivel** (DEBUG · INFO · WARNING · ERROR · CRITICAL), **servicio** (`core`, y los microservicios futuros), **módulo** (`auth`, `users`, `roles`, `database`, `http`, `system`, `security`), un **código de evento** estable (`auth.login.success`), mensaje, **`user_id`**, **`session_id`** (la del refresh token: el mismo id atraviesa login → refresh → logout), **`request_id`** (enlaza TODO lo de una petición con la cabecera `X-Request-ID`), IP y `details`.

**Qué se registra:** arranque y apagado, **conexión a MongoDB** (`database.connected` / `database.unreachable`), índices y datos iniciales; login correcto/fallido/bloqueado, renovación y cierre de sesión, recuperación y cambio de contraseña; altas, cambios y bajas de usuarios y roles (con **actor** y **objetivo**); accesos denegados y tokens rechazados (módulo `security`); un evento `http.request` por petición (método, ruta, estado, duración; 2xx INFO · 4xx WARNING · 5xx ERROR); y los avisos/errores del `logging` de Python (`python.*`).

**Qué NUNCA se registra:** contraseñas, tokens, cookies ni cuerpos de petición (las claves que parecen secreto se reemplazan por `[oculto]`); los correos se enmascaran (`a***@dominio.com`); no se guarda la query string. Sondas (`/health`), documentación y la propia consulta de la bitácora no se registran.

**Cómo funciona:** `EventLogger.log()` es **síncrono y no bloquea**: encola el evento y un trabajador lo guarda por lotes. Si la base de logs se cae, la app sigue funcionando (reintenta y, si no hay remedio, descarta avisando por consola). Usuario, sesión, IP y `request_id` se toman solos del contexto de la petición (`ContextVar`). Un índice **TTL** borra los eventos viejos (`LOG_RETENTION_DAYS`).

**Consulta:** `GET /api/v1/logs` (permiso `logs:read`, solo `admin` por defecto) con filtros `module`, `level` (mínimo), `event`, `service`, `user_id`, `session_id`, `request_id`, `since`, `until`, `q` y paginación; `GET /api/v1/logs/modules` lista los módulos. En el frontend: `/admin/logs`.

Para registrar un evento nuevo en un servicio: `self._events.info("modulo", "modulo.accion", "Mensaje", clave=valor)`.

## Seguridad de entradas y cabeceras

- **Tipos estrictos:** un JSON como `{"email": {"$ne": ""}}` se rechaza (422) antes de tocar la base → sin inyección NoSQL por operadores; el buscador y los filtros usan texto literal (`re.escape`).
- **Correo:** RFC + patrón estricto (debe llevar `@`; sin espacios, comillas ni `< >`), en minúsculas.
- **Contraseña nueva:** 8-128 caracteres con **mayúscula, minúscula, número y símbolo**, sin espacios ni caracteres de control. Se guarda con Argon2id; puede llevar cualquier símbolo porque nunca se muestra.
- **Nombres** (solo letras de cualquier idioma, espacios, apóstrofes, puntos y guiones) y **textos libres** (sin `< >` ni caracteres de control): no se guarda marcado HTML/scripts. La interfaz además escapa al mostrar.
- **Cabeceras** en toda respuesta: `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`, `Cache-Control: no-store` y CSP `default-src 'none'` (Swagger queda exento para poder cargar); HSTS en producción.
- **Tamaño:** cuerpos > 1 MB (`MAX_REQUEST_BODY_BYTES`) se rechazan con 413, también si llegan por trozos.

## Convenciones RESTful

- **Versionado en la URL:** `/api/v1/...`. Un cambio incompatible crea `/api/v2`.
- **Recursos = sustantivos** (`/products`, `/warehouses`); la acción la da el verbo HTTP: `GET` leer, `POST` crear (201 + `Location`), `PUT` reemplazar, `PATCH` modificar parcial, `DELETE` borrar (204).
- **Códigos de estado correctos:** 200, 201, 202, 204, 400, 401, 403, 404, 409, 422, 429, 500, 501, 503.
- **Errores estándar** en `application/problem+json` ([RFC 9457](https://www.rfc-editor.org/rfc/rfc9457)) con un `code` estable para máquinas (`email_taken`, `last_admin`…) y `request_id` para rastrear.
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
| `MONGODB_LOGS_DB` | Base de datos de la bitácora (separada) | `centynella_logs` |
| `LOG_RETENTION_DAYS` · `LOG_MIN_LEVEL` | Días que se conservan los eventos · nivel mínimo que se guarda | `30` · `INFO` |
| `MAX_REQUEST_BODY_BYTES` | Tamaño máximo del cuerpo de una petición | `1048576` |
| `JWT_SECRET_KEY` | **Obligatoria** (≥ 32 caracteres); firma los JWT. Distinta por ambiente | — |
| `FRONTEND_URL` | URL pública del shell (enlace de recuperación) | `http://localhost:5173` |
| `BOOTSTRAP_ADMIN_EMAIL` / `_PASSWORD` | Administrador inicial (solo con la base vacía) | — |
| `ACCESS_TOKEN_TTL_MINUTES` · `REFRESH_TOKEN_TTL_DAYS` | Vida de las sesiones | `15` · `14` |
| `MAX_FAILED_LOGINS` · `LOCKOUT_MINUTES` | Bloqueo por intentos fallidos | `5` · `15` |
| `REGISTRATION_ENABLED` | Registro público de cuentas | `true` |
| `GOOGLE_CLIENT_ID` | Para el login con Google (aún inactivo) | — |
| `CORS_ORIGINS` | Orígenes EXACTOS permitidos (coma) — el shell del MFE. El `*` se ignora (cookies) y en producción falla | `http://localhost:5173` |
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
pytest                       # unitarias: ~280 pruebas, sin Mongo real
pytest --cov                 # con cobertura (mínimo 80 %; hoy ~99 %)

# Integración (requiere MongoDB local: docker compose --profile local up -d mongo)
pytest -m integration        # contrato de repositorios contra Mongo real + ping a Atlas del ambiente activo
ruff check . && ruff format --check .
```

Las unitarias inyectan repositorios **en memoria** (`tests/fakes.py`) y un remitente de correo de prueba; así corren en cualquier lugar y en el CI. `tests/test_repository_contract.py` ejecuta **la misma batería contra la implementación en memoria y contra MongoDB real**, lo que garantiza que el doble se comporta como la base de verdad. **Ningún despliegue corre sin pasar la batería completa.**

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

### 0.4.0 — Bitácora y endurecimiento de entradas
- Bitácora en una base de datos separada (`MONGODB_LOGS_DB`): eventos por módulo, usuario, sesión y petición; cola asíncrona que no bloquea, saneamiento de secretos, TTL, puente con `logging`; consulta en `GET /api/v1/logs` (`logs:read`).
- El access token lleva `sid` (id de sesión) para enlazar cada petición con su sesión.
- Contraseña con mayúscula/minúscula/número/símbolo; correo estricto; nombres y textos sin HTML; rol referenciado con formato de clave.
- Cabeceras de seguridad y límite de tamaño del cuerpo (413).
- El 401 esperado de `/auth/refresh` (visitante sin sesión) se registra como INFO, no como advertencia.
- ~305 pruebas (incluye contrato de la bitácora contra MongoDB real), cobertura ~99 %.

### 0.3.0 — Autenticación, usuarios, roles y permisos
- Registro, login, sesión persistente (access JWT + refresh token rotativo en cookie HttpOnly), logout.
- Recuperación de contraseña por correo (simulado en log) y cambio de contraseña autenticado.
- Perfil propio y administración de usuarios (listado paginado con búsqueda y filtros, CRUD).
- Roles y permisos administrables; protección de endpoints por permiso; reglas contra dejar el sistema sin administrador.
- Bloqueo por intentos fallidos, hash Argon2id, tokens guardados como hash, errores con `code` estable.
- Patrón Repository (interfaces + MongoDB + doble en memoria con pruebas de contrato).
- Administrador inicial por variables de entorno; login con Google preparado (501).
- **Cambio importante:** `app.py` es ahora una *factory* → `uvicorn app:create_app --factory` (o `python app.py`); `JWT_SECRET_KEY` es obligatoria.
- 194 pruebas (154 unitarias + 40 de integración/contrato), cobertura ~99 %.

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
