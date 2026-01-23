"""Unit tests for Daemon hibernation functionality.

These tests verify the hibernation mode behavior:
- Health check (_check_github_connectivity)
- Hibernation entry/exit logic
- Main loop hibernation behavior with mocked connectivity
"""

from unittest.mock import MagicMock, patch

import pytest

from src.daemon import Daemon
from src.ticket_clients.base import NetworkError


@pytest.fixture
def daemon(temp_workspace_dir):
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

    with patch("src.ticket_clients.github.GitHubTicketClient"):
        daemon = Daemon(config)
        daemon.ticket_client = MagicMock()
        daemon.comment_processor.ticket_client = daemon.ticket_client
        yield daemon
        daemon.stop()


@pytest.mark.integration
class TestHibernationState:
    """Tests for hibernation state management."""

    def test_enter_hibernation_sets_flag(self, daemon):
        """Test that _enter_hibernation sets the flag to True."""
        daemon._enter_hibernation("test reason")
        assert daemon._hibernating is True

    def test_enter_hibernation_logs_warning(self, daemon):
        """Test that _enter_hibernation logs a warning with the reason."""
        with patch("src.daemon.logger") as mock_logger:
            daemon._enter_hibernation("GitHub API unreachable")
            mock_logger.warning.assert_any_call(
                "Entering hibernation mode: GitHub API unreachable"
            )

    def test_enter_hibernation_idempotent(self, daemon):
        """Test that calling _enter_hibernation twice doesn't log twice."""
        with patch("src.daemon.logger") as mock_logger:
            daemon._enter_hibernation("first reason")
            daemon._enter_hibernation("second reason")
            # Should only log once (first call)
            warning_calls = [
                call
                for call in mock_logger.warning.call_args_list
                if "Entering hibernation mode" in str(call)
            ]
            assert len(warning_calls) == 1

    def test_exit_hibernation_clears_flag(self, daemon):
        """Test that _exit_hibernation clears the flag."""
        daemon._hibernating = True
        daemon._exit_hibernation()
        assert daemon._hibernating is False

    def test_exit_hibernation_logs_info(self, daemon):
        """Test that _exit_hibernation logs connectivity restored."""
        daemon._hibernating = True
        with patch("src.daemon.logger") as mock_logger:
            daemon._exit_hibernation()
            mock_logger.info.assert_any_call(
                "Exiting hibernation mode: connectivity restored"
            )

    def test_exit_hibernation_idempotent(self, daemon):
        """Test that calling _exit_hibernation when not hibernating doesn't log."""
        daemon._hibernating = False
        with patch("src.daemon.logger") as mock_logger:
            daemon._exit_hibernation()
            # Should not log "Exiting hibernation" if not hibernating
            info_calls = [
                call
                for call in mock_logger.info.call_args_list
                if "Exiting hibernation mode" in str(call)
            ]
            assert len(info_calls) == 0


@pytest.mark.integration
class TestCheckGitHubConnectivity:
    """Tests for _check_github_connectivity method."""

    def test_connectivity_success_returns_true(self, daemon):
        """Test that successful connectivity check returns True."""
        daemon.ticket_client.validate_connection.return_value = True
        result = daemon._check_github_connectivity()
        assert result is True

    def test_connectivity_network_error_returns_false(self, daemon):
        """Test that NetworkError returns False."""
        daemon.ticket_client.validate_connection.side_effect = NetworkError(
            "TLS handshake timeout"
        )
        result = daemon._check_github_connectivity()
        assert result is False

    def test_connectivity_other_exception_returns_true(self, daemon):
        """Test that non-network exceptions return True (to skip hibernation)."""
        daemon.ticket_client.validate_connection.side_effect = RuntimeError(
            "Auth error"
        )
        result = daemon._check_github_connectivity()
        assert result is True

    def test_connectivity_checks_all_hostnames(self, daemon):
        """Test that connectivity is checked for all unique hostnames."""
        daemon.config.project_urls = [
            "https://github.com/orgs/test/projects/1",
            "https://github.com/orgs/other/projects/2",
            "https://ghes.company.com/orgs/corp/projects/1",
        ]
        daemon.ticket_client.validate_connection.return_value = True

        daemon._check_github_connectivity()

        # Should call validate_connection for each unique hostname
        call_args = [
            call[0][0] for call in daemon.ticket_client.validate_connection.call_args_list
        ]
        assert "github.com" in call_args
        assert "ghes.company.com" in call_args
        # github.com should only be called once even though 2 URLs use it
        assert call_args.count("github.com") == 1

    def test_connectivity_empty_project_urls_returns_true(self, daemon):
        """Test that empty project URLs returns True (no hosts to check)."""
        daemon.config.project_urls = []
        result = daemon._check_github_connectivity()
        assert result is True

    def test_connectivity_logs_warning_on_network_error(self, daemon):
        """Test that NetworkError is logged as warning."""
        daemon.ticket_client.validate_connection.side_effect = NetworkError(
            "Connection refused"
        )
        with patch("src.daemon.logger") as mock_logger:
            daemon._check_github_connectivity()
            # Should log warning about unreachable host
            warning_calls = [
                call
                for call in mock_logger.warning.call_args_list
                if "unreachable" in str(call).lower()
            ]
            assert len(warning_calls) >= 1

    def test_connectivity_calls_validate_connection_with_quiet_true(self, daemon):
        """Test that _check_github_connectivity passes quiet=True to validate_connection."""
        daemon.ticket_client.validate_connection.return_value = True

        daemon._check_github_connectivity()

        # Verify validate_connection was called with quiet=True
        daemon.ticket_client.validate_connection.assert_called_once()
        call_kwargs = daemon.ticket_client.validate_connection.call_args[1]
        assert call_kwargs.get("quiet") is True


