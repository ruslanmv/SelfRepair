FROM python:3.11-slim

LABEL maintainer="RepoGuardian"
LABEL description="RepoGuardian - Enterprise Repository Health & Governance Platform"

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user (HF Spaces requirement: uid 1000)
RUN useradd -m -u 1000 guardian
WORKDIR /app

# Install RepoGuardian core
COPY pyproject.toml README.md ./
COPY repoguardian/ repoguardian/
RUN pip install --no-cache-dir -e ".[all]"

# Install web UI dependencies
COPY deploy/huggingface/requirements-web.txt ./
RUN pip install --no-cache-dir -r requirements-web.txt

# Copy web application
COPY deploy/huggingface/webapp/ webapp/
COPY deploy/huggingface/start.sh /app/start.sh
RUN chmod +x /app/start.sh

# HF Spaces expects port 7860
ENV PORT=7860 \
    HOST=0.0.0.0 \
    WORK_DIR=/tmp/repoguardian/work \
    STATE_DIR=/tmp/repoguardian/state \
    STATUS_SITE_DIR=/tmp/repoguardian/status-site \
    DATABASE_URL=sqlite:////tmp/repoguardian/repoguardian.db \
    DRY_RUN=true \
    ADMIN_PASSWORD=guardian2024

# Ensure writable dirs
RUN mkdir -p /tmp/repoguardian/work /tmp/repoguardian/state /tmp/repoguardian/status-site && \
    chown -R guardian:guardian /tmp/repoguardian /app

USER guardian

HEALTHCHECK --interval=30s --timeout=5s \
  CMD curl -f http://localhost:7860/health || exit 1

EXPOSE 7860

CMD ["/app/start.sh"]
