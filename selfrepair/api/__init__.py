"""FastAPI HTTP surface: health, webhooks, jobs, /v1/rpc."""
from selfrepair.api.main import app, build_app

__all__ = ["app", "build_app"]
