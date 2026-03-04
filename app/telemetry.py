"""
Telemetry bootstrap — OpenTelemetry tracing + metrics for FastAPI.
Configured for Oracle APM (Application Performance Monitoring).

Oracle APM URL scheme
---------------------
  Traces (public key):  <base>/20200101/opentelemetry/public/v1/traces
  Traces (private key): <base>/20200101/opentelemetry/private/v1/traces
  Metrics (private):    <base>/20200101/opentelemetry/v1/metrics

Authorization header:   "Authorization": "dataKey <DATA_KEY>"

Required env-vars
-----------------
  OTEL_APM_ENDPOINT      Base data-upload URL, e.g.
                          https://<ID>.apm-agt.ap-mumbai-1.oci.oraclecloud.com
  OTEL_APM_DATA_KEY      Private data key (used for traces + metrics).

Optional env-vars
-----------------
  OTEL_APM_USE_PRIVATE_KEY  "true" (default) → private key for traces
                             "false"          → public key for traces
  OTEL_SERVICE_NAME          Defaults to "video-transcriber"
  OTEL_SERVICE_VERSION       Defaults to "1.0.0"
  OTEL_METRIC_EXPORT_INTERVAL_MS  Metric flush cadence in ms (default 60000)
  OTEL_EXCLUDED_URLS         Comma-separated URL prefixes to skip tracing

Console fallback
----------------
  When OTEL_APM_ENDPOINT is not set the module falls back to
  ConsoleSpanExporter / ConsoleMetricExporter so local dev still works.

Usage (in main.py)
------------------
    from telemetry import setup_telemetry
    _otel_shutdown = setup_telemetry(app)

    @app.on_event("shutdown")
    def on_shutdown():
        _otel_shutdown()

Metrics emitted
---------------
  HTTP (per request):
    http_requests_total          Counter   — by method, route, status_code
    http_request_duration_ms     Histogram — wall-clock time in ms
    http_requests_in_flight      UpDownCounter — concurrent requests
    http_errors_total            Counter   — 4xx and 5xx separately
    http_request_size_bytes      Histogram — incoming Content-Length
    http_response_size_bytes     Histogram — outgoing Content-Length

  System (every export interval via Observable callbacks):
    system_cpu_usage_percent          Gauge — per-core CPU %
    system_memory_used_bytes          Gauge — RSS bytes used
    system_memory_available_bytes     Gauge — available memory bytes
    system_memory_usage_percent       Gauge — % memory used
    system_disk_used_bytes            Gauge — disk used on /
    system_disk_free_bytes            Gauge — disk free on /
    system_disk_usage_percent         Gauge — % disk used on /
    system_network_bytes_sent_total   Gauge — cumulative network TX bytes
    system_network_bytes_recv_total   Gauge — cumulative network RX bytes

  Process:
    process_cpu_usage_percent         Gauge — this process CPU %
    process_memory_rss_bytes          Gauge — resident set size
    process_memory_vms_bytes          Gauge — virtual memory size
    process_open_file_descriptors     Gauge — open fd count
    process_threads_count             Gauge — thread count
    process_uptime_seconds            Gauge — seconds since process start

Exporter support
----------------
  Two independent OTLP exporters can run simultaneously:
  1. Oracle APM:    OTEL_APM_ENDPOINT + OTEL_APM_DATA_KEY (custom URL scheme)
  2. Generic OTLP:  OTLP_ENDPOINT + OTLP_AUTH_HEADER (standard OTLP/HTTP)
  Console exporter is always active for local debugging.
"""

import logging
import os
import time
import threading
from typing import Callable

import psutil

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.routing import Match

from opentelemetry import trace, metrics
from opentelemetry.metrics import Observation
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    ConsoleMetricExporter,
    PeriodicExportingMetricReader,
)
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_resource() -> Resource:
    return Resource.create(
        {
            SERVICE_NAME: os.getenv("OTEL_SERVICE_NAME", "video-transcriber"),
            SERVICE_VERSION: os.getenv("OTEL_SERVICE_VERSION", "1.0.0"),
            "deployment.environment": os.getenv("ENVIRONMENT", "production"),
        }
    )


