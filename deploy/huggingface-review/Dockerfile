# SelfRepair Review — single-process review bot for a Hugging Face Docker Space.
# Build context: the repository root (see deploy/huggingface-review/README.md).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PORT=7860
RUN useradd -m -u 1000 user
WORKDIR /app

COPY --chown=user pyproject.toml README.md LICENSE ./
COPY --chown=user selfrepair ./selfrepair
RUN pip install ".[server]"

USER user
EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:7860/healthz')"
CMD ["sh", "-c", "uvicorn selfrepair.reviewer.space_app:app --host 0.0.0.0 --port ${PORT:-7860} --workers 1 --proxy-headers"]
