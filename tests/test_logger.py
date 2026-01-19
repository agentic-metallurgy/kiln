"""Unit tests for the logger module."""

import logging
import sys
from datetime import datetime
from pathlib import Path

import pytest

from src.logger import (
    ColoredFormatter,
    Colors,
    ContextAwareFormatter,
    DateRotatingFileHandler,
    PlainContextAwareFormatter,
    clear_issue_context,
    get_issue_context,
    get_logger,
    set_issue_context,
    setup_logging,
)


@pytest.mark.unit
class TestSetIssueContext:
    """Tests for set_issue_context function."""

    def teardown_method(self):
        """Clean up issue context after each test."""
        clear_issue_context()

    def test_set_issue_context_formats_repo_and_number(self):
        """Test context is formatted as repo#number."""
        set_issue_context("owner/repo", 42)
        assert get_issue_context() == "owner/repo#42"

    def test_set_issue_context_with_different_numbers(self):
        """Test context with various issue numbers."""
        set_issue_context("org/project", 1)
        assert get_issue_context() == "org/project#1"

        set_issue_context("org/project", 9999)
        assert get_issue_context() == "org/project#9999"

    def test_set_issue_context_none_values_reset_to_default(self):
        """Test that None values reset context to kiln-system."""
        set_issue_context("owner/repo", 42)
        set_issue_context(None, None)
        assert get_issue_context() == "kiln-system"

    def test_set_issue_context_none_repo_resets(self):
        """Test that None repo resets context."""
        set_issue_context("owner/repo", 42)
        set_issue_context(None, 42)
        assert get_issue_context() == "kiln-system"


@pytest.mark.unit
class TestClearIssueContext:
    """Tests for clear_issue_context function."""

    def test_clear_issue_context_resets_to_default(self):
        """Test clear_issue_context resets to kiln-system."""
        set_issue_context("owner/repo", 42)
        clear_issue_context()
        assert get_issue_context() == "kiln-system"

    def test_clear_issue_context_when_already_default(self):
        """Test clear_issue_context works when already at default."""
        clear_issue_context()
        assert get_issue_context() == "kiln-system"


@pytest.mark.unit
class TestGetIssueContext:
    """Tests for get_issue_context function."""

    def teardown_method(self):
        """Clean up issue context after each test."""
        clear_issue_context()

    def test_get_issue_context_default_value(self):
        """Test default context is kiln-system."""
        clear_issue_context()
        assert get_issue_context() == "kiln-system"


@pytest.mark.unit
class TestColoredFormatterGetSemanticColor:
    """Tests for ColoredFormatter._get_semantic_color()."""

    def test_get_semantic_color_starting_keyword(self):
        """Test 'starting' keyword returns green color with >>> prefix."""
        formatter = ColoredFormatter()
        result = formatter._get_semantic_color("Starting daemon process")
        assert result == ("green", ">>>")

    def test_get_semantic_color_completed_keyword(self):
        """Test 'completed' keyword returns green color with checkmark."""
        formatter = ColoredFormatter()
        result = formatter._get_semantic_color("Task completed successfully")
        assert result == ("green", "✓")

    def test_get_semantic_color_skipping_keyword(self):
        """Test 'skipping' keyword returns gray color."""
        formatter = ColoredFormatter()
        result = formatter._get_semantic_color("Skipping inactive issue")
        assert result == ("gray", "⊘")

    def test_get_semantic_color_cleanup_keyword(self):
        """Test 'cleanup' keyword returns blue color."""
        formatter = ColoredFormatter()
        result = formatter._get_semantic_color("Cleanup of workspace")
        assert result == ("blue", "🧹")

    def test_get_semantic_color_status_change_keyword(self):
        """Test 'status change' keyword returns yellow color."""
        formatter = ColoredFormatter()
        result = formatter._get_semantic_color("Status change detected")
        assert result == ("yellow", "→")

    def test_get_semantic_color_no_match(self):
        """Test message without keyword returns None."""
        formatter = ColoredFormatter()
        result = formatter._get_semantic_color("Regular log message")
        assert result is None

    def test_get_semantic_color_case_insensitive(self):
        """Test keyword matching is case-insensitive."""
        formatter = ColoredFormatter()
        result = formatter._get_semantic_color("STARTING daemon")
        assert result == ("green", ">>>")


@pytest.mark.unit
class TestColoredFormatterFormat:
    """Tests for ColoredFormatter.format()."""

    def test_format_error_level_adds_red_color(self):
        """Test ERROR level logs get red color."""
        formatter = ColoredFormatter("%(message)s")
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="Error message",
            args=(),
            exc_info=None,
        )
        result = formatter.format(record)
        assert result.startswith(Colors.RED)
        assert result.endswith(Colors.RESET)

    def test_format_warning_level_adds_yellow_color(self):
        """Test WARNING level logs get yellow color."""
        formatter = ColoredFormatter("%(message)s")
        record = logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname="",
            lineno=0,
            msg="Warning message",
            args=(),
            exc_info=None,
        )
        result = formatter.format(record)
        assert result.startswith(Colors.YELLOW)
        assert result.endswith(Colors.RESET)

    def test_format_info_level_with_semantic_keyword(self):
        """Test INFO level with semantic keyword gets color and prefix."""
        formatter = ColoredFormatter("%(message)s")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Starting process",
            args=(),
            exc_info=None,
        )
        result = formatter.format(record)
        assert ">>>" in result
        assert Colors.GREEN in result

    def test_format_info_level_without_keyword_no_change(self):
        """Test INFO level without keyword returns plain message."""
        formatter = ColoredFormatter("%(message)s")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Regular message",
            args=(),
            exc_info=None,
        )
        result = formatter.format(record)
        assert result == "Regular message"


