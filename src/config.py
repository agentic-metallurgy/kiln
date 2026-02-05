"""Configuration module for kiln.

This module provides configuration management for the application,
loading settings from .kiln/config file (KEY=value format) with
fallback to environment variables for backward compatibility.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Default paths relative to .kiln directory
KILN_DIR = ".kiln"
CONFIG_FILE = "config"


@dataclass
class Config:
    """Application configuration.

    Attributes:
        github_token: GitHub personal access token for github.com
        github_enterprise_host: GitHub Enterprise Server hostname (e.g., github.mycompany.com)
        github_enterprise_token: GitHub Enterprise Server personal access token
        project_urls: List of URLs of GitHub project boards to monitor (required)
        poll_interval: Time in seconds between polling the project board
        database_path: Path to the SQLite database file
        workspace_dir: Directory for workspace files
        watched_statuses: List of project statuses to monitor for changes
        max_concurrent_workflows: Maximum number of workflows to run in parallel
    """

    github_token: str | None = None
    github_enterprise_host: str | None = None
    github_enterprise_token: str | None = None
    github_enterprise_version: str | None = None  # GHES version (e.g., "3.14")
    project_urls: list[str] = field(default_factory=list)  # Required, no default
    poll_interval: int = 30
    database_path: str = ".kiln/kiln.db"
    workspace_dir: str = "workspaces"
    watched_statuses: list[str] = field(default_factory=lambda: ["Research", "Plan", "Implement"])
    username_self: str = ""  # Required, no default
    team_usernames: list[str] = field(default_factory=list)  # Optional team members
    max_concurrent_workflows: int = 5
    log_file: str = ".kiln/logs/kiln.log"
    log_size: int = 10 * 1024 * 1024  # 10MB default
    log_backups: int = 5  # Keep 5 backup files by default
    stage_models: dict[str, str] = field(
        default_factory=lambda: {
            "Prepare": "haiku",
            "Research": "opus",
            "Plan": "opus",
            "Implement": "opus",
            "process_comments": "sonnet",
        }
    )
    otel_endpoint: str = ""
    otel_service_name: str = "kiln"
    claude_code_enable_telemetry: bool = False
    safety_allow_appended_tasks: int = 0  # 0 = infinite (no limit)
    ghes_logs_mask: bool = True  # Mask GHES hostname and org in logs
    pagerduty_routing_key: str | None = None  # PagerDuty Events API v2 routing key
    slack_bot_token: str | None = None  # Slack Bot OAuth token (xoxb-...)
    slack_user_id: str | None = None  # Slack user ID to DM (U...)
    slack_dm_on_comment: bool = True  # Send DM when comment is processed
    # Azure OAuth 2.0 ROPC configuration for MCP authentication
    azure_tenant_id: str | None = None
    azure_client_id: str | None = None
    azure_username: str | None = None
    azure_password: str | None = None
    azure_scope: str | None = None  # Defaults to "https://graph.microsoft.com/.default" if not specified


def determine_workspace_dir() -> str:
    """Determine which workspace directory to use.

    Returns "workspaces" if it exists with content (for backward compatibility),
    otherwise returns "worktrees" (new default).
    """
    workspaces_dir = Path.cwd() / "workspaces"
    if workspaces_dir.exists() and any(workspaces_dir.iterdir()):
        contents = [p for p in workspaces_dir.iterdir() if p.name != ".gitkeep"]
        if contents:
            return "workspaces"
    return "worktrees"


def _validate_project_urls_host(
    project_urls: list[str],
    github_token: str | None,
    github_enterprise_host: str | None,
    github_enterprise_token: str | None,
) -> None:
    """Validate PROJECT_URLS hostnames match the configured GitHub host.

    Args:
        project_urls: List of project URLs to validate
        github_token: GitHub.com personal access token (if configured)
        github_enterprise_host: GHES hostname (if configured)
        github_enterprise_token: GHES personal access token (if configured)

    Raises:
        ValueError: If any PROJECT_URL hostname doesn't match the configured host
    """
    # Determine the expected host based on configuration
    if github_enterprise_host and github_enterprise_token:
        expected_host = github_enterprise_host
    else:
        # Default to github.com (either explicit token or gh auth login)
        expected_host = "github.com"

    for url in project_urls:
        parsed = urlparse(url)
        url_host = parsed.netloc

        if url_host and url_host != expected_host:
            raise ValueError(
                f"PROJECT_URLS contains '{url_host}' but configured for '{expected_host}'. "
                f"All project URLs must use the same GitHub host as your authentication config."
            )


def parse_config_file(config_path: Path) -> dict[str, str]:
    """Parse a KEY=value config file.

    Args:
        config_path: Path to the config file

    Returns:
        Dictionary of key-value pairs
    """
    config = {}
    with open(config_path) as f:
        for line in f:
            line = line.strip()
            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue
            # Parse KEY=value
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                # Remove surrounding quotes if present
                if (value.startswith('"') and value.endswith('"')) or (
                    value.startswith("'") and value.endswith("'")
                ):
                    value = value[1:-1]
                config[key] = value
    return config


def load_config_from_file(config_path: Path) -> Config:
    """Load configuration from a KEY=value config file.

    Args:
        config_path: Path to the config file

    Returns:
        Config: A Config instance populated from the config file

    Raises:
        ValueError: If required fields are missing or invalid
        FileNotFoundError: If the config file doesn't exist
    """
    data = parse_config_file(config_path)

    # Collect all missing required vars
    missing_vars: list[str] = []

    # Parse GitHub token
    github_token = data.get("GITHUB_TOKEN")
    if not github_token:
        github_token = None

    # Parse GitHub Enterprise Server config
    github_enterprise_host = data.get("GITHUB_ENTERPRISE_HOST")
    if not github_enterprise_host:
        github_enterprise_host = None

    github_enterprise_token = data.get("GITHUB_ENTERPRISE_TOKEN")
    if not github_enterprise_token:
        github_enterprise_token = None

    # Validate mutual exclusivity: cannot have both github.com and GHES tokens
    if github_token and github_enterprise_token:
        raise ValueError(
            "Cannot configure both GITHUB_TOKEN and GITHUB_ENTERPRISE_TOKEN. "
            "Kiln operates against either github.com OR a GitHub Enterprise Server, not both."
        )

    # Parse GHES version (e.g., "3.14")
    github_enterprise_version = data.get("GITHUB_ENTERPRISE_VERSION")
    if not github_enterprise_version:
        github_enterprise_version = None

    # Validate GitHub authentication - need either GITHUB_TOKEN or full GHES config
    if not github_token:
        # No github.com token - check GHES configuration
        has_any_ghes = github_enterprise_host or github_enterprise_token or github_enterprise_version
        if has_any_ghes:
            # Attempting GHES - need all three vars
            if not github_enterprise_host:
                missing_vars.append("GITHUB_ENTERPRISE_HOST")
            if not github_enterprise_token:
                missing_vars.append("GITHUB_ENTERPRISE_TOKEN")
            if not github_enterprise_version:
                missing_vars.append("GITHUB_ENTERPRISE_VERSION")
        else:
            # No auth configured at all
            missing_vars.append("GITHUB_TOKEN")

    # Set tokens in environment so Claude subprocesses can use gh CLI
    if github_token:
        os.environ["GITHUB_TOKEN"] = github_token
    if github_enterprise_token:
        os.environ["GITHUB_TOKEN"] = github_enterprise_token
        # gh CLI uses GH_ENTERPRISE_TOKEN for GHES authentication
        os.environ["GH_ENTERPRISE_TOKEN"] = github_enterprise_token

    # Parse required fields - collect all missing vars before raising
    project_urls_str = data.get("PROJECT_URLS", "")
    if not project_urls_str:
        missing_vars.append("PROJECT_URLS")
    project_urls = [url.strip() for url in project_urls_str.split(",") if url.strip()]
    if project_urls_str and not project_urls:
        missing_vars.append("PROJECT_URLS")  # Present but empty after parsing

    username_self = data.get("USERNAME_SELF", "").strip()
    if not username_self:
        missing_vars.append("USERNAME_SELF")

    # Raise error listing all missing required vars
    if missing_vars:
        raise ValueError(
            f"Missing required configuration in .kiln/config: {', '.join(missing_vars)}"
        )

    # Validate PROJECT_URLS hostnames match the configured GitHub host
    _validate_project_urls_host(
        project_urls, github_token, github_enterprise_host, github_enterprise_token
    )

    # Parse team usernames as comma-separated list (optional)
    team_usernames_str = data.get("USERNAMES_TEAM", "")
    team_usernames = [u.strip() for u in team_usernames_str.split(",") if u.strip()]

    # Parse optional fields with defaults
    poll_interval = int(data.get("POLL_INTERVAL", "30"))
    max_concurrent_workflows = int(data.get("MAX_CONCURRENT_WORKFLOWS", "5"))

    # Parse watched_statuses
    watched_statuses_str = data.get("WATCHED_STATUSES")
    if watched_statuses_str:
        watched_statuses = [s.strip() for s in watched_statuses_str.split(",")]
    else:
        watched_statuses = ["Research", "Plan", "Implement"]

    # Parse stage_models
    stage_models_str = data.get("STAGE_MODELS")
    if stage_models_str:
        try:
            stage_models = json.loads(stage_models_str)
        except json.JSONDecodeError as e:
            raise ValueError("STAGE_MODELS must be valid JSON") from e
    else:
        stage_models = {
            "Prepare": "haiku",
            "Research": "opus",
            "Plan": "opus",
            "Implement": "opus",
            "process_comments": "sonnet",
        }

    # Parse log settings
    log_level = data.get("LOG_LEVEL", "INFO")
    os.environ["LOG_LEVEL"] = log_level  # Set for logger module

    # Telemetry settings
    otel_endpoint = data.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    otel_service_name = data.get("OTEL_SERVICE_NAME", "kiln")
    claude_code_enable_telemetry = data.get("CLAUDE_CODE_ENABLE_TELEMETRY", "0") == "1"

    # Safety settings
    safety_allow_appended_tasks = int(data.get("SAFETY_ALLOW_APPENDED_TASKS", "0"))

    # Log masking settings
    ghes_logs_mask = data.get("GHES_LOGS_MASK", "true").lower() == "true"

    # PagerDuty settings
    pagerduty_routing_key = data.get("PAGERDUTY_ROUTING_KEY")
    if not pagerduty_routing_key:
        pagerduty_routing_key = None

    # Slack notification settings
    slack_bot_token = data.get("SLACK_BOT_TOKEN")
    if not slack_bot_token:
        slack_bot_token = None
    slack_user_id = data.get("SLACK_USER_ID")
    if not slack_user_id:
        slack_user_id = None
    slack_dm_on_comment = data.get("SLACK_DM_ON_COMMENT", "1") == "1"

    # Azure OAuth settings
    azure_tenant_id = data.get("AZURE_TENANT_ID")
    if not azure_tenant_id:
        azure_tenant_id = None
    azure_client_id = data.get("AZURE_CLIENT_ID")
    if not azure_client_id:
        azure_client_id = None
    azure_username = data.get("AZURE_USERNAME")
    if not azure_username:
        azure_username = None
    azure_password = data.get("AZURE_PASSWORD")
    if not azure_password:
        azure_password = None
    azure_scope = data.get("AZURE_SCOPE")
    if not azure_scope:
        azure_scope = None

    # Validate Azure OAuth: all fields must be set together or none
    azure_fields = [azure_tenant_id, azure_client_id, azure_username, azure_password]
    azure_fields_set = [f for f in azure_fields if f is not None]
    if azure_fields_set and len(azure_fields_set) != len(azure_fields):
        missing = []
        if not azure_tenant_id:
            missing.append("AZURE_TENANT_ID")
        if not azure_client_id:
            missing.append("AZURE_CLIENT_ID")
        if not azure_username:
            missing.append("AZURE_USERNAME")
        if not azure_password:
            missing.append("AZURE_PASSWORD")
        raise ValueError(
            f"Azure OAuth configuration is incomplete. Missing: {', '.join(missing)}. "
            "All Azure OAuth fields (AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_USERNAME, AZURE_PASSWORD) "
            "must be set together or none at all."
        )

    return Config(
        github_token=github_token,
        github_enterprise_host=github_enterprise_host,
        github_enterprise_token=github_enterprise_token,
        github_enterprise_version=github_enterprise_version,
        project_urls=project_urls,
        poll_interval=poll_interval,
        database_path=".kiln/kiln.db",
        workspace_dir=determine_workspace_dir(),
        watched_statuses=watched_statuses,
        username_self=username_self,
        team_usernames=team_usernames,
        max_concurrent_workflows=max_concurrent_workflows,
        log_file=".kiln/logs/kiln.log",
        stage_models=stage_models,
        otel_endpoint=otel_endpoint,
        otel_service_name=otel_service_name,
        claude_code_enable_telemetry=claude_code_enable_telemetry,
        safety_allow_appended_tasks=safety_allow_appended_tasks,
        ghes_logs_mask=ghes_logs_mask,
        pagerduty_routing_key=pagerduty_routing_key,
        slack_bot_token=slack_bot_token,
        slack_user_id=slack_user_id,
        slack_dm_on_comment=slack_dm_on_comment,
        azure_tenant_id=azure_tenant_id,
        azure_client_id=azure_client_id,
        azure_username=azure_username,
        azure_password=azure_password,
        azure_scope=azure_scope,
    )


def load_config_from_env() -> Config:
    """Load configuration from environment variables.

    Returns:
        Config: A Config instance populated from environment variables

    Raises:
        ValueError: If required environment variables are missing
    """
    # Collect all missing required vars
    missing_vars: list[str] = []

    github_token = os.environ.get("GITHUB_TOKEN")
    # Normalize empty string to None so gh CLI can use gh auth login credentials
    if not github_token:
        github_token = None

    # Parse GitHub Enterprise Server config
    github_enterprise_host = os.environ.get("GITHUB_ENTERPRISE_HOST")
    if not github_enterprise_host:
        github_enterprise_host = None

    github_enterprise_token = os.environ.get("GITHUB_ENTERPRISE_TOKEN")
    if not github_enterprise_token:
        github_enterprise_token = None

    # Validate mutual exclusivity: cannot have both github.com and GHES tokens
    if github_token and github_enterprise_token:
        raise ValueError(
            "Cannot configure both GITHUB_TOKEN and GITHUB_ENTERPRISE_TOKEN. "
            "Kiln operates against either github.com OR a GitHub Enterprise Server, not both."
        )

    # Parse GHES version (e.g., "3.14")
    github_enterprise_version = os.environ.get("GITHUB_ENTERPRISE_VERSION")
    if not github_enterprise_version:
        github_enterprise_version = None

    # Validate GitHub authentication - need either GITHUB_TOKEN or full GHES config
    if not github_token:
        # No github.com token - check GHES configuration
        has_any_ghes = github_enterprise_host or github_enterprise_token or github_enterprise_version
        if has_any_ghes:
            # Attempting GHES - need all three vars
            if not github_enterprise_host:
                missing_vars.append("GITHUB_ENTERPRISE_HOST")
            if not github_enterprise_token:
                missing_vars.append("GITHUB_ENTERPRISE_TOKEN")
            if not github_enterprise_version:
                missing_vars.append("GITHUB_ENTERPRISE_VERSION")
        else:
            # No auth configured at all
            missing_vars.append("GITHUB_TOKEN")

    # Set tokens in environment so Claude subprocesses can use gh CLI
    if github_token:
        os.environ["GITHUB_TOKEN"] = github_token
    if github_enterprise_token:
        os.environ["GITHUB_TOKEN"] = github_enterprise_token
        # gh CLI uses GH_ENTERPRISE_TOKEN for GHES authentication
        os.environ["GH_ENTERPRISE_TOKEN"] = github_enterprise_token

    # PROJECT_URLS: comma-separated list of project URLs - collect missing before raising
    project_urls_env = os.environ.get("PROJECT_URLS")
    if not project_urls_env:
        missing_vars.append("PROJECT_URLS")
        project_urls = []
    else:
        project_urls = [url.strip() for url in project_urls_env.split(",") if url.strip()]
        if not project_urls:
            missing_vars.append("PROJECT_URLS")  # Present but empty after parsing

    # Parse USERNAME_SELF (required) - collect missing before raising
    username_self = os.environ.get("USERNAME_SELF", "").strip()
    if not username_self:
        missing_vars.append("USERNAME_SELF")

    # Raise error listing all missing required vars
    if missing_vars:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing_vars)}"
        )

    # Validate PROJECT_URLS hostnames match the configured GitHub host
    _validate_project_urls_host(
        project_urls, github_token, github_enterprise_host, github_enterprise_token
    )

    poll_interval = int(os.environ.get("POLL_INTERVAL", "30"))

    database_path = os.environ.get("DATABASE_PATH", ".kiln/kiln.db")

    # Parse watched_statuses as comma-separated values if provided
    watched_statuses_env = os.environ.get("WATCHED_STATUSES")
    if watched_statuses_env:
        watched_statuses = [s.strip() for s in watched_statuses_env.split(",")]
    else:
        watched_statuses = ["Research", "Plan", "Implement"]

    max_concurrent_workflows = int(os.environ.get("MAX_CONCURRENT_WORKFLOWS", "5"))

    # Parse USERNAMES_TEAM as comma-separated list (optional)
    team_usernames_str = os.environ.get("USERNAMES_TEAM", "")
    team_usernames = [u.strip() for u in team_usernames_str.split(",") if u.strip()]

    log_file = os.environ.get("LOG_FILE", ".kiln/logs/kiln.log")
    log_size = int(os.environ.get("LOG_SIZE", 10 * 1024 * 1024))  # Default 10MB
    log_backups = int(os.environ.get("LOG_BACKUPS", 5))  # Default 5 backups

    # Parse STAGE_MODELS as JSON or use defaults
    stage_models_env = os.environ.get("STAGE_MODELS")
    if stage_models_env:
        try:
            stage_models = json.loads(stage_models_env)
        except json.JSONDecodeError as e:
            raise ValueError("STAGE_MODELS must be valid JSON") from e
    else:
        stage_models = {
            "Prepare": "haiku",
            "Research": "opus",
            "Plan": "opus",
            "Implement": "opus",
            "process_comments": "sonnet",
        }

    # PagerDuty settings
    pagerduty_routing_key = os.environ.get("PAGERDUTY_ROUTING_KEY")
    if not pagerduty_routing_key:
        pagerduty_routing_key = None

    # Slack notification settings
    slack_bot_token = os.environ.get("SLACK_BOT_TOKEN")
    if not slack_bot_token:
        slack_bot_token = None
    slack_user_id = os.environ.get("SLACK_USER_ID")
    if not slack_user_id:
        slack_user_id = None
    slack_dm_on_comment = os.environ.get("SLACK_DM_ON_COMMENT", "1") == "1"

    # Azure OAuth settings
    azure_tenant_id = os.environ.get("AZURE_TENANT_ID")
    if not azure_tenant_id:
        azure_tenant_id = None
    azure_client_id = os.environ.get("AZURE_CLIENT_ID")
    if not azure_client_id:
        azure_client_id = None
    azure_username = os.environ.get("AZURE_USERNAME")
    if not azure_username:
        azure_username = None
    azure_password = os.environ.get("AZURE_PASSWORD")
    if not azure_password:
        azure_password = None
    azure_scope = os.environ.get("AZURE_SCOPE")
    if not azure_scope:
        azure_scope = None

    # Validate Azure OAuth: all fields must be set together or none
    azure_fields = [azure_tenant_id, azure_client_id, azure_username, azure_password]
    azure_fields_set = [f for f in azure_fields if f is not None]
    if azure_fields_set and len(azure_fields_set) != len(azure_fields):
        missing = []
        if not azure_tenant_id:
            missing.append("AZURE_TENANT_ID")
        if not azure_client_id:
            missing.append("AZURE_CLIENT_ID")
        if not azure_username:
            missing.append("AZURE_USERNAME")
        if not azure_password:
            missing.append("AZURE_PASSWORD")
        raise ValueError(
            f"Azure OAuth configuration is incomplete. Missing: {', '.join(missing)}. "
            "All Azure OAuth fields (AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_USERNAME, AZURE_PASSWORD) "
            "must be set together or none at all."
        )

    return Config(
        github_token=github_token,
        github_enterprise_host=github_enterprise_host,
        github_enterprise_token=github_enterprise_token,
        github_enterprise_version=github_enterprise_version,
        project_urls=project_urls,
        poll_interval=poll_interval,
        database_path=database_path,
        workspace_dir=determine_workspace_dir(),
        watched_statuses=watched_statuses,
        username_self=username_self,
        team_usernames=team_usernames,
        max_concurrent_workflows=max_concurrent_workflows,
        log_file=log_file,
        log_size=log_size,
        log_backups=log_backups,
        stage_models=stage_models,
        otel_endpoint=os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", ""),
        otel_service_name=os.environ.get("OTEL_SERVICE_NAME", "kiln"),
        claude_code_enable_telemetry=os.environ.get("CLAUDE_CODE_ENABLE_TELEMETRY", "0") == "1",
        safety_allow_appended_tasks=int(os.environ.get("SAFETY_ALLOW_APPENDED_TASKS", "0")),
        ghes_logs_mask=os.environ.get("GHES_LOGS_MASK", "true").lower() == "true",
        pagerduty_routing_key=pagerduty_routing_key,
        slack_bot_token=slack_bot_token,
        slack_user_id=slack_user_id,
        slack_dm_on_comment=slack_dm_on_comment,
        azure_tenant_id=azure_tenant_id,
        azure_client_id=azure_client_id,
        azure_username=azure_username,
        azure_password=azure_password,
        azure_scope=azure_scope,
    )


def load_config() -> Config:
    """Load configuration from config file or environment variables.

    Priority:
    1. Config file at .kiln/config
    2. Environment variables (legacy mode)

    Returns:
        Config: A Config instance

    Raises:
        ValueError: If required configuration is missing
    """
    config_path = Path.cwd() / KILN_DIR / CONFIG_FILE

    if config_path.exists():
        return load_config_from_file(config_path)
    else:
        # Fall back to environment variables for backward compatibility
        return load_config_from_env()
