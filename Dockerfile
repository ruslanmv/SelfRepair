FROM python:3.11-slim AS builder

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    git gcc && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY selfrepair/ selfrepair/
COPY backend/ backend/
RUN pip install --no-cache-dir -e ".[all]" fastapi uvicorn

FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    git && \
    rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 guardian

WORKDIR /app
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin/selfrepair-repo /usr/local/bin/selfrepair-repo
COPY --from=builder /app /app

USER guardian

HEALTHCHECK --interval=60s --timeout=5s \
  CMD python -c "import selfrepair; print('ok')" || exit 1

ENTRYPOINT ["uvicorn"]
CMD ["backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
