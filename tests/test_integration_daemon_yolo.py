"""Integration tests for Daemon YOLO label functionality.

Tests for YOLO label removal stopping automatic progression.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.daemon import Daemon
from src.interfaces import TicketItem


@pytest.mark.integration
class TestDaemonYoloLabelRemoval:
    """Tests for YOLO label removal stopping automatic progression."""

    @pytest.fixture
    def daemon(self, temp_workspace_dir):
        """Create a daemon instance for testing."""
        config = MagicMock()
        config.poll_interval = 60
        config.watched_statuses = ["Research", "Plan", "Implement"]
        config.max_concurrent_workflows = 2
        config.database_path = f"{temp_workspace_dir}/test.db"
        config.workspace_dir = temp_workspace_dir
        config.project_urls = ["https://github.com/orgs/test/projects/1"]
        config.stage_models = {}
        config.github_enterprise_version = None
        config.username_self = "test-user"

        with patch("src.ticket_clients.github.GitHubTicketClient"):
            daemon = Daemon(config)
            daemon.ticket_client = MagicMock()
            yield daemon
            daemon.stop()

    def test_has_yolo_label_returns_true_when_present(self, daemon):
        """Test _has_yolo_label returns True when yolo label is present."""
        daemon.ticket_client.get_ticket_labels.return_value = {"yolo", "bug", "enhancement"}

        result = daemon._has_yolo_label("github.com/owner/repo", 42)

        assert result is True
        daemon.ticket_client.get_ticket_labels.assert_called_once_with("github.com/owner/repo", 42)

    def test_has_yolo_label_returns_false_when_absent(self, daemon):
        """Test _has_yolo_label returns False when yolo label is not present."""
        daemon.ticket_client.get_ticket_labels.return_value = {"bug", "enhancement"}

        result = daemon._has_yolo_label("github.com/owner/repo", 42)

        assert result is False

    def test_has_yolo_label_returns_false_on_api_error(self, daemon):
        """Test _has_yolo_label returns False (fail-safe) on API errors."""
        daemon.ticket_client.get_ticket_labels.side_effect = Exception("API error")

        result = daemon._has_yolo_label("github.com/owner/repo", 42)

        assert result is False

    def test_should_yolo_advance_returns_false_when_label_removed(self, daemon):
        """Test _should_yolo_advance returns False when yolo label was removed."""
        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            title="Test Issue",
            repo="github.com/owner/repo",
            status="Research",
            labels={"yolo", "research_ready"},  # Cached labels still have yolo
        )

        # Fresh check shows yolo was removed
        daemon.ticket_client.get_ticket_labels.return_value = {"research_ready"}

        result = daemon._should_yolo_advance(item)

        assert result is False
        daemon.ticket_client.get_ticket_labels.assert_called_once()

    def test_should_yolo_advance_returns_true_when_label_still_present(self, daemon):
        """Test _should_yolo_advance returns True when yolo label is still present."""
        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            title="Test Issue",
            repo="github.com/owner/repo",
            status="Research",
            labels={"yolo", "research_ready"},
        )

        # Fresh check shows yolo is still present
        daemon.ticket_client.get_ticket_labels.return_value = {"yolo", "research_ready"}

        result = daemon._should_yolo_advance(item)

        assert result is True

    def test_yolo_advance_skips_when_label_removed(self, daemon):
        """Test _yolo_advance does not advance when yolo label was removed."""
        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            title="Test Issue",
            repo="github.com/owner/repo",
            status="Research",
            labels={"yolo", "research_ready"},
        )

        # Fresh check shows yolo was removed
        daemon.ticket_client.get_ticket_labels.return_value = {"research_ready"}

        daemon._yolo_advance(item)

        # Should not update status
        daemon.ticket_client.update_item_status.assert_not_called()

    def test_yolo_advance_proceeds_when_label_present(self, daemon):
        """Test _yolo_advance proceeds when yolo label is still present."""
        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            title="Test Issue",
            repo="github.com/owner/repo",
            status="Research",
            labels={"yolo", "research_ready"},
        )

        # Fresh check shows yolo is still present
        daemon.ticket_client.get_ticket_labels.return_value = {"yolo", "research_ready"}
        daemon.ticket_client.get_label_actor.return_value = "test-user"

        daemon._yolo_advance(item)

        # Should update status
        daemon.ticket_client.update_item_status.assert_called_once_with(
            "PVI_123", "Plan", hostname="github.com"
        )


@pytest.mark.integration
class TestDaemonWorkflowTriggerLogging:
    """Tests for _should_trigger_workflow logging behavior.

    These tests verify that team member workflow blocks are logged at DEBUG level
    (not WARNING) while blocked/unknown actors are logged at WARNING level.
    """

    @pytest.fixture
    def daemon(self, temp_workspace_dir):
        """Create a daemon instance for testing."""
        config = MagicMock()
        config.poll_interval = 60
        config.watched_statuses = ["Research", "Plan", "Implement"]
        config.max_concurrent_workflows = 2
        config.database_path = f"{temp_workspace_dir}/test.db"
        config.workspace_dir = temp_workspace_dir
        config.project_urls = ["https://github.com/orgs/test/projects/1"]
        config.stage_models = {}
        config.github_enterprise_version = None
        config.username_self = "test-user"
        config.team_usernames = ["teammate1", "teammate2"]

        with patch("src.ticket_clients.github.GitHubTicketClient"):
            daemon = Daemon(config)
            daemon.ticket_client = MagicMock()
            daemon.ticket_client.supports_status_actor_check = True
            yield daemon
            daemon.stop()

    def test_team_member_workflow_block_logged_at_debug(self, daemon, caplog):
        """Test that team member workflow blocks are logged at DEBUG level."""
        import logging

        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            title="Test Issue",
            repo="github.com/owner/repo",
            status="Research",
            labels=set(),
        )

        # Team member was the last to change status
        daemon.ticket_client.get_last_status_actor.return_value = "teammate1"

        with caplog.at_level(logging.DEBUG):
            result = daemon._should_trigger_workflow(item)

        assert result is False
        # Verify DEBUG log was emitted (not WARNING)
        assert "Workflow trigger skipped" in caplog.text
        assert "team member" in caplog.text
        assert "teammate1" in caplog.text

    def test_team_member_workflow_block_no_warning(self, daemon, caplog):
        """Test that team member workflow blocks do NOT produce WARNING logs."""
        import logging

        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            title="Test Issue",
            repo="github.com/owner/repo",
            status="Research",
            labels=set(),
        )

        # Team member was the last to change status
        daemon.ticket_client.get_last_status_actor.return_value = "teammate1"

        with caplog.at_level(logging.WARNING):
            daemon._should_trigger_workflow(item)

        # No WARNING logs should be emitted for team members
        assert "BLOCKED" not in caplog.text
        assert "not allowed" not in caplog.text

    def test_blocked_actor_workflow_block_logged_at_warning(self, daemon, caplog):
        """Test that blocked actor workflow blocks are logged at WARNING level."""
        import logging

        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            title="Test Issue",
            repo="github.com/owner/repo",
            status="Research",
            labels=set(),
        )

        # Unknown user was the last to change status
        daemon.ticket_client.get_last_status_actor.return_value = "unknown-user"

        with caplog.at_level(logging.WARNING):
            result = daemon._should_trigger_workflow(item)

        assert result is False
        # Verify WARNING log was emitted with BLOCKED
        assert "BLOCKED" in caplog.text
        assert "unknown-user" in caplog.text

    def test_self_actor_workflow_trigger_allowed(self, daemon, caplog):
        """Test that self actor can trigger workflows."""
        import logging

        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            title="Test Issue",
            repo="github.com/owner/repo",
            status="Research",
            labels=set(),
        )

        # Self was the last to change status
        daemon.ticket_client.get_last_status_actor.return_value = "test-user"

        with caplog.at_level(logging.INFO):
            result = daemon._should_trigger_workflow(item)

        assert result is True
        # Verify INFO log was emitted
        assert "Workflow trigger" in caplog.text
        assert "test-user" in caplog.text
