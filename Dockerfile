# SelfRepair backend image.
#
# Default command runs the real product API (`selfrepair.api.main:app`).
# The same image is reused by the worker and the migration service in
# docker-compose.yml — switch the command at run time.
FROM python:3.11-slim AS builder

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    git gcc && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md alembic.ini ./
COPY selfrepair/ selfrepair/
COPY backend/ backend/
COPY migrations/ migrations/
RUN pip install --no-cache-dir -e ".[all]" \
        fastapi \
        uvicorn[standard] \
        arq \
        sqlalchemy[asyncio] \
        asyncpg \
        psycopg[binary] \
        alembic \
        redis \
        pydantic \
        pydantic-settings

FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 selfrepair

WORKDIR /app
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin/ /usr/local/bin/
COPY --from=builder /app /app

USER selfrepair

HEALTHCHECK --interval=30s --timeout=5s --retries=5 \
  CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1

EXPOSE 8000

# Default: run the real product API. docker-compose overrides the command
# for the worker (arq) and migrate (alembic upgrade head) services.
CMD ["uvicorn", "selfrepair.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
