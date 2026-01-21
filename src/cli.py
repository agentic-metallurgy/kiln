"""CLI entry point for kiln.

This module provides the main command-line interface for kiln.
On first run, it creates a .kiln/ directory with a sample config.
On subsequent runs, it loads the config and starts the daemon.
"""

import argparse
import shutil
import sys
from pathlib import Path

# Version is set during build
__version__ = "1.1.0"

KILN_DIR = ".kiln"
CONFIG_FILE = "config"


def get_sample_config() -> str:
    """Load sample config from bundled .env.example."""
    # PyInstaller sets sys._MEIPASS when running from bundle, else use repo root
    base_path = Path(sys._MEIPASS) if hasattr(sys, "_MEIPASS") else Path(__file__).parent.parent  # type: ignore[attr-defined]
    return (base_path / ".env.example").read_text()


def get_readme() -> str:
    """Load README from bundled README.md."""
    base_path = Path(sys._MEIPASS) if hasattr(sys, "_MEIPASS") else Path(__file__).parent.parent  # type: ignore[attr-defined]
    return (base_path / "README.md").read_text()


def get_banner() -> str:
    """Generate the KILN banner with fire gradient colors."""
    # ANSI 256-color codes for fire gradient
    # From bright yellow (226) -> orange (214) -> red-orange (202) -> red (196)
    RESET = "\033[0m"

    # Line 1: █▄▀ █ █   █▄ █
    # Gradient each character from yellow to orange
    c = [226, 220, 214, 214, 208, 208, 202, 202, 202, 196, 196, 196, 196, 196]
    chars1 = "█▄▀ █ █   █▄ █"
    line1 = "".join(f"\033[38;5;{c[i % len(c)]}m{ch}" for i, ch in enumerate(chars1))

    # Line 2: █ █ █ █▄▄ █ ▀█
    # Continue gradient into deeper reds
    c2 = [214, 208, 202, 202, 196, 196, 160, 160, 160, 124, 124, 124, 124, 124]
    chars2 = "█ █ █ █▄▄ █ ▀█"
    line2 = "".join(f"\033[38;5;{c2[i % len(c2)]}m{ch}" for i, ch in enumerate(chars2))

    return f"\n\n  {line1}{RESET}\n  {line2}{RESET}\n  v{__version__}\n\n"


BANNER_PLAIN = f"""

  █▄▀ █ █   █▄ █
  █ █ █ █▄▄ █ ▀█
  v{__version__}

"""


def get_kiln_dir() -> Path:
    """Get the .kiln directory path in the current working directory."""
    return Path.cwd() / KILN_DIR


def extract_claude_resources() -> Path:
    """Extract bundled Claude resources to .kiln/ directory.

    Copies commands, agents, and skills from the bundled .claude/ folder
    (or repo root in development) to .kiln/commands, .kiln/agents, .kiln/skills.

    This is called on every startup to ensure the latest resources are available.

    Returns:
        Path to the .kiln directory containing extracted resources
    """
    kiln_dir = get_kiln_dir()

    # Source .claude from bundle or repo root
    base_path = Path(sys._MEIPASS) if hasattr(sys, "_MEIPASS") else Path(__file__).parent.parent  # type: ignore[attr-defined]

    source_claude = base_path / ".claude"

    if not source_claude.exists():
        return kiln_dir

    # Extract each subdirectory (commands, agents, skills)
    for subdir in ["commands", "agents", "skills"]:
        src = source_claude / subdir
        dest = kiln_dir / subdir

        if not src.exists():
            continue

        # Remove existing and copy fresh
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)

    return kiln_dir