def _oracle_apm_auth_header(data_key: str) -> dict[str, str]:
    """Return the Authorization header Oracle APM expects."""
    return {"Authorization": f"dataKey {data_key}"}


def _build_trace_endpoint(base: str, private: bool) -> str:
    tier = "private" if private else "public"
    return f"{base.rstrip('/')}/20200101/opentelemetry/{tier}/v1/traces"


def _build_metrics_endpoint(base: str) -> str:
    return f"{base.rstrip('/')}/20200101/opentelemetry/v1/metrics"


# ---------------------------------------------------------------------------
# HTTP metrics middleware
# ---------------------------------------------------------------------------

class HttpMetricsMiddleware(BaseHTTPMiddleware):
    """
    Records per-request HTTP metrics:

    http_requests_total        Counter    — by method, route, status_code
    http_request_duration_ms   Histogram  — wall-clock time in ms
    http_requests_in_flight    UpDownCounter — concurrent requests
    http_errors_total          Counter    — 4xx / 5xx errors with error_class label
    http_request_size_bytes    Histogram  — Content-Length of incoming request
    http_response_size_bytes   Histogram  — Content-Length of outgoing response
    """

    def __init__(self, app, meter):
        super().__init__(app)
        self._requests_total = meter.create_counter(
            "http_requests_total",
            description="Total HTTP requests by method, route, and status code",
            unit="{request}",
        )
        self._duration_ms = meter.create_histogram(
            "http_request_duration_ms",
            description="HTTP request handling duration in milliseconds",
            unit="ms",
        )
        self._in_flight = meter.create_up_down_counter(
            "http_requests_in_flight",
            description="Number of HTTP requests currently being processed",
            unit="{request}",
        )
        self._errors_total = meter.create_counter(
            "http_errors_total",
            description="Total HTTP error responses (4xx and 5xx) by route and error class",
            unit="{request}",
        )
        self._req_size = meter.create_histogram(
            "http_request_size_bytes",
            description="Incoming HTTP request body size in bytes (Content-Length)",
            unit="By",
        )
        self._resp_size = meter.create_histogram(
            "http_response_size_bytes",
            description="Outgoing HTTP response body size in bytes (Content-Length)",
            unit="By",
        )

    @staticmethod
    def _get_route(request: Request) -> str:
        for route in request.app.routes:
            match, _ = route.matches(request.scope)
            if match == Match.FULL:
                return getattr(route, "path", request.url.path)
        return request.url.path

    async def dispatch(self, request: Request, call_next):
        route = self._get_route(request)
        labels_base = {"http.method": request.method, "http.route": route}

        # Incoming size
        req_content_length = int(request.headers.get("content-length", 0) or 0)

        self._in_flight.add(1, labels_base)
        t0 = time.perf_counter()
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            status_code = 500
            raise
        finally:
            duration_ms = (time.perf_counter() - t0) * 1000
            self._in_flight.add(-1, labels_base)

            labels = {**labels_base, "http.status_code": str(status_code)}
            self._requests_total.add(1, labels)
            self._duration_ms.record(duration_ms, labels)
            self._req_size.record(req_content_length, labels_base)

            if status_code >= 400:
                error_class = "4xx" if status_code < 500 else "5xx"
                self._errors_total.add(
                    1, {**labels, "error.class": error_class}
                )

        # Outgoing size (may not be set for streaming responses)
        resp_content_length = int(response.headers.get("content-length", 0) or 0)
        self._resp_size.record(resp_content_length, labels)

        return response


# ---------------------------------------------------------------------------
# System & process metrics (Observable Gauges via psutil)
# ---------------------------------------------------------------------------

_proc = psutil.Process()
_boot_time = time.time()


