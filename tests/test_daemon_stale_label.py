"""Unit tests for Daemon stale label detection functionality.

These tests verify the stale label detection behavior in _should_trigger_workflow:
- Stale running labels are removed when no subprocess exists
- Workflow proceeds after stale label removal
- Active subprocess still blocks workflow (label is not stale)
- _running_labels tracking dict is cleaned up with stale labels
"""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from src.daemon import Daemon
from src.interfaces import TicketItem
from src.labels import Labels


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
    config.github_enterprise_version = None
    config.username_self = "kiln-bot"
    config.team_usernames = []

    with patch("src.ticket_clients.github.GitHubTicketClient"):
        daemon = Daemon(config)
        daemon.ticket_client = MagicMock()
        daemon.ticket_client.supports_status_actor_check = True
        daemon.comment_processor.ticket_client = daemon.ticket_client
        yield daemon
        daemon.stop()


@pytest.fixture
def mock_process():
    """Fixture providing a mock subprocess.Popen object."""
    process = MagicMock(spec=subprocess.Popen)
    process.pid = 12345
    return process


def _create_ticket_item(
    repo: str = "test-org/test-repo",
    ticket_id: int = 123,
    status: str = "Implement",
    labels: set[str] | None = None,
) -> TicketItem:
    """Helper to create a TicketItem for testing."""
    return TicketItem(
        item_id="PVTI_test123",
        repo=repo,
        ticket_id=ticket_id,
        status=status,
        title="Test Issue",
        board_url="https://github.com/orgs/test/projects/1",
        labels=labels or set(),
        state="OPEN",
    )


@pytest.mark.integration
class TestStaleRunningLabelDetection:
    """Tests for stale running label detection in _should_trigger_workflow."""

    def test_stale_label_removed_when_no_subprocess_exists(self, daemon):
        """Test that stale running labels are removed when no subprocess exists."""
        key = "test-org/test-repo#123"

        # Setup: issue with implementing label but no subprocess in _running_processes
        item = _create_ticket_item(labels={Labels.IMPLEMENTING})

        # Ensure no subprocess is registered for this key
        assert key not in daemon._running_processes

        # Mock the ticket_client methods
        daemon.ticket_client.get_last_status_actor.return_value = "kiln-bot"

        with patch("src.daemon.logger") as mock_logger:
            result = daemon._should_trigger_workflow(item)

        # Assert: remove_label was called for the stale label
        daemon.ticket_client.remove_label.assert_called_once_with(
            "test-org/test-repo", 123, Labels.IMPLEMENTING
        )

        # Assert: warning was logged about stale label
        mock_logger.warning.assert_called()
        warning_calls = [str(call) for call in mock_logger.warning.call_args_list]
        assert any("Stale" in call and Labels.IMPLEMENTING in call for call in warning_calls)

        # Assert: workflow is allowed to trigger (returns True)
        assert result is True

    def test_stale_label_cleans_up_running_labels_tracking(self, daemon):
        """Test that _running_labels tracking dict is cleaned up when stale label detected."""
        key = "test-org/test-repo#123"

        # Setup: issue with implementing label and stale entry in _running_labels
        item = _create_ticket_item(labels={Labels.IMPLEMENTING})

        # Add stale entry to _running_labels (simulates label was tracked but subprocess died)
        with daemon._running_labels_lock:
            daemon._running_labels[key] = Labels.IMPLEMENTING

        # Ensure no subprocess is registered for this key
        assert key not in daemon._running_processes

        # Mock the ticket_client methods
        daemon.ticket_client.get_last_status_actor.return_value = "kiln-bot"

        daemon._should_trigger_workflow(item)

        # Assert: _running_labels entry was removed
        with daemon._running_labels_lock:
            assert key not in daemon._running_labels

    def test_workflow_proceeds_after_stale_label_removal(self, daemon):
        """Test that workflow is allowed to trigger after stale label is removed."""
        key = "test-org/test-repo#123"

        # Setup: issue with implementing label but no subprocess
        item = _create_ticket_item(labels={Labels.IMPLEMENTING})

        # Ensure no subprocess is registered
        assert key not in daemon._running_processes

        # Mock the ticket_client methods to allow workflow
        daemon.ticket_client.get_last_status_actor.return_value = "kiln-bot"

        # The method should return True (allow workflow to trigger)
        result = daemon._should_trigger_workflow(item)

        assert result is True

    def test_workflow_skipped_with_active_subprocess(self, daemon, mock_process):
        """Test that workflow is skipped when subprocess is actually running."""
        key = "test-org/test-repo#123"

        # Setup: issue with implementing label AND subprocess in _running_processes
        item = _create_ticket_item(labels={Labels.IMPLEMENTING})

        # Register a subprocess for this key
        daemon.register_process(key, mock_process)

        with patch("src.daemon.logger") as mock_logger:
            result = daemon._should_trigger_workflow(item)

        # Assert: label was NOT removed (subprocess is running)
        daemon.ticket_client.remove_label.assert_not_called()

        # Assert: info log about workflow already running
        mock_logger.info.assert_called()
        info_calls = [str(call) for call in mock_logger.info.call_args_list]
        assert any("actually running" in call for call in info_calls)

        # Assert: workflow is skipped (returns False)
        assert result is False

    def test_stale_label_detection_for_research_workflow(self, daemon):
        """Test stale label detection works for research workflow."""
        key = "test-org/test-repo#456"

        # Setup: issue with researching label but no subprocess
        item = _create_ticket_item(
            ticket_id=456,
            status="Research",
            labels={Labels.RESEARCHING},
        )

        # Ensure no subprocess is registered
        assert key not in daemon._running_processes

        # Mock the ticket_client methods
        daemon.ticket_client.get_last_status_actor.return_value = "kiln-bot"

        result = daemon._should_trigger_workflow(item)

        # Assert: stale label was removed
        daemon.ticket_client.remove_label.assert_called_once_with(
            "test-org/test-repo", 456, Labels.RESEARCHING
        )

        # Assert: workflow can proceed
        assert result is True

    def test_stale_label_detection_for_plan_workflow(self, daemon):
        """Test stale label detection works for plan workflow."""
        key = "test-org/test-repo#789"

        # Setup: issue with planning label but no subprocess
        item = _create_ticket_item(
            ticket_id=789,
            status="Plan",
            labels={Labels.PLANNING},
        )

        # Ensure no subprocess is registered
        assert key not in daemon._running_processes

        # Mock the ticket_client methods
        daemon.ticket_client.get_last_status_actor.return_value = "kiln-bot"

        result = daemon._should_trigger_workflow(item)

        # Assert: stale label was removed
        daemon.ticket_client.remove_label.assert_called_once_with(
            "test-org/test-repo", 789, Labels.PLANNING
        )

        # Assert: workflow can proceed
        assert result is True