def install_claude_resources() -> None:
    """Copy kiln resources to ~/.claude/ for Claude Code to discover.

    Copies kiln-prefixed commands, agents, and skills from .kiln/ to ~/.claude/.
    Files are copied directly (not into a subdirectory), overwriting existing files.

    This approach avoids symlink issues where Claude Code may recreate directories
    on startup, removing symlinks.

    Raises:
        RuntimeError: If resources cannot be written to ~/.claude/
    """
    from src.logger import get_logger

    logger = get_logger(__name__)

    kiln_dir = get_kiln_dir()
    claude_home = Path.home() / ".claude"

    # Define exactly which resources to install (excludes arch-eval.md)
    RESOURCES_TO_INSTALL = {
        "commands": [
            "kiln-create_plan_github.md",
            "kiln-create_plan_simple.md",
            "kiln-implement_github.md",
            "kiln-prepare_implementation_github.md",
            "kiln-research_codebase_github.md",
        ],
        "agents": [
            "kiln-codebase-analyzer.md",
            "kiln-codebase-locator.md",
            "kiln-codebase-pattern-finder.md",
            "kiln-pr-review.md",
            "kiln-thoughts-analyzer.md",
            "kiln-thoughts-locator.md",
            "kiln-web-search-researcher.md",
        ],
        "skills": [
            "kiln-create-worktree-from-issues",
            "kiln-edit-github-issue-components",
        ],
    }

    logger.debug(f"Installing kiln resources from {kiln_dir} to {claude_home}")

    installed_count = 0
    errors = []

    for subdir, items in RESOURCES_TO_INSTALL.items():
        source_dir = kiln_dir / subdir
        dest_dir = claude_home / subdir

        if not source_dir.exists():
            logger.debug(f"Skipping {subdir}: source {source_dir} does not exist")
            continue

        # Ensure destination directory exists
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            errors.append(f"Failed to create {dest_dir}: {e}")
            continue

        for item in items:
            src = source_dir / item
            dest = dest_dir / item

            if not src.exists():
                logger.warning(f"Source not found: {src}")
                continue

            try:
                if src.is_dir():
                    # Skills are directories - remove existing and copy
                    if dest.exists():
                        shutil.rmtree(dest)
                    shutil.copytree(src, dest)
                else:
                    # Commands/agents are files - copy with overwrite
                    shutil.copy2(src, dest)

                logger.debug(f"Installed: {dest}")
                installed_count += 1
            except Exception as e:
                errors.append(f"Failed to copy {src} to {dest}: {e}")

    if errors:
        error_msg = f"Failed to install kiln resources:\n" + "\n".join(errors)
        logger.error(error_msg)
        raise RuntimeError(error_msg)

    if installed_count > 0:
        logger.info(f"Installed {installed_count} kiln resource(s) to {claude_home}")
    else:
        logger.warning(f"No kiln resources installed - check {kiln_dir}")




def print_banner() -> None:
    """Print the kiln ASCII banner with fire gradient."""
    print(get_banner())


def init_kiln() -> None:
    """Initialize a new .kiln directory with sample config."""
    print_banner()

    kiln_dir = get_kiln_dir()
    config_path = kiln_dir / CONFIG_FILE
    readme_path = kiln_dir / "README.md"

    # Create .kiln directory
    kiln_dir.mkdir(exist_ok=True)

    # Create logs subdirectory
    (kiln_dir / "logs").mkdir(exist_ok=True)

    # Create workspaces directory with .gitkeep
    workspace_dir = Path.cwd() / "workspaces"
    workspace_dir.mkdir(exist_ok=True)
    (workspace_dir / ".gitkeep").touch()

    # Write sample config
    config_path.write_text(get_sample_config())

    # Write README
    readme_path.write_text(get_readme())

    print("Created:")
    print("  .kiln/")
    print("  .kiln/config")
    print("  .kiln/logs/")
    print("  .kiln/README.md")
    print("  workspaces/")
    print()
    print("Next steps:")
    print("  1. Edit .kiln/config")
    print("  2. Run `kiln` again")