@pytest.mark.unit
class TestContextAwareFormatter:
    """Tests for ContextAwareFormatter."""

    def teardown_method(self):
        """Clean up issue context after each test."""
        clear_issue_context()

    def test_context_aware_formatter_injects_issue_context(self):
        """Test formatter injects issue_context into record."""
        set_issue_context("owner/repo", 42)
        formatter = ContextAwareFormatter("%(issue_context)s - %(message)s")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        result = formatter.format(record)
        assert "owner/repo#42" in result


@pytest.mark.unit
class TestPlainContextAwareFormatter:
    """Tests for PlainContextAwareFormatter."""

    def teardown_method(self):
        """Clean up issue context after each test."""
        clear_issue_context()

    def test_plain_formatter_injects_context_without_colors(self):
        """Test plain formatter injects context without ANSI codes."""
        set_issue_context("owner/repo", 42)
        formatter = PlainContextAwareFormatter("%(issue_context)s - %(message)s")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Starting process",
            args=(),
            exc_info=None,
        )
        result = formatter.format(record)
        # Should contain context but no ANSI codes
        assert "owner/repo#42" in result
        assert "\033[" not in result


@pytest.mark.unit
class TestDateRotatingFileHandlerRotationFilename:
    """Tests for DateRotatingFileHandler.rotation_filename()."""

    def test_rotation_filename_includes_date(self, tmp_path):
        """Test that rotation filename includes current date."""
        log_file = tmp_path / "test.log"
        handler = DateRotatingFileHandler(str(log_file), maxBytes=1000, backupCount=5)

        default_name = str(log_file) + ".1"
        result = handler.rotation_filename(default_name)

        today = datetime.now().strftime("%Y-%m-%d")
        assert today in result
        assert result.endswith(".1")

    def test_rotation_filename_format(self, tmp_path):
        """Test rotation filename format is name.date.ext.N."""
        log_file = tmp_path / "kiln.log"
        handler = DateRotatingFileHandler(str(log_file), maxBytes=1000, backupCount=5)

        default_name = str(log_file) + ".2"
        result = handler.rotation_filename(default_name)

        today = datetime.now().strftime("%Y-%m-%d")
        expected_pattern = f"kiln.{today}.log.2"
        assert Path(result).name == expected_pattern


@pytest.mark.unit
class TestSetupLogging:
    """Tests for setup_logging function."""

    def teardown_method(self):
        """Clean up root logger after each test."""
        root = logging.getLogger()
        root.handlers.clear()
        root.setLevel(logging.WARNING)

    def test_setup_logging_creates_stdout_handler(self, monkeypatch):
        """Test that stdout handler is created for INFO/DEBUG."""
        monkeypatch.setenv("LOG_LEVEL", "INFO")
        setup_logging(log_file=None)

        root = logging.getLogger()
        stdout_handlers = [
            h
            for h in root.handlers
            if isinstance(h, logging.StreamHandler) and h.stream == sys.stdout
        ]
        assert len(stdout_handlers) == 1

    def test_setup_logging_creates_stderr_handler(self, monkeypatch):
        """Test that stderr handler is created for WARNING+."""
        monkeypatch.setenv("LOG_LEVEL", "INFO")
        setup_logging(log_file=None)

        root = logging.getLogger()
        stderr_handlers = [
            h
            for h in root.handlers
            if isinstance(h, logging.StreamHandler) and h.stream == sys.stderr
        ]
        assert len(stderr_handlers) == 1

    def test_setup_logging_creates_file_handler(self, tmp_path, monkeypatch):
        """Test that file handler is created when log_file specified."""
        monkeypatch.setenv("LOG_LEVEL", "INFO")
        log_file = tmp_path / "logs" / "test.log"
        setup_logging(log_file=str(log_file))

        root = logging.getLogger()
        file_handlers = [h for h in root.handlers if isinstance(h, DateRotatingFileHandler)]
        assert len(file_handlers) == 1

    def test_setup_logging_creates_log_directory(self, tmp_path, monkeypatch):
        """Test that log directory is created if it doesn't exist."""
        monkeypatch.setenv("LOG_LEVEL", "INFO")
        log_file = tmp_path / "newdir" / "test.log"
        setup_logging(log_file=str(log_file))

        assert log_file.parent.exists()

    def test_setup_logging_respects_log_level_env(self, monkeypatch):
        """Test that LOG_LEVEL environment variable is respected."""
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        setup_logging(log_file=None)

        root = logging.getLogger()
        assert root.level == logging.DEBUG


@pytest.mark.unit
class TestGetLogger:
    """Tests for get_logger function."""

    def test_get_logger_returns_named_logger(self):
        """Test that get_logger returns logger with given name."""
        logger = get_logger("test.module")
        assert logger.name == "test.module"

    def test_get_logger_returns_same_instance(self):
        """Test that same name returns same logger instance."""
        logger1 = get_logger("test.module")
        logger2 = get_logger("test.module")
        assert logger1 is logger2
