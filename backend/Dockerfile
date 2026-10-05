FROM ghcr.io/astral-sh/uv:0.12.21 AS uv
FROM python:3.13-slim

COPY --from=uv /uv /uvx /usr/local/bin/
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH"
COPY pyproject.toml uv.lock ./
RUN --mount=type=secret,id=build_ca \
    set -eu; \
    if [ -s /run/secrets/build_ca ]; then \
        cat /etc/ssl/certs/ca-certificates.crt /run/secrets/build_ca > /tmp/vigil-build-ca.pem; \
        export SSL_CERT_FILE=/tmp/vigil-build-ca.pem; \
    fi; \
    trap 'rm -f /tmp/vigil-build-ca.pem' EXIT; \
    uv sync --frozen --no-dev --no-install-project
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
