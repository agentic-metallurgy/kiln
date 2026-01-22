"""Integration tests for Daemon hibernation mode behavior.

These tests verify the daemon's hibernation functionality when network
errors are detected, including:
- Network error detection logic
- Hibernation state management (enter/exit)
- Fixed 5-minute interval during hibernation
- Non-network errors using exponential backoff
- PagerDuty alert integration
"""

import logging
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from src.daemon import Daemon


class TestIsNetworkError:
    """Tests for _is_network_error() detection logic."""

    @pytest.fixture
    def daemon(self, temp_workspace_dir):
        """Fixture providing Daemon with mocked dependencies."""
        config = MagicMock()
        config.poll_interval = 60
        config.watched_statuses = ["Research", "Plan", "Implement"]
        config.max_concurrent_workflows = 2
        config.database_path = f"{temp_workspace_dir}/test.db"
        config.workspace_dir = temp_workspace_dir
        config.project_urls = ["https://github.com/orgs/test/projects/1"]
        config.stage_models = {}
        config.github_enterprise_version = None
        config.pagerduty_routing_key = ""

        with patch("src.ticket_clients.github.GitHubTicketClient"):
            daemon = Daemon(config)
            daemon.ticket_client = MagicMock()
            daemon.comment_processor.ticket_client = daemon.ticket_client
            yield daemon
            daemon.stop()

    @pytest.mark.parametrize(
        "error_message",
        [
            "TLS handshake timeout",
            "SSL: CERTIFICATE_VERIFY_FAILED",
            "Connection refused",
            "Network unreachable",
            "Host unreachable",
            "DNS lookup failed",
            "Socket timeout",
            "Connection reset by peer",
            "Broken pipe",
            "EOF occurred",
            "connection timed out",
            "unable to connect to server",
            "name resolution failed",
            "tls: failed to verify certificate",
            "ssl handshake failed",
        ],
    )
    def test_detects_network_errors(self, daemon, error_message):
        """Test that various network error messages are correctly detected."""
        exception = Exception(error_message)
        assert daemon._is_network_error(exception) is True

    @pytest.mark.parametrize(
        "error_message",
        [
            "Bad credentials",
            "401 Unauthorized",
            "403 Forbidden",
            "Rate limit exceeded",
            "Not found",
            "Invalid JSON response",
            "Unexpected error occurred",
            "File not found",
            "Permission denied",
        ],
    )
    def test_non_network_errors_not_detected(self, daemon, error_message):
        """Test that non-network errors are not detected as network errors."""
        exception = Exception(error_message)
        assert daemon._is_network_error(exception) is False

    def test_case_insensitive_detection(self, daemon):
        """Test that network error detection is case-insensitive."""
        exception = Exception("TLS HANDSHAKE TIMEOUT")
        assert daemon._is_network_error(exception) is True

        exception = Exception("connection REFUSED")
        assert daemon._is_network_error(exception) is True


class TestEnterHibernation:
    """Tests for _enter_hibernation() method."""

    @pytest.fixture
    def daemon(self, temp_workspace_dir):
        """Fixture providing Daemon with mocked dependencies."""
        config = MagicMock()
        config.poll_interval = 60
        config.watched_statuses = ["Research", "Plan", "Implement"]
        config.max_concurrent_workflows = 2
        config.database_path = f"{temp_workspace_dir}/test.db"
        config.workspace_dir = temp_workspace_dir
        config.project_urls = ["https://github.com/orgs/test/projects/1"]
        config.stage_models = {}
        config.github_enterprise_version = None
        config.pagerduty_routing_key = ""

        with patch("src.ticket_clients.github.GitHubTicketClient"):
            daemon = Daemon(config)
            daemon.ticket_client = MagicMock()
            daemon.comment_processor.ticket_client = daemon.ticket_client
            yield daemon
            daemon.stop()

    def test_sets_hibernation_state(self, daemon):
        """Test that _enter_hibernation sets hibernation state correctly."""
        assert daemon._hibernating is False
        assert daemon._hibernation_start is None

        daemon._enter_hibernation("Test network failure")

        assert daemon._hibernating is True
        assert daemon._hibernation_start is not None
        assert isinstance(daemon._hibernation_start, datetime)

    def test_logs_warning_message(self, daemon, caplog):
        """Test that entering hibernation logs a warning."""
        with caplog.at_level(logging.WARNING):
            daemon._enter_hibernation("GitHub API unreachable")

        assert "Entering hibernation mode: GitHub API unreachable" in caplog.text

    def test_idempotent_when_already_hibernating(self, daemon):
        """Test that entering hibernation when already hibernating is a no-op."""
        daemon._enter_hibernation("First failure")
        first_start = daemon._hibernation_start

        daemon._enter_hibernation("Second failure")

        assert daemon._hibernating is True
        assert daemon._hibernation_start == first_start

    def test_hibernation_start_uses_utc(self, daemon):
        """Test that hibernation start time uses UTC timezone."""
        daemon._enter_hibernation("Test failure")

        assert daemon._hibernation_start is not None
        assert daemon._hibernation_start.tzinfo == UTC


