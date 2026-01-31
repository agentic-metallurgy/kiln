"""
Logging module for agentic-metallurgy.

Provides a simple interface to configure and retrieve loggers using Python's
built-in logging module.
"""

from __future__ import annotations

import contextvars
import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler

# Context variable for issue tracking (thread-safe)
_issue_context: contextvars.ContextVar[str] = contextvars.ContextVar(
    "issue_context", default="kiln-system"
)


def set_issue_context(repo: str | None = None, issue_number: int | None = None) -> None:
    """Set the current issue context for logging.

    Args:
        repo: Repository in 'owner/repo' format
        issue_number: Issue number
    """
    if repo and issue_number is not None:
        _issue_context.set(f"{repo}#{issue_number}")
    else:
        _issue_context.set("kiln-system")


def clear_issue_context() -> None:
    """Clear the issue context, resetting to kiln-system."""
    _issue_context.set("kiln-system")


def get_issue_context() -> str:
    """Get the current issue context string."""
    return _issue_context.get()


# ANSI color codes
class Colors:
    RESET = "\033[0m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    GRAY = "\033[90m"
    ORANGE = "\033[38;5;208m"


# Semantic color categories for INFO logs
# Keywords that indicate specific event types
SEMANTIC_COLORS = {
    # Starting/Initializing - Green
    "starting": ("green", ">>>"),
    "initializing": ("green", ">>>"),
    "daemon starting": ("green", ">>>"),
    "cloning": ("green", ">>>"),
    "creating": ("green", ">>>"),
    "running": ("green", ">>>"),
    "fetching": ("green", ">>>"),
    "rebasing": ("green", ">>>"),
    # Completion/Success - Green
    "completed": ("green", "✓"),
    "success": ("green", "✓"),
    "stopped": ("green", "✓"),
    # Cleanup - Blue
    "cleaned up": ("blue", "🧹"),
    "cleanup": ("blue", "🧹"),
    "removed worktree": ("blue", "🧹"),
    "removing": ("blue", "🧹"),
    # Reset - Purple/Magenta (use "reset:" to avoid matching label name 'reset')
    "reset:": ("magenta", "↺"),
    "cleared": ("magenta", "↺"),
    # Status changes - Yellow
    "status change": ("yellow", "→"),
    "updating project item": ("yellow", "→"),
    "updated project item": ("yellow", "→"),
    # Skipping - Gray
    "skipping": ("gray", "⊘"),
    "no items": ("gray", "⊘"),
    "already": ("gray", "⊘"),
    # Workflow states - Orange
    "preparing": ("orange", "⚙"),
    "researching": ("orange", "⚙"),
    "planning": ("orange", "⚙"),
    "implementing": ("orange", "⚙"),
}


class DateRotatingFileHandler(RotatingFileHandler):
    """RotatingFileHandler that adds date (yyyy-mm-dd) to backup filenames."""

    def rotation_filename(self, default_name: str) -> str:
        """Generate backup filename with date."""
        # default_name is like "kiln.log.1"
        # We want "kiln.2024-01-15.log.1"
        base = self.baseFilename
        dirname = os.path.dirname(base)
        basename = os.path.basename(base)

        # Extract the suffix (e.g., ".1", ".2")
        suffix = default_name[len(base) :]

        # Get current date
        date_str = datetime.now().strftime("%Y-%m-%d")

        # Insert date before extension
        if "." in basename:
            name_part, ext = basename.rsplit(".", 1)
            new_name = f"{name_part}.{date_str}.{ext}{suffix}"
        else:
            new_name = f"{basename}.{date_str}{suffix}"

        return os.path.join(dirname, new_name)


class ColoredFormatter(logging.Formatter):
    """Custom formatter that adds colors based on log level and semantic content."""

    COLOR_MAP = {
        "green": Colors.GREEN,
        "blue": Colors.BLUE,
        "magenta": Colors.MAGENTA,
        "yellow": Colors.YELLOW,
        "gray": Colors.GRAY,
        "red": Colors.RED,
        "orange": Colors.ORANGE,
    }

    def _get_semantic_color(self, message: str) -> tuple[str, str] | None:
        """
        Determine semantic color based on message content.

        Returns tuple of (color_name, prefix_symbol) or None if no match.
        """
        message_lower = message.lower()
        for keyword, (color, prefix) in SEMANTIC_COLORS.items():
            if keyword in message_lower:
                return (color, prefix)
        return None

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)

        # Color by log level for WARNING and above
        if record.levelno >= logging.ERROR:
            return f"{Colors.RED}{message}{Colors.RESET}"
        elif record.levelno >= logging.WARNING:
            return f"{Colors.YELLOW}{message}{Colors.RESET}"

        # Apply semantic coloring for INFO logs
        if record.levelno == logging.INFO:
            semantic = self._get_semantic_color(record.getMessage())
            if semantic:
                color_name, prefix = semantic
                color_code = self.COLOR_MAP.get(color_name, "")
                return f"{color_code}{prefix} {message}{Colors.RESET}"

        return message


