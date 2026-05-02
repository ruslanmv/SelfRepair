"""OpenTelemetry tracing setup.

Configures a global tracer provider. If `OTEL_EXPORTER_OTLP_ENDPOINT` is set
and the OTLP exporter package is installed, spans ship to that collector.
Otherwise the SDK is configured but spans go nowhere — useful for tests.
"""
from __future__ import annotations

import logging
import os

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger(__name__)

_configured = False


def configure_tracing(*, service: str = "selfrepair") -> None:
    global _configured
    if _configured:
        return

    resource = Resource.create(
        {
            "service.name": service,
            "service.version": os.getenv("SELFREPAIR_VERSION", "dev"),
            "deployment.environment": os.getenv("SELFREPAIR_ENV", "dev"),
        }
    )
    provider = TracerProvider(resource=resource)

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )

            provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint))
            )
            logger.info("OTel tracing enabled, endpoint=%s", endpoint)
        except ImportError:
            logger.warning(
                "opentelemetry-exporter-otlp-proto-grpc not installed; "
                "tracing will not be exported"
            )
    else:
        logger.info(
            "OTel tracing not configured (set OTEL_EXPORTER_OTLP_ENDPOINT)"
        )

    trace.set_tracer_provider(provider)
    _configured = True


def get_tracer(name: str) -> trace.Tracer:
    return trace.get_tracer(name)


def _reset_for_tests() -> None:
    global _configured
    _configured = False