class TestExitHibernation:
    """Tests for _exit_hibernation() method."""

    @pytest.fixture
    def daemon(self, temp_workspace_dir):
        """Fixture providing Daemon with mocked dependencies."""
        config = MagicMock()
        config.poll_interval = 60
        config.watched_statuses = ["Research", "Plan", "Implement"]
        config.max_concurrent_workflows = 2
        config.database_path = f"{temp_workspace_dir}/test.db"
        config.workspace_dir = temp_workspace_dir
        config.project_urls = ["https://github.com/orgs/test/projects/1"]
        config.stage_models = {}
        config.github_enterprise_version = None
        config.pagerduty_routing_key = ""

        with patch("src.ticket_clients.github.GitHubTicketClient"):
            daemon = Daemon(config)
            daemon.ticket_client = MagicMock()
            daemon.comment_processor.ticket_client = daemon.ticket_client
            yield daemon
            daemon.stop()

    def test_clears_hibernation_state(self, daemon):
        """Test that _exit_hibernation clears hibernation state."""
        daemon._hibernating = True
        daemon._hibernation_start = datetime.now(UTC)

        daemon._exit_hibernation()

        assert daemon._hibernating is False
        assert daemon._hibernation_start is None

    def test_logs_info_with_duration(self, daemon, caplog):
        """Test that exiting hibernation logs duration."""
        daemon._hibernating = True
        daemon._hibernation_start = datetime.now(UTC) - timedelta(seconds=300)

        with caplog.at_level(logging.INFO):
            daemon._exit_hibernation()

        assert "Exiting hibernation mode - connectivity restored" in caplog.text
        assert "duration:" in caplog.text

    def test_noop_when_not_hibernating(self, daemon, caplog):
        """Test that exiting when not hibernating is a no-op."""
        assert daemon._hibernating is False

        with caplog.at_level(logging.INFO):
            daemon._exit_hibernation()

        assert "Exiting hibernation mode" not in caplog.text

    def test_calculates_duration_correctly(self, daemon, caplog):
        """Test that hibernation duration is calculated correctly."""
        daemon._hibernating = True
        daemon._hibernation_start = datetime.now(UTC) - timedelta(seconds=600)

        with caplog.at_level(logging.INFO):
            daemon._exit_hibernation()

        # Duration should be approximately 600 seconds
        assert "duration: 60" in caplog.text or "duration: 599" in caplog.text


