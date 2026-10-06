FROM node:24-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=secret,id=build_ca \
    if [ -s /run/secrets/build_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/build_ca; fi; \
    npm ci --no-audit --no-fund
COPY frontend/src ./src
COPY frontend/public ./public
COPY frontend/index.html frontend/tsconfig.json frontend/vite.config.ts ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:0.12.21 AS uv
FROM python:3.13-slim AS backend
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=secret,id=build_ca \
    set -eu; \
    if [ -s /run/secrets/build_ca ]; then \
        cat /etc/ssl/certs/ca-certificates.crt /run/secrets/build_ca > /tmp/vigil-build-ca.pem; \
        export SSL_CERT_FILE=/tmp/vigil-build-ca.pem; \
    fi; \
    trap 'rm -f /tmp/vigil-build-ca.pem' EXIT; \
    uv sync --frozen --no-dev --no-install-project
COPY backend/app ./app
COPY backend/migrations ./migrations
COPY backend/alembic.ini ./

FROM backend AS batch
USER root
RUN apt-get update && apt-get install -y --no-install-recommends iptables iproute2 util-linux \
    && rm -rf /var/lib/apt/lists/*
COPY infra/worker/egress.py /opt/vigil/egress.py
ENV VIGIL_WORKER_NAMESPACE=dedicated VIGIL_WORKER_CONTROL_MODE=database-only
ENTRYPOINT ["python", "/opt/vigil/egress.py"]
CMD ["python", "-m", "app.monitoring.batch"]

FROM backend AS web
COPY --from=frontend /frontend/dist /app/static
COPY scripts/free_cloud_start.py /app/free_cloud_start.py
COPY scripts/free_cloud_checks.py /app/free_cloud_checks.py
ENV VIGIL_FRONTEND_DIST=/app/static
USER 10001:10001
EXPOSE 8000
CMD ["python", "/app/free_cloud_start.py"]
