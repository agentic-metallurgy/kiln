"""CLI entry point for kiln.

This module provides the main command-line interface for kiln.
On first run, it creates a .kiln/ directory with a sample config.
On subsequent runs, it loads the config and starts the daemon.

Subcommands:
    kiln           - Run the daemon (default behavior)
    kiln logs      - View run history and logs for issues
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.database import Database

# Version is set during build
__version__ = "1.1.0"

KILN_DIR = ".kiln"
CONFIG_FILE = "config"

# ANSI escape codes for startup message colors
RESET = "\033[0m"
STARTUP_COLORS = {
    "glow": "\033[38;2;250;204;21m",  # #FACC15 - Phase 1 (brightest)
    "ember": "\033[38;2;245;158;11m",  # #F59E0B - Phase 2
    "fire": "\033[38;2;249;115;22m",  # #F97316 - Phase 3
    "heat": "\033[38;2;239;98;52m",  # #EF6234 - Phase 4+ (hottest)
}


def get_sample_config() -> str:
    """Load sample config from bundled .env.example."""
    # PyInstaller sets sys._MEIPASS when running from bundle, else use repo root
    base_path = Path(getattr(sys, "_MEIPASS", None) or Path(__file__).parent.parent)
    return (base_path / ".env.example").read_text()


def get_readme() -> str:
    """Load README from bundled README.md."""
    base_path = Path(getattr(sys, "_MEIPASS", None) or Path(__file__).parent.parent)
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


def startup_print(msg: str, color: str) -> None:
    """Print a startup message with the specified fire gradient color."""
    print(f"{STARTUP_COLORS.get(color, '')}{msg}{RESET}")


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
    base_path = Path(getattr(sys, "_MEIPASS", None) or Path(__file__).parent.parent)

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
        error_msg = "Failed to install kiln resources:\n" + "\n".join(errors)
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

    # Create worktrees directory with .gitkeep
    workspace_dir = Path.cwd() / "worktrees"
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
    print("  worktrees/")
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
    from src.integrations.telemetry import get_git_version, init_telemetry
    from src.logger import _extract_org_from_url, get_logger, setup_logging
    from src.setup import (
        SetupError,
        check_for_updates,
        check_required_tools,
        configure_git_credential_env,
        get_hostnames_from_project_urls,
        validate_project_columns,
    )
    from src.ticket_clients import get_github_client

    print_banner()

    try:
        # Phase 1: Check required CLI tools
        startup_print("Checking required tools...", "glow")
        claude_info = check_required_tools()
        startup_print("  ✓ gh CLI found", "glow")
        startup_print(
            f"  ✓ claude CLI found at {claude_info.path} ({claude_info.install_method}) v{claude_info.version}",
            "glow",
        )

        # Check for updates (non-blocking, fail-silent)
        update_info = check_for_updates(kiln_dir=get_kiln_dir())
        if update_info is not None:
            startup_print(
                f"  Update available: v{update_info.latest_version} (current: v{update_info.current_version})",
                "glow",
            )
            startup_print("  Run: brew upgrade kiln", "glow")
        print()

        # Phase 2: Extract Claude resources to .kiln/
        startup_print("Extracting Claude resources...", "ember")
        extract_claude_resources()
        startup_print("  ✓ Resources extracted to .kiln/", "ember")
        print()

        # Phase 2b: Install kiln resources to ~/.claude/
        startup_print("Installing kiln resources to ~/.claude/...", "ember")
        install_claude_resources()
        startup_print("  ✓ Kiln resources installed", "ember")
        print()

        # Phase 3: Load and validate config
        startup_print("Loading configuration...", "fire")
        config = load_config()
        startup_print("  ✓ PROJECT_URLS configured", "fire")
        startup_print("  ✓ ALLOWED_USERNAMES configured", "fire")
        print()

        # Phase 3b: Configure git credentials
        startup_print("Configuring git credentials...", "fire")
        hostnames = get_hostnames_from_project_urls(config.project_urls)
        configure_git_credential_env(hostnames)
        for hostname in sorted(hostnames):
            startup_print(f"  ✓ Configured credential helper for {hostname}", "fire")
        print()

        # Phase 4: Validate project columns
        startup_print("Validating project boards...", "heat")

        # Build tokens dict for client
        tokens: dict[str, str] = {}
        if config.github_enterprise_host and config.github_enterprise_token:
            tokens[config.github_enterprise_host] = config.github_enterprise_token
        elif config.github_token:
            tokens["github.com"] = config.github_token

        client = get_github_client(
            tokens=tokens,
            enterprise_version=config.github_enterprise_version,
        )

        total_projects = len(config.project_urls)
        for i, project_url in enumerate(config.project_urls, 1):
            result = validate_project_columns(
                client, project_url, project_index=i, total_projects=total_projects
            )
            if result.action == "ok":
                startup_print(f"  ✓ {project_url}", "heat")
                startup_print("      All required columns present and correctly ordered", "heat")
            elif result.action in ("created", "reordered", "replaced"):
                startup_print(f"  ✓ {project_url}", "heat")
                startup_print(f"      {result.message}", "heat")
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

        if config.workspace_dir == "workspaces":
            logger.info("Using workspaces/ directory (detected existing worktrees)")
            logger.info("New installs use worktrees/ by default")
        else:
            logger.info("Using worktrees/ directory")

        git_version = get_git_version()
        logger.info(f"Git version: {git_version}")

        if config.otel_endpoint:
            init_telemetry(
                config.otel_endpoint,
                config.otel_service_name,
                service_version=git_version,
            )

        # Initialize Slack if configured
        from src.integrations.slack import init_slack, send_startup_ping

        init_slack(config.slack_bot_token, config.slack_user_id)
        send_startup_ping()

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


def parse_issue_arg(issue_arg: str) -> tuple[str, int]:
    """Parse issue argument into repo and issue number.

    Supports formats:
        - owner/repo#42
        - hostname/owner/repo#42

    Args:
        issue_arg: Issue identifier string

    Returns:
        Tuple of (repo, issue_number) where repo includes hostname

    Raises:
        ValueError: If the argument format is invalid
    """
    # Pattern: optional hostname, owner/repo#number
    match = re.match(r"^(?:([^/]+)/)?([^/]+)/([^#]+)#(\d+)$", issue_arg)
    if not match:
        raise ValueError(
            f"Invalid issue format: {issue_arg}\n"
            "Expected format: owner/repo#42 or hostname/owner/repo#42"
        )

    hostname, owner, repo_name, issue_num = match.groups()
    if hostname is None:
        hostname = "github.com"

    repo = f"{hostname}/{owner}/{repo_name}"
    return repo, int(issue_num)


def format_duration(start: datetime, end: datetime | None) -> str:
    """Format duration between two timestamps."""
    if end is None:
        return "running..."
    delta = end - start
    total_seconds = int(delta.total_seconds())
    if total_seconds < 60:
        return f"{total_seconds}s"
    elif total_seconds < 3600:
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes}m {seconds}s"
    else:
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        return f"{hours}h {minutes}m"


def format_outcome(outcome: str | None) -> str:
    """Format run outcome with checkmark/cross symbol."""
    if outcome is None:
        return "⏳ running"
    elif outcome == "success":
        return "✓ success"
    elif outcome == "failed":
        return "✗ failed"
    elif outcome == "stalled":
        return "⚠ stalled"
    else:
        return f"? {outcome}"


def _determine_state(labels: set[str], board_status: str) -> str:
    """Determine display state from labels, falling back to board status.

    Args:
        labels: Set of label names from the issue
        board_status: Current status from the database

    Returns:
        Display state string
    """
    # Priority order: running labels > failure labels > complete labels > board status
    label_priority = [
        "preparing",
        "researching",
        "planning",
        "implementing",
        "reviewing",
        "editing",
        "implementation_failed",
        "research_failed",
        "yolo_failed",
        "research_ready",
        "plan_ready",
    ]
    for label in label_priority:
        if label in labels:
            return label
    return board_status.lower()


def cmd_logs_summary(db: Database) -> None:
    """Show summary of all tracked issues.

    Args:
        db: Database instance
    """
    from src.config import load_config
    from src.ticket_clients import get_github_client

    # Get all issues from database
    issues = db.get_all_issue_states()
    if not issues:
        print("No tracked issues found.")
        return

    # Build GitHub client for live data
    config = load_config()
    tokens: dict[str, str] = {}
    if config.github_enterprise_host and config.github_enterprise_token:
        tokens[config.github_enterprise_host] = config.github_enterprise_token
    elif config.github_token:
        tokens["github.com"] = config.github_token

    client = get_github_client(
        tokens=tokens,
        enterprise_version=config.github_enterprise_version,
    )

    # Print header
    print(f"\n{'Identifier':<25} {'Branch':<30} {'PR':<30} {'State'}")
    print("-" * 95)

    for issue in issues:
        # Format identifier as owner/repo#42 (strip hostname prefix)
        repo_parts = issue.repo.split("/")
        if len(repo_parts) == 3:
            # hostname/owner/repo -> owner/repo
            identifier = f"{repo_parts[1]}/{repo_parts[2]}#{issue.issue_number}"
        else:
            identifier = f"{issue.repo}#{issue.issue_number}"

        # Fetch labels for YOLO detection and state
        labels = client.get_ticket_labels(issue.repo, issue.issue_number)
        is_yolo = "yolo" in labels

        # Determine state from labels (most specific first)
        state = _determine_state(labels, issue.status)
        if is_yolo:
            state = f"{state} (yolo)"

        # Fetch PR info
        prs = client.get_linked_prs(issue.repo, issue.issue_number)
        open_pr = next((pr for pr in prs if pr.state == "OPEN"), None)

        # Format branch name (truncate if needed)
        if open_pr and open_pr.branch_name:
            branch = (
                open_pr.branch_name[:27] + "..."
                if len(open_pr.branch_name) > 30
                else open_pr.branch_name
            )
        else:
            branch = "-"

        # Format PR display (truncate title if needed)
        if open_pr and open_pr.title:
            title = open_pr.title
            if len(title) > 20:
                title = title[:20] + "..."
            pr_display = f"#{open_pr.number}: {title}"
        elif open_pr:
            pr_display = f"#{open_pr.number}"
        else:
            pr_display = "-"

        print(f"{identifier:<25} {branch:<30} {pr_display:<30} {state}")


def cmd_logs(args: argparse.Namespace) -> None:
    """Handle the 'logs' subcommand."""
    from src.database import Database

    kiln_dir = get_kiln_dir()
    db_path = kiln_dir / "kiln.db"

    if not db_path.exists():
        print("No database found. Run 'kiln' first to initialize.", file=sys.stderr)
        sys.exit(1)

    db = Database(str(db_path))

    # Summary view when no issue specified
    if args.issue is None:
        cmd_logs_summary(db)
        return

    try:
        repo, issue_number = parse_issue_arg(args.issue)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    # Handle --view: show specific log file contents
    if args.view is not None:
        record = db.get_run_record(args.view)
        if record is None:
            print(f"Run ID {args.view} not found.", file=sys.stderr)
            sys.exit(1)
        if record.repo != repo or record.issue_number != issue_number:
            print(
                f"Run ID {args.view} does not belong to {args.issue}.",
                file=sys.stderr,
            )
            sys.exit(1)
        if record.log_path is None:
            print(f"No log file for run ID {args.view}.", file=sys.stderr)
            sys.exit(1)

        log_file = Path(record.log_path)
        if not log_file.exists():
            print(f"Log file not found: {record.log_path}", file=sys.stderr)
            sys.exit(1)

        print(
            f"=== Log for run {args.view}: {record.workflow} @ {record.started_at.strftime('%Y-%m-%d %H:%M')} ===\n"
        )
        print(log_file.read_text())
        return

    # Handle --session: show Claude session path
    if args.session is not None:
        record = db.get_run_record(args.session)
        if record is None:
            print(f"Run ID {args.session} not found.", file=sys.stderr)
            sys.exit(1)
        if record.repo != repo or record.issue_number != issue_number:
            print(
                f"Run ID {args.session} does not belong to {args.issue}.",
                file=sys.stderr,
            )
            sys.exit(1)
        if record.session_id is None:
            print(f"No session ID for run ID {args.session}.", file=sys.stderr)
            sys.exit(1)

        # Session file is a companion .session file next to the log
        if record.log_path:
            session_file = Path(record.log_path).with_suffix(".session")
            if session_file.exists():
                print(f"Session file: {session_file}")
            else:
                print(f"Session ID: {record.session_id}")
                # Also show the typical Claude projects path
                print("\nClaude conversations are typically stored in:")
                print(f"  ~/.claude/projects/*/sessions/{record.session_id}.jsonl")
        else:
            print(f"Session ID: {record.session_id}")
        return

    # Default: list run history (--list is implicit)
    runs = db.get_run_history(repo, issue_number)

    if not runs:
        print(f"No run history found for {args.issue}.")
        return

    # Print header
    print(f"\nRun history for {args.issue}:\n")
    print(f"{'ID':<6} {'Workflow':<12} {'Started':<18} {'Duration':<12} {'Outcome'}")
    print("-" * 70)

    for run in runs:
        started_str = run.started_at.strftime("%Y-%m-%d %H:%M")
        duration = format_duration(run.started_at, run.completed_at)
        outcome = format_outcome(run.outcome)
        print(f"{run.id:<6} {run.workflow:<12} {started_str:<18} {duration:<12} {outcome}")

    print()
    print("Use 'kiln logs <issue> --view <id>' to view a specific log file.")
    print("Use 'kiln logs <issue> --session <id>' to get Claude session info.")


def cmd_run(args: argparse.Namespace) -> None:
    """Handle the 'run' subcommand (default daemon behavior)."""
    from src.setup import SetupError, validate_working_directory

    # Validate working directory before any other operations
    try:
        validate_working_directory()
    except SetupError as e:
        print(f"\n{e}", file=sys.stderr)
        sys.exit(1)

    kiln_dir = get_kiln_dir()
    config_path = kiln_dir / CONFIG_FILE

    if not config_path.exists():
        # First run: initialize
        init_kiln()
    else:
        # Config exists: run
        run_daemon(daemon_mode=args.daemon)


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

    # Create subparsers
    subparsers = parser.add_subparsers(dest="command")

    # 'run' subcommand (also the default behavior)
    run_parser = subparsers.add_parser(
        "run",
        help="Start the kiln daemon (default if no subcommand given)",
    )
    run_parser.add_argument(
        "--daemon",
        "-d",
        action="store_true",
        help="Run in daemon mode (log to file only, no stdout)",
    )

    # 'logs' subcommand
    logs_parser = subparsers.add_parser(
        "logs",
        help="View run history and logs for a specific issue",
    )
    logs_parser.add_argument(
        "issue",
        nargs="?",
        default=None,
        help="Issue identifier (e.g., owner/repo#42). If omitted, shows all issues.",
    )
    logs_parser.add_argument(
        "--list",
        "-l",
        action="store_true",
        default=True,
        help="List run history (default behavior)",
    )
    logs_parser.add_argument(
        "--view",
        type=int,
        metavar="RUN_ID",
        help="View the log file for a specific run ID",
    )
    logs_parser.add_argument(
        "--session",
        type=int,
        metavar="RUN_ID",
        help="Show Claude session info for a specific run ID",
    )

    args = parser.parse_args()

    # Handle commands
    if args.command == "logs":
        cmd_logs(args)
    elif args.command == "run":
        cmd_run(args)
    else:
        # No subcommand given - default to 'run' behavior
        # Use daemon flag from main parser
        args.command = "run"
        cmd_run(args)


if __name__ == "__main__":
    main()