class TestHibernationInterval:
    """Tests for hibernation mode using fixed 5-minute interval."""

    @pytest.fixture
    def daemon(self, temp_workspace_dir):
        """Fixture providing Daemon with mocked dependencies."""
        config = MagicMock()
        config.poll_interval = 60
        config.watched_statuses = ["Research", "Plan", "Implement"]
        config.max_concurrent_workflows = 2
        config.database_path = f"{temp_workspace_dir}/test.db"
        config.workspace_dir = temp_workspace_dir
        config.project_urls = ["https://github.com/orgs/test/projects/1"]
        config.stage_models = {}
        config.github_enterprise_version = None
        config.pagerduty_routing_key = ""

        with patch("src.ticket_clients.github.GitHubTicketClient"):
            daemon = Daemon(config)
            daemon.ticket_client = MagicMock()
            daemon.comment_processor.ticket_client = daemon.ticket_client
            yield daemon
            daemon.stop()

    def test_hibernation_interval_constant(self, daemon):
        """Test that HIBERNATION_INTERVAL is 5 minutes (300 seconds)."""
        assert daemon.HIBERNATION_INTERVAL == 300

    def test_hibernation_uses_fixed_interval(self, daemon):
        """Test that hibernation uses fixed 5-minute interval instead of backoff."""
        wait_timeouts = []

        def mock_wait(timeout=None):
            wait_timeouts.append(timeout)
            # Return True on second wait to stop the loop
            return len(wait_timeouts) >= 2

        call_count = [0]

        def mock_poll():
            call_count[0] += 1
            raise Exception("TLS handshake timeout")

        with (
            patch.object(daemon, "_poll", side_effect=mock_poll),
            patch.object(daemon, "_initialize_project_metadata"),
            patch.object(daemon._shutdown_event, "wait", mock_wait),
        ):
            daemon.run()

        # Both waits should be the 5-minute hibernation interval (300s)
        # not exponential backoff (2, 4, 8...)
        assert wait_timeouts[0] == 300
        assert wait_timeouts[1] == 300

    def test_hibernation_logs_check_interval(self, daemon, caplog):
        """Test that hibernation logs the check interval message."""
        wait_count = [0]

        def mock_wait(timeout=None):
            wait_count[0] += 1
            return True  # Shutdown immediately

        def mock_poll():
            raise Exception("Connection refused")

        with (
            patch.object(daemon, "_poll", side_effect=mock_poll),
            patch.object(daemon, "_initialize_project_metadata"),
            patch.object(daemon._shutdown_event, "wait", mock_wait),
            caplog.at_level(logging.INFO),
        ):
            daemon.run()

        assert "Hibernation check in 5 minutes" in caplog.text


class TestNonNetworkErrorBackoff:
    """Tests for non-network errors still using exponential backoff."""

    @pytest.fixture
    def daemon(self, temp_workspace_dir):
        """Fixture providing Daemon with mocked dependencies."""
        config = MagicMock()
        config.poll_interval = 60
        config.watched_statuses = ["Research", "Plan", "Implement"]
        config.max_concurrent_workflows = 2
        config.database_path = f"{temp_workspace_dir}/test.db"
        config.workspace_dir = temp_workspace_dir
        config.project_urls = ["https://github.com/orgs/test/projects/1"]
        config.stage_models = {}
        config.github_enterprise_version = None
        config.pagerduty_routing_key = ""

        with patch("src.ticket_clients.github.GitHubTicketClient"):
            daemon = Daemon(config)
            daemon.ticket_client = MagicMock()
            daemon.comment_processor.ticket_client = daemon.ticket_client
            yield daemon
            daemon.stop()

    def test_non_network_errors_use_exponential_backoff(self, daemon):
        """Test that non-network errors use exponential backoff (not hibernation)."""
        wait_timeouts = []

        def mock_wait(timeout=None):
            wait_timeouts.append(timeout)
            return False

        call_count = [0]

        def mock_poll():
            call_count[0] += 1
            if call_count[0] >= 3:
                daemon._shutdown_requested = True
            raise Exception("Bad credentials")

        with (
            patch.object(daemon, "_poll", side_effect=mock_poll),
            patch.object(daemon, "_initialize_project_metadata"),
            patch.object(daemon._shutdown_event, "wait", mock_wait),
        ):
            daemon.run()

        # Should use exponential backoff: 2, 4, 8... not 300
        assert wait_timeouts[0] == 2.0
        assert wait_timeouts[1] == 4.0
        assert wait_timeouts[2] == 8.0

    def test_non_network_error_does_not_enter_hibernation(self, daemon):
        """Test that non-network errors don't enter hibernation mode."""
        call_count = [0]

        def mock_poll():
            call_count[0] += 1
            if call_count[0] >= 2:
                daemon._shutdown_requested = True
            raise Exception("Rate limit exceeded")

        def mock_wait(timeout=None):
            return False

        with (
            patch.object(daemon, "_poll", side_effect=mock_poll),
            patch.object(daemon, "_initialize_project_metadata"),
            patch.object(daemon._shutdown_event, "wait", mock_wait),
        ):
            daemon.run()

        assert daemon._hibernating is False