@pytest.mark.integration
class TestMainLoopHibernation:
    """Tests for main loop hibernation behavior."""

    def test_hibernation_on_connectivity_failure(self, daemon):
        """Test that daemon enters hibernation when connectivity fails."""
        call_count = [0]

        def mock_connectivity_check():
            call_count[0] += 1
            if call_count[0] == 1:
                return False  # First check fails
            daemon._shutdown_requested = True
            return True  # Second check succeeds

        wait_timeouts = []

        def mock_wait(timeout=None):
            wait_timeouts.append(timeout)
            return False

        with (
            patch.object(daemon, "_check_github_connectivity", side_effect=mock_connectivity_check),
            patch.object(daemon, "_poll"),
            patch.object(daemon, "_initialize_project_metadata"),
            patch.object(daemon._shutdown_event, "wait", mock_wait),
        ):
            daemon.run()

        # Should have waited for HIBERNATION_INTERVAL (300s)
        assert 300 in wait_timeouts

    def test_hibernation_exit_on_connectivity_restored(self, daemon):
        """Test that daemon exits hibernation when connectivity is restored."""
        call_count = [0]

        def mock_connectivity_check():
            call_count[0] += 1
            if call_count[0] == 1:
                return False  # First check fails
            return True  # Second check succeeds

        def mock_wait(timeout=None):
            if daemon._hibernating:
                # While hibernating, simulate wait completion
                return False
            # After exiting hibernation, request shutdown
            daemon._shutdown_requested = True
            return True

        exited_hibernation = [False]
        original_exit = daemon._exit_hibernation

        def track_exit():
            exited_hibernation[0] = True
            original_exit()

        with (
            patch.object(daemon, "_check_github_connectivity", side_effect=mock_connectivity_check),
            patch.object(daemon, "_poll"),
            patch.object(daemon, "_initialize_project_metadata"),
            patch.object(daemon._shutdown_event, "wait", mock_wait),
            patch.object(daemon, "_exit_hibernation", side_effect=track_exit),
        ):
            daemon.run()

        assert exited_hibernation[0] is True

    def test_network_error_during_poll_continues_to_health_check(self, daemon):
        """Test that NetworkError during _poll loops back to health check."""
        poll_count = [0]

        def mock_poll():
            poll_count[0] += 1
            if poll_count[0] == 1:
                raise NetworkError("Connection lost during poll")
            daemon._shutdown_requested = True

        def mock_wait(timeout=None):
            return False

        with (
            patch.object(daemon, "_check_github_connectivity", return_value=True),
            patch.object(daemon, "_poll", side_effect=mock_poll),
            patch.object(daemon, "_initialize_project_metadata"),
            patch.object(daemon._shutdown_event, "wait", mock_wait),
        ):
            daemon.run()

        # Poll should be called twice (once failed with NetworkError, once succeeded)
        assert poll_count[0] == 2

    def test_non_network_error_uses_backoff_not_hibernation(self, daemon):
        """Test that non-network errors use exponential backoff, not hibernation."""
        poll_count = [0]
        wait_timeouts = []

        def mock_poll():
            poll_count[0] += 1
            if poll_count[0] >= 2:
                daemon._shutdown_requested = True
            raise RuntimeError("Internal error")

        def mock_wait(timeout=None):
            wait_timeouts.append(timeout)
            return False

        with (
            patch.object(daemon, "_check_github_connectivity", return_value=True),
            patch.object(daemon, "_poll", side_effect=mock_poll),
            patch.object(daemon, "_initialize_project_metadata"),
            patch.object(daemon._shutdown_event, "wait", mock_wait),
        ):
            daemon.run()

        # Should use exponential backoff (2, 4, ...) not hibernation interval (300)
        assert 2.0 in wait_timeouts
        assert 300 not in wait_timeouts

    def test_hibernation_interruptible_by_shutdown(self, daemon):
        """Test that hibernation sleep can be interrupted by shutdown signal."""
        wait_returns = [False]  # First wait returns True (interrupted)

        def mock_connectivity_check():
            return False  # Always fail

        def mock_wait(timeout=None):
            return wait_returns.pop(0) if wait_returns else True

        with (
            patch.object(daemon, "_check_github_connectivity", side_effect=mock_connectivity_check),
            patch.object(daemon, "_poll"),
            patch.object(daemon, "_initialize_project_metadata"),
            patch.object(daemon._shutdown_event, "wait", mock_wait),
        ):
            daemon.run()

        # Daemon should have stopped after shutdown signal during hibernation
        assert daemon._running is False

    def test_consecutive_hibernation_checks(self, daemon):
        """Test multiple consecutive failed connectivity checks stay in hibernation."""
        check_count = [0]
        hibernation_waits = []

        def mock_connectivity_check():
            check_count[0] += 1
            if check_count[0] >= 3:
                daemon._shutdown_requested = True
                return True
            return False

        def mock_wait(timeout=None):
            hibernation_waits.append(timeout)
            return False

        with (
            patch.object(daemon, "_check_github_connectivity", side_effect=mock_connectivity_check),
            patch.object(daemon, "_poll"),
            patch.object(daemon, "_initialize_project_metadata"),
            patch.object(daemon._shutdown_event, "wait", mock_wait),
        ):
            daemon.run()

        # Should have done 3 connectivity checks
        assert check_count[0] == 3
        # Should have waited twice at hibernation interval (300s), plus once for poll interval
        # First two waits at 300s (hibernation), last wait is poll interval (60s)
        assert hibernation_waits[:2] == [300, 300]


