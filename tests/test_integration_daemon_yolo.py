"""Integration tests for YOLO label functionality.

Tests for YOLO label removal stopping automatic progression.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.daemon import Daemon
from src.interfaces import TicketItem
from src.yolo_controller import YoloController


# Workflow config for testing (matches Daemon.WORKFLOW_CONFIG structure)
WORKFLOW_CONFIG = {
    "Research": {
        "complete_label": "research_ready",
    },
    "Plan": {
        "complete_label": "plan_ready",
    },
    "Implement": {
        "complete_label": None,
    },
}


@pytest.mark.unit
class TestYoloControllerDirect:
    """Tests for YoloController class directly."""

    @pytest.fixture
    def yolo_controller(self):
        """Create a YoloController instance for testing."""
        ticket_client = MagicMock()
        controller = YoloController(
            ticket_client=ticket_client,
            username_self="test-user",
            team_usernames=[],
            workflow_config=WORKFLOW_CONFIG,
        )
        return controller

    def test_has_yolo_label_returns_true_when_present(self, yolo_controller):
        """Test has_yolo_label returns True when yolo label is present."""
        yolo_controller.ticket_client.get_issue_labels.return_value = {"yolo", "bug", "enhancement"}

        result = yolo_controller.has_yolo_label("github.com/owner/repo", 42)

        assert result is True
        yolo_controller.ticket_client.get_issue_labels.assert_called_once_with(
            "github.com/owner/repo", 42
        )

    def test_has_yolo_label_returns_false_when_absent(self, yolo_controller):
        """Test has_yolo_label returns False when yolo label is not present."""
        yolo_controller.ticket_client.get_issue_labels.return_value = {"bug", "enhancement"}

        result = yolo_controller.has_yolo_label("github.com/owner/repo", 42)

        assert result is False

    def test_has_yolo_label_returns_false_on_api_error(self, yolo_controller):
        """Test has_yolo_label returns False (fail-safe) on API errors."""
        yolo_controller.ticket_client.get_issue_labels.side_effect = Exception("API error")

        result = yolo_controller.has_yolo_label("github.com/owner/repo", 42)

        assert result is False

    def test_should_yolo_advance_returns_false_when_label_removed(self, yolo_controller):
        """Test should_yolo_advance returns False when yolo label was removed."""
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
        yolo_controller.ticket_client.get_issue_labels.return_value = {"research_ready"}

        result = yolo_controller.should_yolo_advance(item)

        assert result is False
        yolo_controller.ticket_client.get_issue_labels.assert_called_once()

    def test_should_yolo_advance_returns_true_when_label_still_present(self, yolo_controller):
        """Test should_yolo_advance returns True when yolo label is still present."""
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
        yolo_controller.ticket_client.get_issue_labels.return_value = {"yolo", "research_ready"}

        result = yolo_controller.should_yolo_advance(item)

        assert result is True

    def test_yolo_advance_skips_when_label_removed(self, yolo_controller):
        """Test yolo_advance does not advance when yolo label was removed."""
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
        yolo_controller.ticket_client.get_issue_labels.return_value = {"research_ready"}

        yolo_controller.yolo_advance(item)

        # Should not update status
        yolo_controller.ticket_client.update_item_status.assert_not_called()

    def test_yolo_advance_proceeds_when_label_present(self, yolo_controller):
        """Test yolo_advance proceeds when yolo label is still present."""
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
        yolo_controller.ticket_client.get_issue_labels.return_value = {"yolo", "research_ready"}
        yolo_controller.ticket_client.get_label_actor.return_value = "test-user"

        yolo_controller.yolo_advance(item)

        # Should update status
        yolo_controller.ticket_client.update_item_status.assert_called_once_with(
            "PVI_123", "Plan", hostname="github.com"
        )


@pytest.mark.unit
class TestDaemonYoloLabelRemoval:
    """Tests for YOLO label removal stopping automatic progression via Daemon delegation."""

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
            # Also update the yolo_controller's ticket_client
            daemon.yolo_controller.ticket_client = daemon.ticket_client
            yield daemon
            daemon.stop()

    def test_has_yolo_label_returns_true_when_present(self, daemon):
        """Test _has_yolo_label returns True when yolo label is present."""
        daemon.ticket_client.get_issue_labels.return_value = {"yolo", "bug", "enhancement"}

        result = daemon._has_yolo_label("github.com/owner/repo", 42)

        assert result is True
        daemon.ticket_client.get_issue_labels.assert_called_once_with("github.com/owner/repo", 42)

    def test_has_yolo_label_returns_false_when_absent(self, daemon):
        """Test _has_yolo_label returns False when yolo label is not present."""
        daemon.ticket_client.get_issue_labels.return_value = {"bug", "enhancement"}

        result = daemon._has_yolo_label("github.com/owner/repo", 42)

        assert result is False

    def test_has_yolo_label_returns_false_on_api_error(self, daemon):
        """Test _has_yolo_label returns False (fail-safe) on API errors."""
        daemon.ticket_client.get_issue_labels.side_effect = Exception("API error")

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
        daemon.ticket_client.get_issue_labels.return_value = {"research_ready"}

        result = daemon._should_yolo_advance(item)

        assert result is False
        daemon.ticket_client.get_issue_labels.assert_called_once()

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
        daemon.ticket_client.get_issue_labels.return_value = {"yolo", "research_ready"}

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
        daemon.ticket_client.get_issue_labels.return_value = {"research_ready"}

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
        daemon.ticket_client.get_issue_labels.return_value = {"yolo", "research_ready"}
        daemon.ticket_client.get_label_actor.return_value = "test-user"

        daemon._yolo_advance(item)

        # Should update status
        daemon.ticket_client.update_item_status.assert_called_once_with(
            "PVI_123", "Plan", hostname="github.com"
        )
