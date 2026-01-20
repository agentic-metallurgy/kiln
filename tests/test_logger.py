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
    MaskingFilter,
    PlainContextAwareFormatter,
    _extract_org_from_url,
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

    def test_setup_logging_adds_masking_filter_when_enabled(self, tmp_path, monkeypatch):
        """Test that masking filter is added to handlers when enabled."""
        monkeypatch.setenv("LOG_LEVEL", "INFO")
        log_file = tmp_path / "logs" / "test.log"
        setup_logging(
            log_file=str(log_file),
            mask_ghes_logs=True,
            ghes_host="github.corp.com",
            org_name="myorg",
        )

        root = logging.getLogger()

        # Check that all handlers have a MaskingFilter
        for handler in root.handlers:
            masking_filters = [f for f in handler.filters if isinstance(f, MaskingFilter)]
            assert len(masking_filters) == 1, f"Handler {handler} should have MaskingFilter"
            assert masking_filters[0].ghes_host == "github.corp.com"
            assert masking_filters[0].org_name == "myorg"

    def test_setup_logging_no_masking_filter_when_disabled(self, tmp_path, monkeypatch):
        """Test that masking filter is not added when mask_ghes_logs is False."""
        monkeypatch.setenv("LOG_LEVEL", "INFO")
        log_file = tmp_path / "logs" / "test.log"
        setup_logging(
            log_file=str(log_file),
            mask_ghes_logs=False,
            ghes_host="github.corp.com",
            org_name="myorg",
        )

        root = logging.getLogger()

        # Check that no handlers have a MaskingFilter
        for handler in root.handlers:
            masking_filters = [f for f in handler.filters if isinstance(f, MaskingFilter)]
            assert len(masking_filters) == 0, f"Handler {handler} should not have MaskingFilter"

    def test_setup_logging_no_masking_filter_for_github_com(self, tmp_path, monkeypatch):
        """Test that masking filter is not added when host is github.com."""
        monkeypatch.setenv("LOG_LEVEL", "INFO")
        log_file = tmp_path / "logs" / "test.log"
        setup_logging(
            log_file=str(log_file),
            mask_ghes_logs=True,
            ghes_host="github.com",
            org_name="owner",
        )

        root = logging.getLogger()

        # Check that no handlers have a MaskingFilter
        for handler in root.handlers:
            masking_filters = [f for f in handler.filters if isinstance(f, MaskingFilter)]
            assert len(masking_filters) == 0, f"Handler {handler} should not have MaskingFilter"


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