class ContextAwareFormatter(ColoredFormatter):
    """Formatter that injects issue context from contextvars."""

    def __init__(
        self, fmt: str | None = None, masking_filter: "MaskingFilter | None" = None
    ) -> None:
        """Initialize the formatter.

        Args:
            fmt: Format string for log messages.
            masking_filter: Optional MaskingFilter to apply to issue_context.
        """
        super().__init__(fmt)
        self.masking_filter = masking_filter

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record with issue context."""
        issue_context = get_issue_context()
        if self.masking_filter:
            issue_context = self.masking_filter._mask_value(issue_context)
        record.issue_context = issue_context
        return super().format(record)


class PlainContextAwareFormatter(logging.Formatter):
    """Plain formatter (no colors) that injects issue context from contextvars."""

    def __init__(
        self, fmt: str | None = None, masking_filter: "MaskingFilter | None" = None
    ) -> None:
        """Initialize the formatter.

        Args:
            fmt: Format string for log messages.
            masking_filter: Optional MaskingFilter to apply to issue_context.
        """
        super().__init__(fmt)
        self.masking_filter = masking_filter

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record with issue context."""
        issue_context = get_issue_context()
        if self.masking_filter:
            issue_context = self.masking_filter._mask_value(issue_context)
        record.issue_context = issue_context
        return super().format(record)


class MaskingFilter(logging.Filter):
    """Filter that masks GHES hostname and org name in log records.

    When enabled, replaces GHES hostname with <GHES> and organization name
    with <ORG> in all log output to prevent exposure of sensitive
    infrastructure details.
    """

    def __init__(self, ghes_host: str | None, org_name: str | None) -> None:
        """Initialize MaskingFilter.

        Args:
            ghes_host: GitHub Enterprise Server hostname to mask (e.g., "github.corp.com").
                       If None or "github.com", masking is disabled.
            org_name: Organization name to mask (e.g., "myorg").
                      If None, only hostname is masked.
        """
        super().__init__()
        self.ghes_host = ghes_host
        self.org_name = org_name

    def filter(self, record: logging.LogRecord) -> bool:
        """Apply masking to the log record.

        Args:
            record: The log record to process.

        Returns:
            True to allow all records through (masking is applied in-place).
        """
        # Skip masking for github.com or when no GHES host configured
        if not self.ghes_host or self.ghes_host == "github.com":
            return True

        # Mask issue_context attribute if present
        if hasattr(record, "issue_context"):
            record.issue_context = self._mask_value(str(record.issue_context))

        # Mask the message content
        if record.msg:
            record.msg = self._mask_value(str(record.msg))

        # Mask any args that contain strings
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: self._mask_value(str(v)) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    self._mask_value(str(arg)) if isinstance(arg, str) else arg
                    for arg in record.args
                )

        return True

    def _mask_value(self, value: str) -> str:
        """Replace GHES hostname and org name with placeholders.

        Args:
            value: The string value to mask.

        Returns:
            The masked string with hostname replaced by <GHES> and org by <ORG>.
        """
        if self.ghes_host:
            value = value.replace(self.ghes_host, "<GHES>")
        if self.org_name:
            # Handle /org/ pattern (repo paths)
            value = value.replace(f"/{self.org_name}/", "/<ORG>/")
            # Handle /orgs/org pattern (project URLs)
            value = value.replace(f"/orgs/{self.org_name}", "/orgs/<ORG>")
        return value