class TestPagerDutyIntegration:
    """Tests for PagerDuty calls during hibernation."""

    @pytest.fixture
    def daemon_with_pagerduty(self, temp_workspace_dir):
        """Fixture providing Daemon with PagerDuty configured."""
        config = MagicMock()
        config.poll_interval = 60
        config.watched_statuses = ["Research", "Plan", "Implement"]
        config.max_concurrent_workflows = 2
        config.database_path = f"{temp_workspace_dir}/test.db"
        config.workspace_dir = temp_workspace_dir
        config.project_urls = ["https://github.com/orgs/test/projects/1"]
        config.stage_models = {}
        config.github_enterprise_version = None
        config.pagerduty_routing_key = "test-routing-key"

        with patch("src.ticket_clients.github.GitHubTicketClient"):
            daemon = Daemon(config)
            daemon.ticket_client = MagicMock()
            daemon.comment_processor.ticket_client = daemon.ticket_client
            yield daemon
            daemon.stop()

    @pytest.fixture
    def daemon_without_pagerduty(self, temp_workspace_dir):
        """Fixture providing Daemon without PagerDuty configured."""
        config = MagicMock()
        config.poll_interval = 60
        config.watched_statuses = ["Research", "Plan", "Implement"]
        config.max_concurrent_workflows = 2
        config.database_path = f"{temp_workspace_dir}/test.db"
        config.workspace_dir = temp_workspace_dir
        config.project_urls = ["https://github.com/orgs/test/projects/1"]
        config.stage_models = {}
        config.github_enterprise_version = None
        config.pagerduty_routing_key = ""

        with patch("src.ticket_clients.github.GitHubTicketClient"):
            daemon = Daemon(config)
            daemon.ticket_client = MagicMock()
            daemon.comment_processor.ticket_client = daemon.ticket_client
            yield daemon
            daemon.stop()

    def test_pagerduty_trigger_called_on_hibernation_entry(self, daemon_with_pagerduty):
        """Test that PagerDuty trigger_alert is called when entering hibernation."""
        with patch("src.pagerduty.trigger_alert") as mock_trigger:
            daemon_with_pagerduty._enter_hibernation("TLS handshake timeout")

            mock_trigger.assert_called_once()
            call_args = mock_trigger.call_args
            assert call_args[1]["routing_key"] == "test-routing-key"
            assert call_args[1]["dedup_key"] == "kiln-hibernation"
            assert call_args[1]["summary"] == "Kiln daemon entered hibernation mode"
            assert call_args[1]["reason"] == "TLS handshake timeout"
            assert "custom_details" in call_args[1]

    def test_pagerduty_resolve_called_on_hibernation_exit(self, daemon_with_pagerduty):
        """Test that PagerDuty resolve_alert is called when exiting hibernation."""
        daemon_with_pagerduty._hibernating = True
        daemon_with_pagerduty._hibernation_start = datetime.now(UTC)

        with patch("src.pagerduty.resolve_alert") as mock_resolve:
            daemon_with_pagerduty._exit_hibernation()

            mock_resolve.assert_called_once_with(
                routing_key="test-routing-key",
                dedup_key="kiln-hibernation",
            )

    def test_pagerduty_not_called_when_not_configured(self, daemon_without_pagerduty):
        """Test that PagerDuty is not called when routing key is empty."""
        with (
            patch("src.pagerduty.trigger_alert") as mock_trigger,
            patch("src.pagerduty.resolve_alert") as mock_resolve,
        ):
            daemon_without_pagerduty._enter_hibernation("Network error")

            mock_trigger.assert_not_called()

            # Enter hibernation to enable exit
            daemon_without_pagerduty._hibernating = True
            daemon_without_pagerduty._hibernation_start = datetime.now(UTC)
            daemon_without_pagerduty._exit_hibernation()

            mock_resolve.assert_not_called()

    def test_pagerduty_trigger_includes_custom_details(self, daemon_with_pagerduty):
        """Test that PagerDuty trigger includes custom_details with timestamps."""
        with patch("src.pagerduty.trigger_alert") as mock_trigger:
            daemon_with_pagerduty._enter_hibernation("Connection refused")

            call_args = mock_trigger.call_args
            custom_details = call_args[1]["custom_details"]

            assert "project_urls" in custom_details
            assert custom_details["project_urls"] == [
                "https://github.com/orgs/test/projects/1"
            ]
            assert "hibernation_started" in custom_details
            assert "next_check" in custom_details

    def test_pagerduty_not_called_when_already_hibernating(self, daemon_with_pagerduty):
        """Test that PagerDuty is not re-triggered when already hibernating."""
        with patch("src.pagerduty.trigger_alert") as mock_trigger:
            daemon_with_pagerduty._enter_hibernation("First failure")
            assert mock_trigger.call_count == 1

            daemon_with_pagerduty._enter_hibernation("Second failure")
            # Should still be 1, not 2
            assert mock_trigger.call_count == 1