@pytest.mark.integration
class TestGetHostnameFromUrl:
    """Tests for _get_hostname_from_url helper method."""

    def test_github_com_url(self, daemon):
        """Test parsing github.com URL."""
        url = "https://github.com/orgs/test/projects/1"
        assert daemon._get_hostname_from_url(url) == "github.com"

    def test_ghes_url(self, daemon):
        """Test parsing GHES URL."""
        url = "https://github.mycompany.com/orgs/corp/projects/5"
        assert daemon._get_hostname_from_url(url) == "github.mycompany.com"

    def test_http_url(self, daemon):
        """Test parsing HTTP URL (should work even though not recommended)."""
        url = "http://github.local/orgs/test/projects/1"
        assert daemon._get_hostname_from_url(url) == "github.local"

    def test_invalid_url_returns_default(self, daemon):
        """Test that invalid URLs return default github.com."""
        assert daemon._get_hostname_from_url("invalid") == "github.com"
        assert daemon._get_hostname_from_url("") == "github.com"
        assert daemon._get_hostname_from_url("not-a-url") == "github.com"


@pytest.mark.integration
class TestHibernationPagerDutyIntegration:
    """Tests for PagerDuty integration with hibernation state changes."""

    def test_pagerduty_trigger_called_when_entering_hibernation(self, daemon):
        """Test that PagerDuty trigger is called when daemon enters hibernation."""
        with patch("src.daemon.trigger_hibernation_alert") as mock_trigger:
            daemon._enter_hibernation("GitHub API unreachable")

            mock_trigger.assert_called_once_with(
                "GitHub API unreachable",
                daemon.config.project_urls,
            )

    def test_pagerduty_resolve_called_when_exiting_hibernation(self, daemon):
        """Test that PagerDuty resolve is called when daemon exits hibernation."""
        daemon._hibernating = True

        with patch("src.daemon.resolve_hibernation_alert") as mock_resolve:
            daemon._exit_hibernation()

            mock_resolve.assert_called_once()

    def test_pagerduty_trigger_not_called_when_already_hibernating(self, daemon):
        """Test that PagerDuty trigger is not called when already hibernating."""
        daemon._hibernating = True

        with patch("src.daemon.trigger_hibernation_alert") as mock_trigger:
            daemon._enter_hibernation("Another reason")

            mock_trigger.assert_not_called()

    def test_pagerduty_resolve_not_called_when_not_hibernating(self, daemon):
        """Test that PagerDuty resolve is not called when not hibernating."""
        daemon._hibernating = False

        with patch("src.daemon.resolve_hibernation_alert") as mock_resolve:
            daemon._exit_hibernation()

            mock_resolve.assert_not_called()

    def test_daemon_continues_when_pagerduty_trigger_fails(self, daemon):
        """Test that daemon continues normally when PagerDuty trigger fails."""
        with patch("src.daemon.trigger_hibernation_alert") as mock_trigger:
            mock_trigger.return_value = False  # Simulate failure

            # Should not raise exception and should set hibernation flag
            daemon._enter_hibernation("GitHub API unreachable")

            assert daemon._hibernating is True
            mock_trigger.assert_called_once()

    def test_daemon_continues_when_pagerduty_resolve_fails(self, daemon):
        """Test that daemon continues normally when PagerDuty resolve fails."""
        daemon._hibernating = True

        with patch("src.daemon.resolve_hibernation_alert") as mock_resolve:
            mock_resolve.return_value = False  # Simulate failure

            # Should not raise exception and should clear hibernation flag
            daemon._exit_hibernation()

            assert daemon._hibernating is False
            mock_resolve.assert_called_once()

    def test_pagerduty_trigger_receives_project_urls(self, daemon):
        """Test that PagerDuty trigger receives correct project URLs."""
        daemon.config.project_urls = [
            "https://github.com/orgs/test/projects/1",
            "https://github.com/orgs/test/projects/2",
            "https://ghes.company.com/orgs/corp/projects/3",
        ]

        with patch("src.daemon.trigger_hibernation_alert") as mock_trigger:
            daemon._enter_hibernation("Network error")

            mock_trigger.assert_called_once_with(
                "Network error",
                [
                    "https://github.com/orgs/test/projects/1",
                    "https://github.com/orgs/test/projects/2",
                    "https://ghes.company.com/orgs/corp/projects/3",
                ],
            )

    def test_pagerduty_integration_in_main_loop_hibernation(self, daemon):
        """Test PagerDuty is called correctly during main loop hibernation cycle."""
        call_count = [0]

        def mock_connectivity_check():
            call_count[0] += 1
            if call_count[0] == 1:
                return False  # First check fails - enter hibernation
            daemon._shutdown_requested = True
            return True  # Second check succeeds - exit hibernation

        def mock_wait(timeout=None):
            return False

        with (
            patch.object(daemon, "_check_github_connectivity", side_effect=mock_connectivity_check),
            patch.object(daemon, "_poll"),
            patch.object(daemon, "_initialize_project_metadata"),
            patch.object(daemon._shutdown_event, "wait", mock_wait),
            patch("src.daemon.trigger_hibernation_alert") as mock_trigger,
            patch("src.daemon.resolve_hibernation_alert") as mock_resolve,
        ):
            daemon.run()

            # Should have triggered alert when entering hibernation
            mock_trigger.assert_called_once()
            # Should have resolved alert when exiting hibernation
            mock_resolve.assert_called_once()

    def test_pagerduty_not_triggered_during_normal_operation(self, daemon):
        """Test PagerDuty is not triggered during normal (non-hibernation) operation."""
        poll_count = [0]

        def mock_poll():
            poll_count[0] += 1
            if poll_count[0] >= 2:
                daemon._shutdown_requested = True

        def mock_wait(timeout=None):
            return False

        with (
            patch.object(daemon, "_check_github_connectivity", return_value=True),
            patch.object(daemon, "_poll", side_effect=mock_poll),
            patch.object(daemon, "_initialize_project_metadata"),
            patch.object(daemon._shutdown_event, "wait", mock_wait),
            patch("src.daemon.trigger_hibernation_alert") as mock_trigger,
            patch("src.daemon.resolve_hibernation_alert") as mock_resolve,
        ):
            daemon.run()

            # Should not have called PagerDuty during normal operation
            mock_trigger.assert_not_called()
            mock_resolve.assert_not_called()