def _extract_org_from_url(project_url: str) -> str | None:
    """Extract organization name from a project URL.

    Args:
        project_url: GitHub project URL, e.g., "https://github.com/orgs/myorg/projects/1"

    Returns:
        The organization name if found, otherwise None.
    """
    import re

    match = re.search(r"/orgs/([^/]+)/projects/", project_url)
    return match.group(1) if match else None


def setup_logging(
    log_file: str | None = "./logs/kiln.log",
    log_size: int = 10 * 1024 * 1024,
    log_backups: int = 50,
    daemon_mode: bool = False,
    ghes_logs_mask: bool = False,
    ghes_host: str | None = None,
    org_name: str | None = None,
) -> None:
    """
    Configure the root logger with a standard format and level.

    The log level can be configured via the LOG_LEVEL environment variable.
    Default level is INFO.

    Args:
        log_file: Path to log file. Required when daemon_mode=True.
        log_size: Max size in bytes before rotation. Default: 10MB
        log_backups: Number of backup files to keep. Default: 50
        daemon_mode: If True, log to file only (no stdout/stderr).
                     If False, log to both stdout/stderr and file.
        ghes_logs_mask: If True, mask GHES hostname and org name in logs.
        ghes_host: GitHub Enterprise Server hostname to mask. If None or
                   "github.com", masking is disabled regardless of ghes_logs_mask.
        org_name: Organization name to mask. Extracted from project URLs.

    Format: "[%(asctime)s] %(levelname)s %(threadName)s %(name)s: %(message)s"
    Output: When daemon_mode=False: stdout for INFO/DEBUG, stderr for WARNING+, and file.
            When daemon_mode=True: file only.
    """
    # Get log level from environment variable, default to INFO
    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    # Create masking filter if enabled and GHES is configured
    masking_filter = None
    if ghes_logs_mask and ghes_host and ghes_host != "github.com":
        masking_filter = MaskingFilter(ghes_host, org_name)

    # Create context-aware colored formatter (with optional masking)
    log_format = (
        "[%(asctime)s] %(levelname)s %(issue_context)s %(threadName)s %(name)s: %(message)s"
    )
    formatter = ContextAwareFormatter(log_format, masking_filter=masking_filter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove any existing handlers
    root_logger.handlers.clear()

    # Add console handlers only in non-daemon mode
    if not daemon_mode:
        # Create handler for INFO and DEBUG - outputs to stdout
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setLevel(logging.DEBUG)
        stdout_handler.addFilter(lambda record: record.levelno < logging.WARNING)
        stdout_handler.setFormatter(formatter)
        if masking_filter:
            stdout_handler.addFilter(masking_filter)

        # Create handler for WARNING and above - outputs to stderr
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setLevel(logging.WARNING)
        stderr_handler.setFormatter(formatter)
        if masking_filter:
            stderr_handler.addFilter(masking_filter)

        # Add handlers to root logger
        root_logger.addHandler(stdout_handler)
        root_logger.addHandler(stderr_handler)

    # Add file handler for persistent logging (always when log_file specified)
    if log_file:
        try:
            # Plain context-aware formatter for file output (no ANSI colors, with optional masking)
            plain_formatter = PlainContextAwareFormatter(
                log_format, masking_filter=masking_filter
            )

            log_dir = os.path.dirname(log_file)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)

            # DateRotatingFileHandler: configurable size and backup count, date in filenames
            file_handler = DateRotatingFileHandler(
                log_file,
                maxBytes=log_size,
                backupCount=log_backups,
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(plain_formatter)
            if masking_filter:
                file_handler.addFilter(masking_filter)
            root_logger.addHandler(file_handler)
            print(f"[logger] File handler added: {log_file}", file=sys.stderr)
        except Exception as e:
            print(f"[logger] Failed to create file handler: {e}", file=sys.stderr)


def get_logger(name: str) -> logging.Logger:
    """
    Get a configured logger with the specified name.

    Args:
        name: The name for the logger, typically __name__ of the calling module

    Returns:
        A configured Logger instance
    """
    return logging.getLogger(name)


def is_debug_mode() -> bool:
    """Check if logging is set to DEBUG level."""
    return logging.getLogger().level <= logging.DEBUG


def log_message(logger: logging.Logger, label: str, content: str) -> None:
    """Log message content - full in debug mode, truncated otherwise.

    Args:
        logger: The logger instance to use
        label: A descriptive label for the log entry
        content: The content to log (will be truncated if not in debug mode)
    """
    if is_debug_mode():
        logger.debug(f"{label}:\n{content}")
    else:
        logger.debug(f"{label}: {content[:100]}...")


class RunLogger:
    """Context manager for per-run logging.

    Adds a temporary file handler to capture logs for a specific workflow run.
    Creates a dedicated log file at .kiln/logs/{hostname}/{owner}/{repo}/{issue_number}/{workflow}-{timestamp}.log

    Example:
        with RunLogger("github.com/owner/repo", 42, "Research") as run_logger:
            # ... workflow execution ...
            run_logger.set_session_id("session123")
            run_logger.write_session_file()
    """

    def __init__(
        self,
        repo: str,
        issue_number: int,
        workflow: str,
        base_log_dir: str = ".kiln/logs",
        masking_filter: MaskingFilter | None = None,
    ) -> None:
        """Initialize RunLogger.

        Args:
            repo: Repository in 'hostname/owner/repo' format (e.g., 'github.com/owner/repo')
            issue_number: GitHub issue number
            workflow: Workflow name ('Research', 'Plan', 'Implement')
            base_log_dir: Base directory for log files
            masking_filter: Optional MaskingFilter to apply to logs
        """
        self.repo = repo
        self.issue_number = issue_number
        self.workflow = workflow
        self.base_log_dir = base_log_dir
        self.masking_filter = masking_filter

        self.started_at = datetime.now()
        self.log_path: str | None = None
        self.session_id: str | None = None
        self._handler: logging.FileHandler | None = None

    def _generate_log_path(self) -> str:
        """Generate hierarchical log path.

        Returns:
            Path in format: {base_log_dir}/{hostname}/{owner}/{repo}/{issue_number}/{workflow}-{timestamp}.log
        """
        # repo is "hostname/owner/repo" -> split into parts
        parts = self.repo.split("/")
        if len(parts) >= 3:
            # hostname/owner/repo format
            hostname = parts[0]
            owner_repo = "/".join(parts[1:])
        else:
            # Fallback for old owner/repo format
            hostname = "github.com"
            owner_repo = self.repo

        timestamp = self.started_at.strftime("%Y%m%d-%H%M")
        filename = f"{self.workflow.lower()}-{timestamp}.log"

        return os.path.join(
            self.base_log_dir,
            hostname,
            owner_repo,
            str(self.issue_number),
            filename,
        )

    def __enter__(self) -> "RunLogger":
        """Set up per-run file handler.

        Creates the log directory if needed and adds a file handler to the root logger.

        Returns:
            Self for context manager usage.
        """
        self.log_path = self._generate_log_path()
        log_dir = os.path.dirname(self.log_path)
        os.makedirs(log_dir, exist_ok=True)

        # Create file handler with same format as global log
        log_format = (
            "[%(asctime)s] %(levelname)s %(issue_context)s %(threadName)s %(name)s: %(message)s"
        )
        formatter = PlainContextAwareFormatter(log_format, masking_filter=self.masking_filter)

        self._handler = logging.FileHandler(self.log_path)
        self._handler.setLevel(logging.getLogger().level)  # Follow global level
        self._handler.setFormatter(formatter)
        if self.masking_filter:
            self._handler.addFilter(self.masking_filter)

        logging.getLogger().addHandler(self._handler)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Remove the per-run file handler and clean up.

        Args:
            exc_type: Exception type if an exception was raised
            exc_val: Exception value if an exception was raised
            exc_tb: Exception traceback if an exception was raised
        """
        if self._handler:
            self._handler.close()
            logging.getLogger().removeHandler(self._handler)
            self._handler = None

    def set_session_id(self, session_id: str) -> None:
        """Record the Claude session ID for this run.

        Args:
            session_id: The Claude session ID to associate with this run.
        """
        self.session_id = session_id

    def write_session_file(self) -> None:
        """Write .session file with session_id for Claude conversation lookup.

        Creates a companion file alongside the log file containing the session ID.
        This allows users to easily find the corresponding Claude conversation.
        """
        if self.log_path and self.session_id:
            session_path = self.log_path.replace(".log", ".session")
            with open(session_path, "w") as f:
                f.write(self.session_id)
