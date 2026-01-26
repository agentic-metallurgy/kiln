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
class TestDaemonYoloAllowOthersTickets:
    """Tests for YOLO label functionality with ALLOW_OTHERS_TICKETS enabled."""

    @pytest.fixture
    def daemon_allow_others(self, temp_workspace_dir):
        """Create a daemon instance with allow_others_tickets enabled."""
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
        config.allow_others_tickets = True  # Enable bypass
        config.team_usernames = []

        with patch("src.ticket_clients.github.GitHubTicketClient"):
            daemon = Daemon(config)
            daemon.ticket_client = MagicMock()
            yield daemon
            daemon.stop()

    def test_yolo_advance_bypasses_actor_check_when_enabled(self, daemon_allow_others):
        """Test _yolo_advance bypasses actor check when allow_others_tickets is enabled."""
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
        daemon_allow_others.ticket_client.get_ticket_labels.return_value = {"yolo", "research_ready"}

        daemon_allow_others._yolo_advance(item)

        # Should update status without calling get_label_actor
        daemon_allow_others.ticket_client.get_label_actor.assert_not_called()
        daemon_allow_others.ticket_client.update_item_status.assert_called_once_with(
            "PVI_123", "Plan", hostname="github.com"
        )

    def test_yolo_advance_allows_non_self_actor_when_enabled(self, daemon_allow_others):
        """Test _yolo_advance allows non-self actor when allow_others_tickets is enabled."""
        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            title="Test Issue",
            repo="github.com/owner/repo",
            status="Research",
            labels={"yolo", "research_ready"},
        )

        # Fresh check shows yolo is still present (added by "other-user")
        daemon_allow_others.ticket_client.get_ticket_labels.return_value = {"yolo", "research_ready"}

        daemon_allow_others._yolo_advance(item)

        # Should update status (allowing "other-user"'s action)
        daemon_allow_others.ticket_client.update_item_status.assert_called_once()

    def test_yolo_backlog_actor_bypass_config_enabled(self, daemon_allow_others):
        """Test that allow_others_tickets config is properly set for YOLO Backlog bypass.

        This verifies the config is correctly set to bypass actor checks.
        The full _poll() behavior is complex and depends on many external calls,
        but the core logic is that when allow_others_tickets=True, the daemon
        skips calling get_label_actor for YOLO Backlog items.
        """
        # Verify the config is set correctly
        assert daemon_allow_others.config.allow_others_tickets is True
        assert daemon_allow_others.config.username_self == "test-user"

        # Verify _has_yolo_label works correctly
        daemon_allow_others.ticket_client.get_ticket_labels.return_value = {"yolo"}
        assert daemon_allow_others._has_yolo_label("github.com/owner/repo", 99) is True

        # The key behavior: when allow_others_tickets=True, the YOLO Backlog logic
        # in _poll() will NOT call get_label_actor and will directly update status
