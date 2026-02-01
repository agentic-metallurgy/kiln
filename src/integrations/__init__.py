"""Integrations package for optional external service integrations.

This package contains modules for optional external services:
- azure_oauth: Azure Entra ID authentication
- mcp_client: MCP server connectivity testing
- mcp_config: MCP configuration management
- pagerduty: PagerDuty alerting
- slack: Slack notifications
- telemetry: OpenTelemetry instrumentation
"""

# Re-exports from azure_oauth
from src.integrations.azure_oauth import (
    AzureOAuthClient,
    AzureOAuthError,
    AzureTokenExpiredError,
    AzureTokenRequestError,
)

# Re-exports from mcp_client
from src.integrations.mcp_client import (
    MCPTestResult,
    check_all_mcp_servers,
    check_mcp_server,
)

# Re-exports from mcp_config
from src.integrations.mcp_config import (
    MCPConfig,
    MCPConfigError,
    MCPConfigLoadError,
    MCPConfigManager,
    MCPConfigWriteError,
)

# Re-exports from pagerduty
from src.integrations.pagerduty import (
    init_pagerduty,
    resolve_hibernation_alert,
    trigger_hibernation_alert,
)

# Re-exports from slack
from src.integrations.slack import (
    init_slack,
    send_comment_processed_notification,
    send_phase_completion_notification,
    send_startup_ping,
)

# Re-exports from telemetry
from src.integrations.telemetry import (
    LLMMetrics,
    get_git_version,
    get_tracer,
    init_telemetry,
    record_llm_metrics,
)

__all__ = [
    # azure_oauth
    "AzureOAuthClient",
    "AzureOAuthError",
    "AzureTokenExpiredError",
    "AzureTokenRequestError",
    # mcp_client
    "MCPTestResult",
    "check_all_mcp_servers",
    "check_mcp_server",
    # mcp_config
    "MCPConfig",
    "MCPConfigError",
    "MCPConfigLoadError",
    "MCPConfigManager",
    "MCPConfigWriteError",
    # pagerduty
    "init_pagerduty",
    "resolve_hibernation_alert",
    "trigger_hibernation_alert",
    # slack
    "init_slack",
    "send_comment_processed_notification",
    "send_phase_completion_notification",
    "send_startup_ping",
    # telemetry
    "LLMMetrics",
    "get_git_version",
    "get_tracer",
    "init_telemetry",
    "record_llm_metrics",
]
