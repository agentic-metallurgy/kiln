"""Setup validation module for kiln.

This module provides pre-flight checks that run before the daemon starts:
- CLI tool availability (gh, claude)
- Configuration validation
- GitHub project column validation
"""

from src.setup.checks import (
    ClaudeInfo,
    SetupError,
    UpdateInfo,
    check_anthropic_env_vars,
    check_claude_installation,
    check_for_updates,
    check_required_tools,
    configure_git_credential_env,
    get_hostnames_from_project_urls,
    is_restricted_directory,
    validate_working_directory,
)
from src.setup.project import validate_project_columns

__all__ = [
    "ClaudeInfo",
    "UpdateInfo",
    "check_anthropic_env_vars",
    "check_claude_installation",
    "check_for_updates",
    "check_required_tools",
    "configure_git_credential_env",
    "get_hostnames_from_project_urls",
    "is_restricted_directory",
    "validate_project_columns",
    "validate_working_directory",
    "SetupError",
]
