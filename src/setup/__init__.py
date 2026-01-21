"""Setup validation module for kiln.

This module provides pre-flight checks that run before the daemon starts:
- CLI tool availability (gh, claude)
- Configuration validation
- GitHub project column validation
"""

from src.setup.checks import (
    SetupError,
    check_required_tools,
    configure_git_credential_helper,
    get_hostnames_from_project_urls,
)
from src.setup.project import validate_project_columns

__all__ = [
    "check_required_tools",
    "configure_git_credential_helper",
    "get_hostnames_from_project_urls",
    "validate_project_columns",
    "SetupError",
]
