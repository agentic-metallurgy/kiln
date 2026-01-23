"""Integration tests for Daemon core behavior.

These tests verify daemon core functionality like exponential backoff,
while mocking external dependencies.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.daemon import Daemon


@pytest.mark.integration
class TestDaemonBackoff:
    """Tests for daemon exponential backoff behavior using tenacity."""

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

        with patch("src.ticket_clients.github.GitHubTicketClient"):
            daemon = Daemon(config)
            daemon.ticket_client = MagicMock()
            # Also update the ticket_client reference in comment_processor
            daemon.comment_processor.ticket_client = daemon.ticket_client
            yield daemon
            daemon.stop()

    def test_backoff_increases_on_consecutive_failures(self, daemon):
        """Test that backoff increases exponentially on failures using tenacity."""
        wait_timeouts = []

        # Mock Event.wait to track timeout values and return False (not interrupted)
        def mock_wait(timeout=None):
            wait_timeouts.append(timeout)
            return False  # Not interrupted

        # Fail twice then request shutdown on the second failure
        call_count = [0]

        def mock_poll():
            call_count[0] += 1
            if call_count[0] >= 2:
                daemon._shutdown_requested = True
            raise Exception("Simulated failure")

        with (
            patch.object(daemon, "_poll", side_effect=mock_poll),
            patch.object(daemon, "_initialize_project_metadata"),
            patch.object(daemon._shutdown_event, "wait", mock_wait),
        ):
            daemon.run()

        # First failure: 2^1 = 2 seconds backoff
        # Second failure: 2^2 = 4 seconds backoff (then shutdown detected on loop check)
        # Uses Event.wait with the full timeout (not 1-second loops)
        assert wait_timeouts == [2.0, 4.0]

    def test_backoff_resets_on_success(self, daemon):
        """Test that consecutive failure count resets after successful poll."""
        wait_timeouts = []

        def mock_wait(timeout=None):
            wait_timeouts.append(timeout)
            return False  # Not interrupted

        # Fail once, succeed, fail once, then shutdown on the third failure
        call_count = [0]

        def mock_poll():
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("First failure")
            elif call_count[0] == 2:
                pass  # Success
            elif call_count[0] == 3:
                daemon._shutdown_requested = True
                raise Exception("Third call failure triggers shutdown")

        with (
            patch.object(daemon, "_poll", side_effect=mock_poll),
            patch.object(daemon, "_initialize_project_metadata"),
            patch.object(daemon._shutdown_event, "wait", mock_wait),
        ):
            daemon.run()

        # First failure: 2s backoff (consecutive_failures=1)
        # Success: 60s poll interval wait (consecutive_failures reset to 0)
        # Third failure: 2s backoff (consecutive_failures=1, reset after success)
        assert wait_timeouts == [2.0, 60, 2.0]

    def test_backoff_caps_at_maximum(self, daemon):
        """Test that backoff caps at 300 seconds using tenacity."""
        wait_timeouts = []

        call_count = [0]

        def mock_poll():
            call_count[0] += 1
            # Shutdown on the 10th call to get exactly 10 backoffs
            if call_count[0] >= 10:
                daemon._shutdown_requested = True
            raise Exception("Simulated failure")

        def mock_wait(timeout=None):
            wait_timeouts.append(timeout)
            return False  # Not interrupted

        with (
            patch.object(daemon, "_poll", side_effect=mock_poll),
            patch.object(daemon, "_initialize_project_metadata"),
            patch.object(daemon._shutdown_event, "wait", mock_wait),
        ):
            daemon.run()

        # Expected backoffs: 2, 4, 8, 16, 32, 64, 128, 256, 300, 300
        # (2^1 through 2^8=256, then capped at 300 by tenacity for 2^9=512 and beyond)
        expected = [2.0, 4.0, 8.0, 16.0, 32.0, 64.0, 128.0, 256.0, 300.0, 300.0]
        assert wait_timeouts == expected

    def test_backoff_interruptible_for_shutdown(self, daemon):
        """Test that backoff sleep is interruptible during shutdown via Event."""
        wait_count = [0]

        def mock_poll():
            raise Exception("Always fail")

        def mock_wait(timeout=None):
            wait_count[0] += 1
            # Return True on first wait to indicate shutdown was signaled
            return True

        with (
            patch.object(daemon, "_poll", side_effect=mock_poll),
            patch.object(daemon, "_initialize_project_metadata"),
            patch.object(daemon._shutdown_event, "wait", mock_wait),
        ):
            daemon.run()

        # Should have only 1 wait call before shutdown was detected
        assert wait_count[0] == 1
