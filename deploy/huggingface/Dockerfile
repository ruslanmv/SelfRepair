# =============================================================================
# SelfRepair — Hugging Face Docker Space (self-contained admin webapp)
# =============================================================================
# Build context = this directory (deploy/huggingface), which is pushed as the
# Space repository root. The app is a single FastAPI + SQLite + Jinja webapp:
# login, plus a Connections page to wire OllaBridge / GitPilot / MatrixLab.
#
# HF Spaces constraints: listen on 7860, run as uid 1000, only /tmp writable.
# Golden rule: this Space never receives HF_TOKEN. Only OllaBridge holds it.
# =============================================================================

FROM python:3.11-slim

LABEL maintainer="SelfRepair"
LABEL description="SelfRepair — repository maintenance console (HF Space)"

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Non-root user (HF Spaces requirement: uid 1000)
RUN useradd -m -u 1000 appuser
WORKDIR /app

# Python deps (cache layer)
COPY requirements-web.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements-web.txt

# Application code
COPY webapp/ webapp/
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

ENV PORT=7860 \
    HOST=0.0.0.0 \
    SELFREPAIR_DB_DIR=/tmp/selfrepair \
    ADMIN_PASSWORD=selfrepair2024

# Writable, ephemeral state
RUN mkdir -p /tmp/selfrepair && chown -R appuser:appuser /tmp/selfrepair /app

USER appuser

HEALTHCHECK --interval=30s --timeout=5s \
  CMD curl -f http://localhost:7860/health || exit 1

EXPOSE 7860

CMD ["/app/start.sh"]
