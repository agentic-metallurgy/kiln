"""
Logging module for agentic-metallurgy.

Provides a simple interface to configure and retrieve loggers using Python's
built-in logging module.
"""

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

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record with issue context."""
        record.issue_context = get_issue_context()
        return super().format(record)


class PlainContextAwareFormatter(logging.Formatter):
    """Plain formatter (no colors) that injects issue context from contextvars."""

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record with issue context."""
        record.issue_context = get_issue_context()
        return super().format(record)


def setup_logging(
    log_file: str | None = "./logs/kiln.log",
    log_size: int = 10 * 1024 * 1024,
    log_backups: int = 50,
) -> None:
    """
    Configure the root logger with a standard format and level.

    The log level can be configured via the LOG_LEVEL environment variable.
    Default level is INFO.

    Args:
        log_file: Path to log file, or None for stdout-only mode
        log_size: Max size in bytes before rotation. Default: 10MB
        log_backups: Number of backup files to keep. Default: 50

    Format: "[%(asctime)s] %(levelname)s %(threadName)s %(name)s: %(message)s"
    Output: stdout for INFO and DEBUG, stderr for WARNING and above,
            and optionally to the specified log file.
    """
    # Get log level from environment variable, default to INFO
    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    # Create context-aware colored formatter
    log_format = (
        "[%(asctime)s] %(levelname)s %(issue_context)s %(threadName)s %(name)s: %(message)s"
    )
    formatter = ContextAwareFormatter(log_format)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove any existing handlers
    root_logger.handlers.clear()

    # Create handler for INFO and DEBUG - outputs to stdout
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.DEBUG)
    stdout_handler.addFilter(lambda record: record.levelno < logging.WARNING)
    stdout_handler.setFormatter(formatter)

    # Create handler for WARNING and above - outputs to stderr
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.setFormatter(formatter)

    # Add handlers to root logger
    root_logger.addHandler(stdout_handler)
    root_logger.addHandler(stderr_handler)

    # Add file handler for persistent logging (if log_file specified)
    if log_file:
        # Plain context-aware formatter for file output (no ANSI colors)
        plain_formatter = PlainContextAwareFormatter(log_format)

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
        root_logger.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """
    Get a configured logger with the specified name.

    Args:
        name: The name for the logger, typically __name__ of the calling module

    Returns:
        A configured Logger instance
    """
    return logging.getLogger(name)
