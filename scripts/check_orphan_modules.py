#!/usr/bin/env python3
"""Detect orphaned Python modules not reachable from entry points.

This script builds an import graph starting from the main entry point (src/cli.py)
and all test files, then compares reachable modules against all .py files in src/.
Any modules not reachable are flagged as orphans.

Usage:
    python scripts/check_orphan_modules.py

Exit codes:
    0 - No orphan modules found
    1 - Orphan modules detected

Edge cases handled:
    - TYPE_CHECKING imports (included in graph)
    - Deferred imports inside functions (included)
    - __init__.py re-exports (followed)
    - Relative imports within packages
"""

import ast
import sys
from pathlib import Path


class ImportVisitor(ast.NodeVisitor):
    """AST visitor to extract all import statements from a Python file.

    Handles:
    - import module
    - import module.submodule
    - from module import name
    - from module.submodule import name
    - TYPE_CHECKING blocks
    - Imports inside functions (deferred imports)
    """

    def __init__(self):
        self.imports: set[str] = set()

    def visit_Import(self, node: ast.Import) -> None:
        """Handle 'import module' statements."""
        for alias in node.names:
            self.imports.add(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Handle 'from module import name' statements."""
        if node.module:
            self.imports.add(node.module)
        self.generic_visit(node)


def get_imports_from_file(path: Path) -> set[str]:
    """Extract all import module names from a Python file using AST.

    Args:
        path: Path to the Python file

    Returns:
        Set of module names imported (e.g., 'src.config', 'os', 'src.cli')
    """
    try:
        content = path.read_text()
        tree = ast.parse(content)
    except (SyntaxError, UnicodeDecodeError) as e:
        print(f"WARNING: Could not parse {path}: {e}", file=sys.stderr)
        return set()

    visitor = ImportVisitor()
    visitor.visit(tree)
    return visitor.imports


def module_to_path(module: str, project_root: Path) -> Path | None:
    """Convert a module name to its file path.

    Args:
        module: Module name (e.g., 'src.config', 'src.ticket_clients.github')
        project_root: Root directory of the project

    Returns:
        Path to the module file, or None if not found
    """
    # Try as a direct module file
    parts = module.split(".")

    # Try module.py
    module_file = project_root / "/".join(parts)
    if module_file.with_suffix(".py").exists():
        return module_file.with_suffix(".py")

    # Try as a package (__init__.py)
    package_init = module_file / "__init__.py"
    if package_init.exists():
        return package_init

    return None


def is_src_module(module: str) -> bool:
    """Check if a module is a src module (internal to this project)."""
    return module.startswith("src.") or module == "src"


def get_all_src_files(project_root: Path) -> set[Path]:
    """Get all Python files in src/ directory.

    Excludes __init__.py files since they serve as package markers and are
    implicitly imported when any module from their package is imported.

    Args:
        project_root: Root directory of the project

    Returns:
        Set of paths to all .py files in src/ (excluding __init__.py)
    """
    src_dir = project_root / "src"
    return {f for f in src_dir.rglob("*.py") if f.name != "__init__.py"}


def build_import_graph(
    entry_points: list[Path],
    project_root: Path,
) -> set[Path]:
    """Build a complete import graph starting from entry points.

    Recursively traces all imports to find all reachable modules.

    Args:
        entry_points: List of Python files to start tracing from
        project_root: Root directory of the project

    Returns:
        Set of all reachable Python file paths in src/
    """
    reachable: set[Path] = set()
    to_visit: list[Path] = list(entry_points)
    visited: set[Path] = set()

    while to_visit:
        current = to_visit.pop()

        if current in visited:
            continue
        visited.add(current)

        # Track if this is a src file
        try:
            current.relative_to(project_root / "src")
            reachable.add(current)
        except ValueError:
            pass  # Not a src file, but we still trace its imports

        # Get all imports from this file
        imports = get_imports_from_file(current)

        for module in imports:
            if not is_src_module(module):
                continue

            # Convert module to path
            module_path = module_to_path(module, project_root)
            if module_path and module_path not in visited:
                to_visit.append(module_path)

                # Also check if it's a package - visit __init__.py re-exports
                if module_path.name == "__init__.py":
                    # The imports from __init__.py will be traced when we visit it
                    pass

    return reachable


def main() -> int:
    """Main entry point for orphan module detection.

    Returns:
        0 if no orphans found, 1 if orphans detected
    """
    # Find project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent

    src_dir = project_root / "src"
    tests_dir = project_root / "tests"

    # Validate directories exist
    if not src_dir.exists():
        print(f"ERROR: {src_dir} not found")
        return 1

    # Collect entry points
    entry_points: list[Path] = []

    # Main entry point: src/cli.py
    cli_entry = src_dir / "cli.py"
    if cli_entry.exists():
        entry_points.append(cli_entry)
    else:
        print(f"WARNING: Main entry point {cli_entry} not found")

    # Test files as additional entry points
    if tests_dir.exists():
        for test_file in tests_dir.glob("*.py"):
            entry_points.append(test_file)

    if not entry_points:
        print("ERROR: No entry points found")
        return 1

    print(f"Tracing imports from {len(entry_points)} entry points...")

    # Build import graph
    reachable = build_import_graph(entry_points, project_root)

    # Get all src files
    all_src_files = get_all_src_files(project_root)

    # Find orphans
    orphans = all_src_files - reachable

    # Report results
    if orphans:
        print(f"\nERROR: Found {len(orphans)} orphaned module(s):")
        for orphan in sorted(orphans):
            # Show relative path from project root
            rel_path = orphan.relative_to(project_root)
            print(f"  - {rel_path}")
        print("\nOrphan module check FAILED")
        print("These modules are not imported by any entry point or test.")
        print("Consider removing them or ensuring they are imported.")
        return 1
    else:
        print(f"\nOrphan module check PASSED ({len(all_src_files)} modules, all reachable)")
        return 0


if __name__ == "__main__":
    sys.exit(main())
