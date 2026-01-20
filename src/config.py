"""Configuration module for kiln.

This module provides configuration management for the application,
loading settings from .kiln/config file (KEY=value format) with
fallback to environment variables for backward compatibility.
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

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
    allowed_username: str = ""  # Required, no default
    max_concurrent_workflows: int = 3
    log_file: str = ".kiln/logs/kiln.log"
    log_size: int = 10 * 1024 * 1024  # 10MB default
    log_backups: int = 50  # Keep 50 backup files by default
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

    # Validate GHES token requires GHES host
    if github_enterprise_token and not github_enterprise_host:
        raise ValueError(
            "GITHUB_ENTERPRISE_TOKEN requires GITHUB_ENTERPRISE_HOST. "
            "Please set the hostname of your GitHub Enterprise Server."
        )

    # Parse GHES version (e.g., "3.14")
    github_enterprise_version = data.get("GITHUB_ENTERPRISE_VERSION")
    if not github_enterprise_version:
        github_enterprise_version = None

    # Validate GHES version requires GHES host and token
    if github_enterprise_version and not (github_enterprise_host and github_enterprise_token):
        raise ValueError(
            "GITHUB_ENTERPRISE_VERSION requires GITHUB_ENTERPRISE_HOST and GITHUB_ENTERPRISE_TOKEN. "
            "Please configure all GitHub Enterprise Server settings."
        )

    # Set tokens in environment so Claude subprocesses can use gh CLI
    if github_token:
        os.environ["GITHUB_TOKEN"] = github_token
    if github_enterprise_token:
        os.environ["GITHUB_TOKEN"] = github_enterprise_token

    # Parse required fields
    project_urls_str = data.get("PROJECT_URLS", "")
    if not project_urls_str:
        raise ValueError("PROJECT_URLS is required in .kiln/config")
    project_urls = [url.strip() for url in project_urls_str.split(",") if url.strip()]
    if not project_urls:
        raise ValueError("At least one project URL must be provided")

    # Validate PROJECT_URLS hostnames match the configured GitHub host
    _validate_project_urls_host(
        project_urls, github_token, github_enterprise_host, github_enterprise_token
    )

    allowed_username = data.get("ALLOWED_USERNAME", "").strip()
    if not allowed_username:
        raise ValueError("ALLOWED_USERNAME is required in .kiln/config")

    # Parse optional fields with defaults
    poll_interval = int(data.get("POLL_INTERVAL", "30"))
    max_concurrent_workflows = int(data.get("MAX_CONCURRENT_WORKFLOWS", "3"))

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

    return Config(
        github_token=github_token,
        github_enterprise_host=github_enterprise_host,
        github_enterprise_token=github_enterprise_token,
        github_enterprise_version=github_enterprise_version,
        project_urls=project_urls,
        poll_interval=poll_interval,
        database_path=".kiln/kiln.db",
        workspace_dir="workspaces",
        watched_statuses=watched_statuses,
        allowed_username=allowed_username,
        max_concurrent_workflows=max_concurrent_workflows,
        log_file=".kiln/logs/kiln.log",
        stage_models=stage_models,
        otel_endpoint=otel_endpoint,
        otel_service_name=otel_service_name,
        claude_code_enable_telemetry=claude_code_enable_telemetry,
        safety_allow_appended_tasks=safety_allow_appended_tasks,
    )


def load_config_from_env() -> Config:
    """Load configuration from environment variables.

    Returns:
        Config: A Config instance populated from environment variables

    Raises:
        ValueError: If required environment variables (PROJECT_URLS) are missing
    """
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

    # Validate GHES token requires GHES host
    if github_enterprise_token and not github_enterprise_host:
        raise ValueError(
            "GITHUB_ENTERPRISE_TOKEN requires GITHUB_ENTERPRISE_HOST. "
            "Please set the hostname of your GitHub Enterprise Server."
        )

    # Parse GHES version (e.g., "3.14")
    github_enterprise_version = os.environ.get("GITHUB_ENTERPRISE_VERSION")
    if not github_enterprise_version:
        github_enterprise_version = None

    # Validate GHES version requires GHES host and token
    if github_enterprise_version and not (github_enterprise_host and github_enterprise_token):
        raise ValueError(
            "GITHUB_ENTERPRISE_VERSION requires GITHUB_ENTERPRISE_HOST and GITHUB_ENTERPRISE_TOKEN. "
            "Please configure all GitHub Enterprise Server settings."
        )

    # Set tokens in environment so Claude subprocesses can use gh CLI
    if github_token:
        os.environ["GITHUB_TOKEN"] = github_token
    if github_enterprise_token:
        os.environ["GITHUB_TOKEN"] = github_enterprise_token

    # PROJECT_URLS: comma-separated list of project URLs
    project_urls_env = os.environ.get("PROJECT_URLS")
    if not project_urls_env:
        raise ValueError("PROJECT_URLS environment variable is required")

    project_urls = [url.strip() for url in project_urls_env.split(",") if url.strip()]
    if not project_urls:
        raise ValueError("At least one project URL must be provided")

    # Validate PROJECT_URLS hostnames match the configured GitHub host
    _validate_project_urls_host(
        project_urls, github_token, github_enterprise_host, github_enterprise_token
    )

    poll_interval = int(os.environ.get("POLL_INTERVAL", "30"))

    database_path = os.environ.get("DATABASE_PATH", ".kiln/kiln.db")

    workspace_dir = os.environ.get("WORKSPACE_DIR", "workspaces")

    # Parse watched_statuses as comma-separated values if provided
    watched_statuses_env = os.environ.get("WATCHED_STATUSES")
    if watched_statuses_env:
        watched_statuses = [s.strip() for s in watched_statuses_env.split(",")]
    else:
        watched_statuses = ["Research", "Plan", "Implement"]

    max_concurrent_workflows = int(os.environ.get("MAX_CONCURRENT_WORKFLOWS", "3"))

    # Parse ALLOWED_USERNAME (required)
    allowed_username = os.environ.get("ALLOWED_USERNAME", "").strip()
    if not allowed_username:
        raise ValueError("ALLOWED_USERNAME environment variable is required")

    log_file = os.environ.get("LOG_FILE", ".kiln/logs/kiln.log")
    log_size = int(os.environ.get("LOG_SIZE", 10 * 1024 * 1024))  # Default 10MB
    log_backups = int(os.environ.get("LOG_BACKUPS", 50))  # Default 50 backups

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

    return Config(
        github_token=github_token,
        github_enterprise_host=github_enterprise_host,
        github_enterprise_token=github_enterprise_token,
        github_enterprise_version=github_enterprise_version,
        project_urls=project_urls,
        poll_interval=poll_interval,
        database_path=database_path,
        workspace_dir=workspace_dir,
        watched_statuses=watched_statuses,
        allowed_username=allowed_username,
        max_concurrent_workflows=max_concurrent_workflows,
        log_file=log_file,
        log_size=log_size,
        log_backups=log_backups,
        stage_models=stage_models,
        otel_endpoint=os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", ""),
        otel_service_name=os.environ.get("OTEL_SERVICE_NAME", "kiln"),
        claude_code_enable_telemetry=os.environ.get("CLAUDE_CODE_ENABLE_TELEMETRY", "0") == "1",
        safety_allow_appended_tasks=int(os.environ.get("SAFETY_ALLOW_APPENDED_TASKS", "0")),
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