def _register_system_metrics(meter) -> None:
    """
    Register Observable Gauges that are polled on every export cycle.
    These cover CPU, memory, disk, network, and process internals.
    """

    # ── CPU ───────────────────────────────────────────────────────────────
    def _cpu_usage(options):
        for i, pct in enumerate(psutil.cpu_percent(percpu=True)):
            yield Observation(pct, {"cpu.core": str(i)})

    meter.create_observable_gauge(
        "system_cpu_usage_percent",
        callbacks=[_cpu_usage],
        description="CPU usage percentage per core",
        unit="%",
    )

    # ── Memory ────────────────────────────────────────────────────────────
    def _mem_used(options):
        yield Observation(psutil.virtual_memory().used)

    def _mem_available(options):
        yield Observation(psutil.virtual_memory().available)

    def _mem_pct(options):
        yield Observation(psutil.virtual_memory().percent)

    meter.create_observable_gauge(
        "system_memory_used_bytes",
        callbacks=[_mem_used],
        description="System memory currently in use (bytes)",
        unit="By",
    )
    meter.create_observable_gauge(
        "system_memory_available_bytes",
        callbacks=[_mem_available],
        description="System memory available (bytes)",
        unit="By",
    )
    meter.create_observable_gauge(
        "system_memory_usage_percent",
        callbacks=[_mem_pct],
        description="System memory usage percentage",
        unit="%",
    )

    # ── Disk (/mnt/extra and / separately if different) ───────────────────
    _disk_paths = list({"/", os.getenv("UPLOAD_DIR", "/mnt/extra").split("/")[0] + "/" or "/"})

    def _disk_used(options):
        for path in ["/", "/mnt/extra"]:
            try:
                du = psutil.disk_usage(path)
                yield Observation(du.used, {"disk.mount": path})
            except Exception:
                pass

    def _disk_free(options):
        for path in ["/", "/mnt/extra"]:
            try:
                du = psutil.disk_usage(path)
                yield Observation(du.free, {"disk.mount": path})
            except Exception:
                pass

    def _disk_pct(options):
        for path in ["/", "/mnt/extra"]:
            try:
                du = psutil.disk_usage(path)
                yield Observation(du.percent, {"disk.mount": path})
            except Exception:
                pass

    meter.create_observable_gauge(
        "system_disk_used_bytes",
        callbacks=[_disk_used],
        description="Disk space used in bytes",
        unit="By",
    )
    meter.create_observable_gauge(
        "system_disk_free_bytes",
        callbacks=[_disk_free],
        description="Disk space free in bytes",
        unit="By",
    )
    meter.create_observable_gauge(
        "system_disk_usage_percent",
        callbacks=[_disk_pct],
        description="Disk usage percentage",
        unit="%",
    )

    # ── Network ───────────────────────────────────────────────────────────
    def _net_sent(options):
        yield Observation(psutil.net_io_counters().bytes_sent)

    def _net_recv(options):
        yield Observation(psutil.net_io_counters().bytes_recv)

    meter.create_observable_gauge(
        "system_network_bytes_sent_total",
        callbacks=[_net_sent],
        description="Cumulative bytes sent over all network interfaces",
        unit="By",
    )
    meter.create_observable_gauge(
        "system_network_bytes_recv_total",
        callbacks=[_net_recv],
        description="Cumulative bytes received over all network interfaces",
        unit="By",
    )

    # ── Process ───────────────────────────────────────────────────────────
    def _proc_cpu(options):
        try:
            yield Observation(_proc.cpu_percent())
        except Exception:
            pass

    def _proc_mem_rss(options):
        try:
            yield Observation(_proc.memory_info().rss)
        except Exception:
            pass

    def _proc_mem_vms(options):
        try:
            yield Observation(_proc.memory_info().vms)
        except Exception:
            pass

    def _proc_fds(options):
        try:
            yield Observation(_proc.num_fds())
        except Exception:
            pass

    def _proc_threads(options):
        try:
            yield Observation(_proc.num_threads())
        except Exception:
            pass

    def _proc_uptime(options):
        yield Observation(time.time() - _boot_time)

    meter.create_observable_gauge(
        "process_cpu_usage_percent",
        callbacks=[_proc_cpu],
        description="CPU usage of this process",
        unit="%",
    )
    meter.create_observable_gauge(
        "process_memory_rss_bytes",
        callbacks=[_proc_mem_rss],
        description="Resident set size of this process",
        unit="By",
    )
    meter.create_observable_gauge(
        "process_memory_vms_bytes",
        callbacks=[_proc_mem_vms],
        description="Virtual memory size of this process",
        unit="By",
    )
    meter.create_observable_gauge(
        "process_open_file_descriptors",
        callbacks=[_proc_fds],
        description="Number of open file descriptors by this process",
        unit="{fd}",
    )
    meter.create_observable_gauge(
        "process_threads_count",
        callbacks=[_proc_threads],
        description="Number of threads used by this process",
        unit="{thread}",
    )
    meter.create_observable_gauge(
        "process_uptime_seconds",
        callbacks=[_proc_uptime],
        description="Seconds since the process started",
        unit="s",
    )

    logger.info(
        "System & process metrics registered "
        "(CPU, memory, disk, network, process)"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def setup_telemetry(app: FastAPI) -> Callable[[], None]:
    """
    Wire OpenTelemetry tracing + metrics into *app*.

    Supports two OTLP exporters simultaneously:
    1. Oracle APM  — OTEL_APM_ENDPOINT + OTEL_APM_DATA_KEY
    2. Generic OTLP — OTLP_ENDPOINT + optional OTLP_AUTH_HEADER

    Returns a ``shutdown()`` callable — call it from your ASGI lifespan or
    ``on_event("shutdown")`` handler so providers flush cleanly on SIGTERM.
    """
    resource = _build_resource()

    # ── Read config ───────────────────────────────────────────────────────
    # Oracle APM
    apm_base: str = os.getenv("OTEL_APM_ENDPOINT", "").strip()
    apm_data_key: str = os.getenv("OTEL_APM_DATA_KEY", "").strip()
    use_private_for_traces: bool = (
        os.getenv("OTEL_APM_USE_PRIVATE_KEY", "true").lower() != "false"
    )
    oracle_apm_enabled = bool(apm_base and apm_data_key)

    # Generic OTLP
    otlp_endpoint: str = os.getenv("OTLP_ENDPOINT", "").strip()
    otlp_auth_header: str = os.getenv("OTLP_AUTH_HEADER", "").strip()
    generic_otlp_enabled = bool(otlp_endpoint)

    # Shared
    export_interval_ms: int = int(
        os.getenv("OTEL_METRIC_EXPORT_INTERVAL_MS", "60000")
    )
    excluded_urls: str = os.getenv(
        "OTEL_EXCLUDED_URLS", "/health,/metrics,/openapi.json"
    )

    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
        OTLPSpanExporter,
    )
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
        OTLPMetricExporter,
    )

    # ══════════════════════════════════════════════════════════════════════
    #  TRACER PROVIDER
    # ══════════════════════════════════════════════════════════════════════
    tracer_provider = TracerProvider(resource=resource)

    # Console exporter — always on (visible in journalctl / stdout)
    tracer_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    # --- Oracle APM trace exporter ---
    if oracle_apm_enabled:
        try:
            trace_url = _build_trace_endpoint(apm_base, private=use_private_for_traces)
            tracer_provider.add_span_processor(
                BatchSpanProcessor(
                    OTLPSpanExporter(
                        endpoint=trace_url,
                        headers=_oracle_apm_auth_header(apm_data_key),
                    )
                )
            )
            key_type = "private" if use_private_for_traces else "public"
            logger.info("Oracle APM trace exporter enabled (%s key) → %s", key_type, trace_url)
        except Exception as exc:
            logger.warning("Failed to configure Oracle APM trace exporter: %s", exc)
    else:
        logger.info(
            "Oracle APM trace exporter disabled "
            "(set OTEL_APM_ENDPOINT + OTEL_APM_DATA_KEY to enable)"
        )

    # --- Generic OTLP trace exporter ---
    if generic_otlp_enabled:
        try:
            generic_trace_url = f"{otlp_endpoint.rstrip('/')}/v1/traces"
            generic_headers: dict[str, str] = {}
            if otlp_auth_header:
                generic_headers["Authorization"] = otlp_auth_header
            tracer_provider.add_span_processor(
                BatchSpanProcessor(
                    OTLPSpanExporter(
                        endpoint=generic_trace_url,
                        headers=generic_headers,
                    )
                )
            )
            logger.info("Generic OTLP trace exporter enabled → %s", generic_trace_url)
        except Exception as exc:
            logger.warning("Failed to configure generic OTLP trace exporter: %s", exc)
    else:
        logger.info(
            "Generic OTLP trace exporter disabled "
            "(set OTLP_ENDPOINT to enable)"
        )

    trace.set_tracer_provider(tracer_provider)

    # ══════════════════════════════════════════════════════════════════════
    #  METER PROVIDER
    # ══════════════════════════════════════════════════════════════════════
    metric_readers = [
        PeriodicExportingMetricReader(
            ConsoleMetricExporter(),
            export_interval_millis=export_interval_ms,
        )
    ]

    # --- Oracle APM metric exporter ---
    if oracle_apm_enabled:
        try:
            metrics_url = _build_metrics_endpoint(apm_base)
            metric_readers.append(
                PeriodicExportingMetricReader(
                    OTLPMetricExporter(
                        endpoint=metrics_url,
                        headers=_oracle_apm_auth_header(apm_data_key),
                    ),
                    export_interval_millis=export_interval_ms,
                )
            )
            logger.info("Oracle APM metric exporter enabled (private key) → %s", metrics_url)
        except Exception as exc:
            logger.warning("Failed to configure Oracle APM metric exporter: %s", exc)

    # --- Generic OTLP metric exporter ---
    if generic_otlp_enabled:
        try:
            generic_metrics_url = f"{otlp_endpoint.rstrip('/')}/v1/metrics"
            generic_headers_m: dict[str, str] = {}
            if otlp_auth_header:
                generic_headers_m["Authorization"] = otlp_auth_header
            metric_readers.append(
                PeriodicExportingMetricReader(
                    OTLPMetricExporter(
                        endpoint=generic_metrics_url,
                        headers=generic_headers_m,
                    ),
                    export_interval_millis=export_interval_ms,
                )
            )
            logger.info("Generic OTLP metric exporter enabled → %s", generic_metrics_url)
        except Exception as exc:
            logger.warning("Failed to configure generic OTLP metric exporter: %s", exc)

    meter_provider = MeterProvider(resource=resource, metric_readers=metric_readers)
    metrics.set_meter_provider(meter_provider)

    # ── Custom HTTP metrics middleware ────────────────────────────────────
    _http_meter = meter_provider.get_meter("video-transcriber.http", version="1.0.0")
    app.add_middleware(HttpMetricsMiddleware, meter=_http_meter)
    logger.info("HttpMetricsMiddleware active")

    # ── System & process metrics ──────────────────────────────────────────
    _sys_meter = meter_provider.get_meter("video-transcriber.system", version="1.0.0")
    _register_system_metrics(_sys_meter)

    # ── FastAPI auto-instrumentation ──────────────────────────────────────
    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
        excluded_urls=excluded_urls,
    )
    logger.info("FastAPI OpenTelemetry instrumentation active")

    # ── Logging integration ───────────────────────────────────────────────
    LoggingInstrumentor().instrument(set_logging_format=False)
    logger.info("OTel logging instrumentation active (trace/span IDs in log records)")

    # ── Shutdown helper ───────────────────────────────────────────────────
    def shutdown() -> None:
        logger.info("Shutting down OpenTelemetry providers…")
        tracer_provider.shutdown()
        meter_provider.shutdown()

    return shutdown
