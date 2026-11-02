# syntax=docker/dockerfile:1

# ─────────────────────────────────────────────────────────────
# CENTYNELLA-CORE · imagen de la API (FastAPI)
#
#   docker build -t centynella-core .
#   docker run --rm -p 8000:8000 --env-file private/.env.sandbox centynella-core
#
# La imagen NO contiene secretos: private/ está en .dockerignore.
# La configuración se inyecta en runtime (--env-file, ECS task definition, Secrets Manager).
# ─────────────────────────────────────────────────────────────

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /code

# Capa de dependencias primero: se cachea mientras no cambie requirements.txt
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app.py .
COPY src ./src

# Ejecutar como usuario sin privilegios. `media/` (fotos de producto, ver `ProductImageStorage`)
# se crea y se le da dueño ANTES de bajar privilegios: si no, el usuario sin privilegios no
# puede crearla en tiempo de ejecución. MVP: disco del contenedor, no persiste entre despliegues
# de ECS — mover a S3 detrás de la misma interfaz cuando haga falta (ver `image_storage.py`).
RUN adduser --system --no-create-home --group centynella \
    && mkdir -p /code/media \
    && chown -R centynella:centynella /code/media
USER centynella

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request, sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"

CMD ["uvicorn", "app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
