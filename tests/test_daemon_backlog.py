"""Unit tests for Daemon _maybe_set_backlog() functionality.

These tests verify that the daemon correctly:
- Sets items with "Unknown" status to "Backlog"
- Preserves items with valid statuses (e.g., "Research")
- Preserves items with custom statuses (e.g., "Future Ideas")
- Skips closed issues even if they have "Unknown" status
"""

from unittest.mock import MagicMock, patch

import pytest

from src.daemon import Daemon
from src.interfaces.ticket import TicketItem


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
    config.username_self = "test-bot"

    with patch("src.ticket_clients.github.GitHubTicketClient"):
        daemon = Daemon(config)
        daemon.ticket_client = MagicMock()
        daemon.runner = MagicMock()
        yield daemon
        daemon.stop()


def make_ticket_item(
    status: str = "Unknown",
    state: str = "OPEN",
    ticket_id: int = 42,
) -> TicketItem:
    """Helper to create a TicketItem for testing."""
    return TicketItem(
        item_id="PVTI_item123",
        board_url="https://github.com/orgs/test-org/projects/1",
        ticket_id=ticket_id,
        repo="github.com/test-org/test-repo",
        status=status,
        title="Test Issue",
        labels=set(),
        state=state,
        state_reason=None,
        has_merged_changes=False,
        comment_count=0,
    )


@pytest.mark.unit
class TestMaybeSetBacklog:
    """Tests for _maybe_set_backlog method."""

    def test_unknown_status_gets_set_to_backlog(self, daemon):
        """Test that an item with 'Unknown' status gets set to 'Backlog'."""
        item = make_ticket_item(status="Unknown", state="OPEN")

        daemon._maybe_set_backlog(item)

        daemon.ticket_client.update_item_status.assert_called_once_with(
            "PVTI_item123", "Backlog", hostname="github.com"
        )

    def test_valid_status_is_not_modified(self, daemon):
        """Test that an item with a valid status (e.g., 'Research') is not modified."""
        item = make_ticket_item(status="Research", state="OPEN")

        daemon._maybe_set_backlog(item)

        daemon.ticket_client.update_item_status.assert_not_called()

    def test_closed_issue_with_unknown_status_is_not_modified(self, daemon):
        """Test that a closed issue with 'Unknown' status is not modified."""
        item = make_ticket_item(status="Unknown", state="CLOSED")

        daemon._maybe_set_backlog(item)

        daemon.ticket_client.update_item_status.assert_not_called()

    def test_custom_status_is_not_modified(self, daemon):
        """Test that an item with a custom status (e.g., 'Future Ideas') is not modified."""
        item = make_ticket_item(status="Future Ideas", state="OPEN")

        daemon._maybe_set_backlog(item)

        daemon.ticket_client.update_item_status.assert_not_called()

    def test_backlog_status_is_not_modified(self, daemon):
        """Test that an item already in 'Backlog' is not modified."""
        item = make_ticket_item(status="Backlog", state="OPEN")

        daemon._maybe_set_backlog(item)

        daemon.ticket_client.update_item_status.assert_not_called()

    def test_plan_status_is_not_modified(self, daemon):
        """Test that an item with 'Plan' status is not modified."""
        item = make_ticket_item(status="Plan", state="OPEN")

        daemon._maybe_set_backlog(item)

        daemon.ticket_client.update_item_status.assert_not_called()

    def test_implement_status_is_not_modified(self, daemon):
        """Test that an item with 'Implement' status is not modified."""
        item = make_ticket_item(status="Implement", state="OPEN")

        daemon._maybe_set_backlog(item)

        daemon.ticket_client.update_item_status.assert_not_called()

    def test_validate_status_is_not_modified(self, daemon):
        """Test that an item with 'Validate' status is not modified."""
        item = make_ticket_item(status="Validate", state="OPEN")

        daemon._maybe_set_backlog(item)

        daemon.ticket_client.update_item_status.assert_not_called()

    def test_done_status_is_not_modified(self, daemon):
        """Test that an item with 'Done' status is not modified."""
        item = make_ticket_item(status="Done", state="OPEN")

        daemon._maybe_set_backlog(item)

        daemon.ticket_client.update_item_status.assert_not_called()

    def test_api_error_is_handled_gracefully(self, daemon):
        """Test that API errors during status update are handled gracefully."""
        item = make_ticket_item(status="Unknown", state="OPEN")
        daemon.ticket_client.update_item_status.side_effect = Exception("API Error")

        # Should not raise - errors are logged but don't crash
        daemon._maybe_set_backlog(item)

        daemon.ticket_client.update_item_status.assert_called_once()

    def test_enterprise_hostname_extracted_correctly(self, daemon):
        """Test that the hostname is correctly extracted for enterprise URLs."""
        item = TicketItem(
            item_id="PVTI_item456",
            board_url="https://github.example.com/orgs/enterprise-org/projects/5",
            ticket_id=99,
            repo="github.example.com/enterprise-org/enterprise-repo",
            status="Unknown",
            title="Enterprise Issue",
            labels=set(),
            state="OPEN",
            state_reason=None,
            has_merged_changes=False,
            comment_count=0,
        )

        daemon._maybe_set_backlog(item)

        daemon.ticket_client.update_item_status.assert_called_once_with(
            "PVTI_item456", "Backlog", hostname="github.example.com"
        )
