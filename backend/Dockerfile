ARG PYTHON_IMAGE=python:3.12-slim
FROM ${PYTHON_IMAGE} AS build

# Only the uv bootstrap installer may use a reviewed mirror. `uv sync --locked` must stay on the
# index recorded in uv.lock: overriding it makes uv reject the committed lockfile as stale.
ARG PYPI_INDEX_URL=https://pypi.org/simple

WORKDIR /app
ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1 \
    UV_HTTP_TIMEOUT=120
RUN python -m pip install --no-cache-dir --index-url "${PYPI_INDEX_URL}" uv==0.12.5
COPY backend/pyproject.toml backend/uv.lock /app/backend/
RUN uv sync --project backend --locked --no-dev --no-install-project
COPY backend /app/backend
RUN uv sync --project backend --locked --no-dev --no-editable

FROM ${PYTHON_IMAGE} AS runtime
WORKDIR /app
ENV PATH="/app/backend/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SERVICEOS_ENV=production \
    SERVICEOS_AUTH_MODE=disabled
RUN groupadd --gid 10001 serviceos \
    && useradd --uid 10001 --gid serviceos --create-home serviceos \
    && mkdir -p /data/evidence \
    && chown serviceos:serviceos /data/evidence \
    && chmod 700 /data/evidence
COPY --from=build /app/backend/.venv /app/backend/.venv
COPY backend/alembic.ini /app/backend/alembic.ini
COPY backend/migrations /app/backend/migrations
COPY deploy/preflight.py /app/deploy/preflight.py
USER serviceos
EXPOSE 8000
CMD ["uvicorn", "serviceos_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers", "--no-access-log"]
