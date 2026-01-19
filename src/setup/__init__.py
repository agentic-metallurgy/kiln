"""Setup validation module for kiln.

This module provides pre-flight checks that run before the daemon starts:
- CLI tool availability (gh, claude)
- Configuration validation
- GitHub project column validation
"""

from src.setup.checks import SetupError, check_required_tools
from src.setup.project import validate_project_columns

__all__ = [
    "check_required_tools",
    "validate_project_columns",
    "SetupError",
]
