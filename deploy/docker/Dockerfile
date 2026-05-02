# Multi-stage Dockerfile shared by api and worker.
#   docker build -f deploy/docker/Dockerfile -t selfrepair:dev .
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        git \
        curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app

FROM base AS runtime
COPY pyproject.toml README.md ./
COPY selfrepair ./selfrepair
COPY backend ./backend
COPY migrations ./migrations
COPY alembic.ini ./
RUN pip install --upgrade pip && pip install ".[server]"
EXPOSE 8000
CMD ["uvicorn", "selfrepair.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