def run_daemon(daemon_mode: bool = False) -> None:
    """Load config and run the daemon.

    Args:
        daemon_mode: If True, log to file only (background mode).
                     If False, log to both stdout and file.
    """
    from src.config import load_config
    from src.daemon import Daemon
    from src.logger import _extract_org_from_url, get_logger, setup_logging
    from src.setup import (
        SetupError,
        check_required_tools,
        configure_git_credential_helper,
        get_hostnames_from_project_urls,
        validate_project_columns,
    )
    from src.telemetry import get_git_version, init_telemetry
    from src.ticket_clients.github import GitHubTicketClient

    print_banner()

    try:
        # Phase 1: Check required CLI tools
        print("Checking required tools...")
        check_required_tools()
        print("  ✓ gh CLI found")
        print("  ✓ claude CLI found")
        print()

        # Phase 2: Extract Claude resources to .kiln/
        print("Extracting Claude resources...")
        extract_claude_resources()
        print("  ✓ Resources extracted to .kiln/")
        print()

        # Phase 2b: Install kiln resources to ~/.claude/
        print("Installing kiln resources to ~/.claude/...")
        install_claude_resources()
        print("  ✓ Kiln resources installed")
        print()

        # Phase 3: Load and validate config
        print("Loading configuration...")
        config = load_config()
        print("  ✓ PROJECT_URLS configured")
        print("  ✓ ALLOWED_USERNAMES configured")
        print()

        # Phase 3b: Configure git credentials
        print("Configuring git credentials...")
        hostnames = get_hostnames_from_project_urls(config.project_urls)
        for hostname in sorted(hostnames):
            configure_git_credential_helper(hostname)
            print(f"  ✓ Configured credential helper for {hostname}")
        print()

        # Phase 4: Validate project columns
        print("Validating project boards...")

        # Build tokens dict for client
        tokens: dict[str, str] = {}
        if config.github_enterprise_host and config.github_enterprise_token:
            tokens[config.github_enterprise_host] = config.github_enterprise_token
        elif config.github_token:
            tokens["github.com"] = config.github_token

        client = GitHubTicketClient(tokens)

        for project_url in config.project_urls:
            result = validate_project_columns(client, project_url)
            if result.action == "ok":
                print(f"  ✓ {project_url}")
                print("      All required columns present and correctly ordered")
            elif result.action in ("created", "reordered"):
                print(f"  ✓ {project_url}")
                print(f"      {result.message}")
        print()

        # Extract org name from first project URL for log masking
        org_name = None
        if config.project_urls:
            org_name = _extract_org_from_url(config.project_urls[0])

        # Always log to file; stdout/stderr only in non-daemon mode
        setup_logging(
            log_file=config.log_file,
            log_size=config.log_size,
            log_backups=config.log_backups,
            daemon_mode=daemon_mode,
            ghes_logs_mask=config.ghes_logs_mask,
            ghes_host=config.github_enterprise_host,
            org_name=org_name,
        )

        logger = get_logger(__name__)
        logger.info(f"=== Kiln Starting (v{__version__}) ===")
        logger.info(f"Logging to {config.log_file}")

        git_version = get_git_version()
        logger.info(f"Git version: {git_version}")

        if config.otel_endpoint:
            init_telemetry(
                config.otel_endpoint,
                config.otel_service_name,
                service_version=git_version,
            )

        daemon = Daemon(config, version=git_version)
        daemon.run()

    except SetupError as e:
        print(f"\n{e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as e:
        print(f"\n{e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        sys.exit(0)


def main() -> None:
    """Main entry point for the kiln CLI."""
    parser = argparse.ArgumentParser(
        prog="kiln",
        description="GitHub project automation daemon with Claude-powered workflows",
    )
    parser.add_argument(
        "--version",
        "-v",
        action="version",
        version=f"kiln {__version__}",
    )
    parser.add_argument(
        "--daemon",
        "-d",
        action="store_true",
        help="Run in daemon mode (log to file only, no stdout)",
    )
    args = parser.parse_args()

    kiln_dir = get_kiln_dir()
    config_path = kiln_dir / CONFIG_FILE

    if not config_path.exists():
        # First run: initialize
        init_kiln()
    else:
        # Config exists: run
        run_daemon(daemon_mode=args.daemon)


if __name__ == "__main__":
    main()