@pytest.mark.integration
class TestStaleLabelsEdgeCases:
    """Edge case tests for stale label handling."""

    def test_no_stale_detection_when_no_running_label(self, daemon):
        """Test that _should_trigger_workflow proceeds normally without running label."""
        key = "test-org/test-repo#123"

        # Setup: issue without any running label
        item = _create_ticket_item(labels=set())

        # Mock the ticket_client methods
        daemon.ticket_client.get_last_status_actor.return_value = "kiln-bot"

        result = daemon._should_trigger_workflow(item)

        # Assert: remove_label was NOT called (no stale label to remove)
        daemon.ticket_client.remove_label.assert_not_called()

        # Assert: workflow can proceed
        assert result is True

    def test_closed_issue_skipped_before_stale_check(self, daemon):
        """Test that closed issues are skipped before stale label check."""
        # Setup: closed issue with stale implementing label
        item = _create_ticket_item(labels={Labels.IMPLEMENTING})
        item.state = "CLOSED"

        result = daemon._should_trigger_workflow(item)

        # Assert: remove_label was NOT called (closed issue skipped first)
        daemon.ticket_client.remove_label.assert_not_called()

        # Assert: workflow not triggered
        assert result is False

    def test_complete_label_blocks_after_stale_removal(self, daemon):
        """Test that complete label still blocks workflow even after stale label removal."""
        key = "test-org/test-repo#123"

        # Setup: issue with both implementing (stale) and implementation complete labels
        # Note: In practice, plan_ready is the complete label for Plan status
        # For Implement status, there's no complete_label (it's None)
        # So let's test with Research which has research_ready as complete_label
        item = _create_ticket_item(
            status="Research",
            labels={Labels.RESEARCHING, Labels.RESEARCH_READY},
        )

        # Ensure no subprocess
        assert key not in daemon._running_processes

        # Mock the ticket_client methods
        daemon.ticket_client.get_last_status_actor.return_value = "kiln-bot"

        result = daemon._should_trigger_workflow(item)

        # Stale label is removed first
        daemon.ticket_client.remove_label.assert_called_once_with(
            "test-org/test-repo", 123, Labels.RESEARCHING
        )

        # But then complete_label blocks the workflow
        assert result is False