@pytest.mark.unit
class TestMaskingFilter:
    """Tests for MaskingFilter class."""

    def test_mask_ghes_hostname(self):
        """Test GHES hostname is replaced with <GHES>."""
        f = MaskingFilter("github.corp.com", "myorg")
        assert f._mask_value("github.corp.com/myorg/repo") == "<GHES>/<ORG>/repo"

    def test_mask_project_url(self):
        """Test project URL is masked correctly."""
        f = MaskingFilter("github.corp.com", "myorg")
        url = "https://github.corp.com/orgs/myorg/projects/1"
        assert f._mask_value(url) == "https://<GHES>/orgs/<ORG>/projects/1"

    def test_mask_issue_context_format(self):
        """Test issue context format is masked correctly."""
        f = MaskingFilter("github.corp.com", "myorg")
        context = "github.corp.com/myorg/repo#42"
        assert f._mask_value(context) == "<GHES>/<ORG>/repo#42"

    def test_mask_only_hostname_when_no_org(self):
        """Test only hostname is masked when org is None."""
        f = MaskingFilter("github.corp.com", None)
        assert f._mask_value("github.corp.com/someorg/repo") == "<GHES>/someorg/repo"

    def test_mask_value_replaces_github_com_if_set(self):
        """Test _mask_value replaces the configured host (filter() handles skipping github.com)."""
        # _mask_value always does replacement; filter() decides whether to skip
        f = MaskingFilter("github.com", "owner")
        # This is expected because _mask_value just does string replacement
        # The github.com check happens in filter() which returns early
        assert f._mask_value("github.com/owner/repo") == "<GHES>/<ORG>/repo"

    def test_no_mask_when_ghes_host_none(self):
        """Test masking is disabled when ghes_host is None."""
        f = MaskingFilter(None, None)
        assert f._mask_value("github.corp.com/org/repo") == "github.corp.com/org/repo"

    def test_filter_masks_issue_context_attribute(self):
        """Test filter() masks the issue_context attribute on LogRecord."""
        f = MaskingFilter("github.corp.com", "myorg")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.issue_context = "github.corp.com/myorg/repo#42"

        f.filter(record)

        assert record.issue_context == "<GHES>/<ORG>/repo#42"

    def test_filter_masks_message(self):
        """Test filter() masks the message content."""
        f = MaskingFilter("github.corp.com", "myorg")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Processing https://github.corp.com/orgs/myorg/projects/1",
            args=(),
            exc_info=None,
        )

        f.filter(record)

        assert record.msg == "Processing https://<GHES>/orgs/<ORG>/projects/1"

    def test_filter_masks_args_tuple(self):
        """Test filter() masks string args in tuple."""
        f = MaskingFilter("github.corp.com", "myorg")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Processing %s",
            args=("github.corp.com/myorg/repo",),
            exc_info=None,
        )

        f.filter(record)

        assert record.args == ("<GHES>/<ORG>/repo",)

    def test_filter_masks_args_dict(self):
        """Test filter() masks string args in dict."""
        f = MaskingFilter("github.corp.com", "myorg")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Processing url",
            args=(),
            exc_info=None,
        )
        # Manually set dict args after creation to test dict handling
        record.args = {"url": "github.corp.com/myorg/repo"}

        f.filter(record)

        assert record.args == {"url": "<GHES>/<ORG>/repo"}

    def test_filter_returns_true_always(self):
        """Test filter() returns True to allow all records through."""
        f = MaskingFilter("github.corp.com", "myorg")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test",
            args=(),
            exc_info=None,
        )

        result = f.filter(record)

        assert result is True

    def test_filter_skips_masking_for_github_com(self):
        """Test filter() skips masking when GHES host is github.com."""
        f = MaskingFilter("github.com", "owner")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="github.com/owner/repo",
            args=(),
            exc_info=None,
        )

        f.filter(record)

        # Message should be unchanged
        assert record.msg == "github.com/owner/repo"

    def test_filter_skips_masking_when_disabled(self):
        """Test filter() skips masking when ghes_host is None."""
        f = MaskingFilter(None, None)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="github.corp.com/org/repo",
            args=(),
            exc_info=None,
        )

        f.filter(record)

        assert record.msg == "github.corp.com/org/repo"


@pytest.mark.unit
class TestExtractOrgFromUrl:
    """Tests for _extract_org_from_url helper function."""

    def test_extract_org_from_standard_project_url(self):
        """Test extraction from standard project URL format."""
        url = "https://github.com/orgs/myorg/projects/1"
        assert _extract_org_from_url(url) == "myorg"

    def test_extract_org_from_ghes_project_url(self):
        """Test extraction from GHES project URL."""
        url = "https://github.corp.com/orgs/enterprise-org/projects/42"
        assert _extract_org_from_url(url) == "enterprise-org"

    def test_extract_org_with_hyphens_and_numbers(self):
        """Test extraction of org name with hyphens and numbers."""
        url = "https://github.com/orgs/my-org-123/projects/5"
        assert _extract_org_from_url(url) == "my-org-123"

    def test_extract_org_returns_none_for_invalid_url(self):
        """Test None is returned for URLs without org pattern."""
        url = "https://github.com/owner/repo"
        assert _extract_org_from_url(url) is None

    def test_extract_org_returns_none_for_empty_string(self):
        """Test None is returned for empty string."""
        assert _extract_org_from_url("") is None

    def test_extract_org_returns_none_for_malformed_url(self):
        """Test None is returned for malformed URLs."""
        assert _extract_org_from_url("not-a-url") is None
        assert _extract_org_from_url("/orgs/") is None
