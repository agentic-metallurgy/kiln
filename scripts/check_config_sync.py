#!/usr/bin/env python3
"""Check that .env.example and config.py are in sync.

This script validates that all configuration variables documented in .env.example
are actually used in config.py, and vice versa. It uses AST parsing to extract
variable names from data.get() and os.environ.get() calls in the config loaders.

Usage:
    python scripts/check_config_sync.py

Exit codes:
    0 - Config is in sync (no mismatches)
    1 - Config drift detected (mismatches found)
"""

import ast
import re
import sys
from pathlib import Path


def extract_env_example_vars(path: Path) -> set[str]:
    """Extract variable names from .env.example.

    Parses lines in KEY=value format, skipping comments and empty lines.
    Handles both uncommented vars (USERNAME_SELF=) and commented examples (# LOG_LEVEL=INFO).

    Args:
        path: Path to .env.example file

    Returns:
        Set of variable names found in the file
    """
    vars_found = set()
    content = path.read_text()

    for line in content.splitlines():
        line = line.strip()

        # Skip empty lines
        if not line:
            continue

        # Handle commented lines - extract var if it's a commented example (# VAR=value)
        if line.startswith("#"):
            # Check if it's a commented-out config line (e.g., "# LOG_LEVEL=INFO")
            # vs a pure comment (e.g., "# This is a description")
            comment_content = line[1:].strip()
            if "=" in comment_content:
                # Check if it looks like a config variable (starts with uppercase letter)
                var_candidate = comment_content.split("=")[0].strip()
                if (
                    var_candidate
                    and var_candidate[0].isupper()
                    and var_candidate.replace("_", "").isalnum()
                ):
                    vars_found.add(var_candidate)
            continue

        # Handle uncommented lines with =
        if "=" in line:
            var = line.split("=")[0].strip()
            if var:
                vars_found.add(var)

    return vars_found


class ConfigVarVisitor(ast.NodeVisitor):
    """AST visitor to extract config variable names from get() calls within loader functions."""

    # Target functions where config vars are parsed
    LOADER_FUNCTIONS = {"load_config_from_file", "load_config_from_env"}

    def __init__(self):
        self.vars_found: set[str] = set()
        self._in_loader_function = False

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Track when we enter/exit loader functions."""
        if node.name in self.LOADER_FUNCTIONS:
            self._in_loader_function = True
            self.generic_visit(node)
            self._in_loader_function = False
        else:
            self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Visit function calls looking for data.get() and os.environ.get()."""
        # Only process calls inside loader functions
        if not self._in_loader_function:
            self.generic_visit(node)
            return

        # Check for method calls with .get()
        if isinstance(node.func, ast.Attribute) and node.func.attr == "get":
            # Check if it's called on 'data' or 'os.environ'
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "data":
                # data.get("VAR_NAME", ...)
                if node.args and isinstance(node.args[0], ast.Constant):
                    self.vars_found.add(node.args[0].value)
            elif isinstance(node.func.value, ast.Attribute):
                # os.environ.get("VAR_NAME", ...)
                if (
                    node.func.value.attr == "environ"
                    and isinstance(node.func.value.value, ast.Name)
                    and node.func.value.value.id == "os"
                ):
                    if node.args and isinstance(node.args[0], ast.Constant):
                        self.vars_found.add(node.args[0].value)

        # Continue visiting child nodes
        self.generic_visit(node)


def extract_config_py_vars(path: Path) -> set[str]:
    """Extract variable names accessed via data.get() or os.environ.get() in config loaders.

    Uses AST parsing to find all string literals passed as the first argument
    to .get() calls on 'data' or 'os.environ' objects, but ONLY within the
    load_config_from_file() and load_config_from_env() functions.

    Args:
        path: Path to config.py file

    Returns:
        Set of variable names found in the loader functions
    """
    content = path.read_text()
    tree = ast.parse(content)

    visitor = ConfigVarVisitor()
    visitor.visit(tree)

    return visitor.vars_found


def main() -> int:
    """Main entry point for config sync check.

    Returns:
        0 if configs are in sync, 1 if mismatches found
    """
    # Find project root (where .env.example is)
    script_dir = Path(__file__).parent
    project_root = script_dir.parent

    env_example_path = project_root / ".env.example"
    config_py_path = project_root / "src" / "config.py"

    # Validate files exist
    if not env_example_path.exists():
        print(f"ERROR: {env_example_path} not found")
        return 1

    if not config_py_path.exists():
        print(f"ERROR: {config_py_path} not found")
        return 1

    # Extract variables from both sources
    env_vars = extract_env_example_vars(env_example_path)
    config_vars = extract_config_py_vars(config_py_path)

    # Find mismatches
    documented_not_implemented = env_vars - config_vars
    implemented_not_documented = config_vars - env_vars

    # Report results
    has_errors = False

    if documented_not_implemented:
        has_errors = True
        print("ERROR: Variables documented in .env.example but NOT used in config.py:")
        for var in sorted(documented_not_implemented):
            print(f"  - {var}")
        print()

    if implemented_not_documented:
        has_errors = True
        print("ERROR: Variables used in config.py but NOT documented in .env.example:")
        for var in sorted(implemented_not_documented):
            print(f"  - {var}")
        print()

    if has_errors:
        print("Config sync check FAILED")
        return 1
    else:
        print(f"Config sync check PASSED ({len(env_vars)} variables in sync)")
        return 0


if __name__ == "__main__":
    sys.exit(main())