class TestHibernationExitOnSuccessfulPoll:
    """Tests for exiting hibernation after successful poll."""

    @pytest.fixture
    def daemon(self, temp_workspace_dir):
        """Fixture providing Daemon with mocked dependencies."""
        config = MagicMock()
        config.poll_interval = 60
        config.watched_statuses = ["Research", "Plan", "Implement"]
        config.max_concurrent_workflows = 2
        config.database_path = f"{temp_workspace_dir}/test.db"
        config.workspace_dir = temp_workspace_dir
        config.project_urls = ["https://github.com/orgs/test/projects/1"]
        config.stage_models = {}
        config.github_enterprise_version = None
        config.pagerduty_routing_key = ""

        with patch("src.ticket_clients.github.GitHubTicketClient"):
            daemon = Daemon(config)
            daemon.ticket_client = MagicMock()
            daemon.comment_processor.ticket_client = daemon.ticket_client
            yield daemon
            daemon.stop()

    def test_exits_hibernation_on_successful_poll(self, daemon, caplog):
        """Test that successful poll exits hibernation mode."""
        call_count = [0]

        def mock_poll():
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("TLS timeout")
            elif call_count[0] == 2:
                # Successful poll - should exit hibernation
                pass
            else:
                daemon._shutdown_requested = True

        def mock_wait(timeout=None):
            return False

        with (
            patch.object(daemon, "_poll", side_effect=mock_poll),
            patch.object(daemon, "_initialize_project_metadata"),
            patch.object(daemon._shutdown_event, "wait", mock_wait),
            caplog.at_level(logging.INFO),
        ):
            daemon.run()

        assert "Entering hibernation mode" in caplog.text
        assert "Exiting hibernation mode" in caplog.text
        assert daemon._hibernating is False

    def test_pagerduty_resolve_called_after_recovery(self, temp_workspace_dir):
        """Test that PagerDuty resolve is called after connectivity restored."""
        config = MagicMock()
        config.poll_interval = 60
        config.watched_statuses = ["Research", "Plan", "Implement"]
        config.max_concurrent_workflows = 2
        config.database_path = f"{temp_workspace_dir}/test.db"
        config.workspace_dir = temp_workspace_dir
        config.project_urls = ["https://github.com/orgs/test/projects/1"]
        config.stage_models = {}
        config.github_enterprise_version = None
        config.pagerduty_routing_key = "test-key"

        with patch("src.ticket_clients.github.GitHubTicketClient"):
            daemon = Daemon(config)
            daemon.ticket_client = MagicMock()
            daemon.comment_processor.ticket_client = daemon.ticket_client

            try:
                call_count = [0]

                def mock_poll():
                    call_count[0] += 1
                    if call_count[0] == 1:
                        raise Exception("Connection refused")
                    elif call_count[0] == 2:
                        pass  # Success
                    else:
                        daemon._shutdown_requested = True

                def mock_wait(timeout=None):
                    return False

                with (
                    patch.object(daemon, "_poll", side_effect=mock_poll),
                    patch.object(daemon, "_initialize_project_metadata"),
                    patch.object(daemon._shutdown_event, "wait", mock_wait),
                    patch("src.pagerduty.trigger_alert") as mock_trigger,
                    patch("src.pagerduty.resolve_alert") as mock_resolve,
                ):
                    daemon.run()

                mock_trigger.assert_called_once()
                mock_resolve.assert_called_once()
            finally:
                daemon.stop()
