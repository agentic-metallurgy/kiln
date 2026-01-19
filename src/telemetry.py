"""OpenTelemetry instrumentation for kiln."""

from dataclasses import dataclass, field
from typing import Any

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from src.logger import get_logger

logger = get_logger(__name__)


def get_git_version() -> str:
    """Get the current git version using git describe.

    Returns:
        Version string (e.g., 'v1.2.3', 'v1.2.3-5-g1234abc', or '1234abc')
        Returns 'unknown' if git is not available or not in a repo.
    """
    import subprocess

    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--always"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return "unknown"


_initialized = False
_tracer: trace.Tracer | None = None
_meter: metrics.Meter | None = None
_token_counter: metrics.Counter | None = None
_cost_counter: metrics.Counter | None = None
_duration_histogram: metrics.Histogram | None = None


@dataclass
class LLMMetrics:
    """Metrics from a Claude CLI execution."""

    duration_ms: int = 0
    duration_api_ms: int = 0
    total_cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    num_turns: int = 0
    session_id: str = ""
    model_usage: dict[str, dict[str, Any]] = field(default_factory=dict)


def init_telemetry(
    endpoint: str,
    service_name: str,
    service_version: str | None = None,
) -> None:
    """Initialize OpenTelemetry tracing and metrics.

    Args:
        endpoint: OTLP endpoint URL (e.g., http://192.168.0.120:4318)
        service_name: Service name for telemetry (e.g., "kiln")
        service_version: Optional service version (e.g., "v1.2.3")
    """
    global _initialized, _tracer, _meter
    global _token_counter, _cost_counter, _duration_histogram

    if _initialized or not endpoint:
        return

    resource_attrs = {"service.name": service_name}
    if service_version:
        resource_attrs["service.version"] = service_version
    resource = Resource.create(resource_attrs)

    # Setup tracing
    trace_exporter = OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")
    trace_provider = TracerProvider(resource=resource)
    trace_provider.add_span_processor(BatchSpanProcessor(trace_exporter))
    trace.set_tracer_provider(trace_provider)
    _tracer = trace.get_tracer(__name__)

    # Setup metrics
    metric_exporter = OTLPMetricExporter(endpoint=f"{endpoint}/v1/metrics")
    metric_reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=10000)
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)
    _meter = metrics.get_meter(__name__)

    # Create instruments
    _token_counter = _meter.create_counter(
        "llm.tokens",
        unit="tokens",
        description="Number of tokens processed by LLM",
    )
    _cost_counter = _meter.create_counter(
        "llm.cost",
        unit="usd",
        description="Cost of LLM requests in USD",
    )
    _duration_histogram = _meter.create_histogram(
        "llm.duration",
        unit="ms",
        description="Duration of LLM requests in milliseconds",
    )

    _initialized = True
    version_info = f", version={service_version}" if service_version else ""
    logger.info(
        f"OpenTelemetry initialized: endpoint={endpoint}, service={service_name}{version_info}"
    )


def get_tracer() -> trace.Tracer:
    """Get the global tracer, or a no-op tracer if not initialized."""
    return _tracer or trace.get_tracer(__name__)


def record_llm_metrics(
    metrics_data: LLMMetrics,
    repo: str,
    issue_number: int,
    workflow: str,
    model: str | None = None,
    version: str | None = None,
) -> None:
    """Record LLM metrics to OTel.

    Args:
        metrics_data: LLMMetrics from Claude CLI execution
        repo: Repository in 'owner/repo' format
        issue_number: Issue number
        workflow: Workflow name (e.g., "Research", "Plan")
        model: Primary model used (optional)
        version: Service version from daemon startup (optional)
    """
    if not _initialized:
        return

    attributes: dict[str, Any] = {
        "repo": repo,
        "issue.number": issue_number,
        "workflow": workflow,
    }
    if model:
        attributes["model"] = model
    if version:
        attributes["service_version"] = version

    if _token_counter:
        _token_counter.add(metrics_data.input_tokens, {**attributes, "token_type": "input"})
        _token_counter.add(metrics_data.output_tokens, {**attributes, "token_type": "output"})

    if _cost_counter and metrics_data.total_cost_usd > 0:
        _cost_counter.add(metrics_data.total_cost_usd, attributes)

    if _duration_histogram and metrics_data.duration_ms > 0:
        _duration_histogram.record(metrics_data.duration_ms, attributes)
