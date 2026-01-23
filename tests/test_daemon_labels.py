"""Unit tests for idempotent label creation functionality.

These tests verify that:
- _repos_with_labels persists after initialization
- Labels are ensured for new repos during poll
- Labels are not re-ensured for repos already in tracking set
- Daemon starts successfully with empty projects
"""

from unittest.mock import MagicMock, patch

import pytest

from src.daemon import Daemon
from src.interfaces import TicketItem


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
        daemon.hibernation.ticket_client = daemon.ticket_client
        daemon.comment_processor.ticket_client = daemon.ticket_client
        yield daemon
        daemon.stop()


def make_ticket_item(
    repo: str = "owner/repo",
    ticket_id: int = 1,
    status: str = "Backlog",
    state: str = "OPEN",
) -> TicketItem:
    """Helper to create TicketItem instances for testing."""
    return TicketItem(
        item_id=f"PVTI_{ticket_id}",
        board_url="https://github.com/orgs/test/projects/1",
        ticket_id=ticket_id,
        repo=repo,
        status=status,
        title="Test Issue",
        labels=set(),
        state=state,
        comment_count=0,
    )


class TestReposWithLabelsTracking:
    """Tests for _repos_with_labels instance attribute persistence."""

    def test_repos_with_labels_persists_after_init(self, daemon):
        """Test that _repos_with_labels is populated after _initialize_project_metadata."""
        # Setup mock to return items from a repo
        test_repo = "owner/test-repo"
        items = [make_ticket_item(repo=test_repo)]

        daemon.ticket_client.get_board_metadata.return_value = {
            "project_id": "PVT_1",
            "status_field_id": "PVSSF_1",
            "status_options": {"Backlog": "opt_1", "Research": "opt_2"},
        }
        daemon.ticket_client.get_board_items.return_value = items
        daemon.ticket_client.get_repo_labels.return_value = []
        daemon.ticket_client.create_repo_label.return_value = True

        # Clear any prior state
        daemon._repos_with_labels.clear()

        # Call _initialize_project_metadata
        daemon._initialize_project_metadata()

        # Assert _repos_with_labels contains the repo from items
        assert test_repo in daemon._repos_with_labels

    def test_repos_with_labels_is_instance_attribute(self, daemon):
        """Test that _repos_with_labels is an instance attribute (not local variable)."""
        # The attribute should exist on the daemon instance
        assert hasattr(daemon, "_repos_with_labels")
        assert isinstance(daemon._repos_with_labels, set)


class TestLabelsEnsuredDuringPoll:
    """Tests for label initialization during _poll() for new repos."""

    def test_labels_ensured_for_new_repo_during_poll(self, daemon):
        """Test that labels are ensured when new repo appears in poll."""
        # Setup daemon with empty _repos_with_labels
        daemon._repos_with_labels.clear()

        new_repo = "owner/new-repo"
        items = [make_ticket_item(repo=new_repo)]

        daemon.ticket_client.get_board_items.return_value = items
        daemon.ticket_client.get_repo_labels.return_value = []
        daemon.ticket_client.create_repo_label.return_value = True

        # Track if _ensure_required_labels was called
        ensure_labels_calls = []
        original_ensure = daemon._ensure_required_labels

        def track_ensure_labels(repo):
            ensure_labels_calls.append(repo)
            original_ensure(repo)

        with patch.object(daemon, "_ensure_required_labels", side_effect=track_ensure_labels):
            daemon._poll()

        # Assert _ensure_required_labels was called for new repo
        assert new_repo in ensure_labels_calls
        # Assert new repo is now in _repos_with_labels
        assert new_repo in daemon._repos_with_labels

    def test_labels_not_re_ensured_for_known_repo(self, daemon):
        """Test that labels are not re-ensured for repos already in tracking set."""
        known_repo = "owner/known-repo"

        # Setup daemon with repo already in _repos_with_labels
        daemon._repos_with_labels.add(known_repo)

        items = [make_ticket_item(repo=known_repo)]
        daemon.ticket_client.get_board_items.return_value = items

        # Track if _ensure_required_labels was called
        ensure_labels_calls = []

        def track_ensure_labels(repo):
            ensure_labels_calls.append(repo)

        with patch.object(daemon, "_ensure_required_labels", side_effect=track_ensure_labels):
            daemon._poll()

        # Assert _ensure_required_labels was NOT called for known repo
        assert known_repo not in ensure_labels_calls

    def test_labels_ensured_only_once_per_repo_across_polls(self, daemon):
        """Test that multiple polls don't re-initialize labels for same repo."""
        daemon._repos_with_labels.clear()

        test_repo = "owner/multi-poll-repo"
        items = [make_ticket_item(repo=test_repo)]

        daemon.ticket_client.get_board_items.return_value = items
        daemon.ticket_client.get_repo_labels.return_value = []
        daemon.ticket_client.create_repo_label.return_value = True

        ensure_labels_calls = []
        original_ensure = daemon._ensure_required_labels

        def track_ensure_labels(repo):
            ensure_labels_calls.append(repo)
            original_ensure(repo)

        with patch.object(daemon, "_ensure_required_labels", side_effect=track_ensure_labels):
            # First poll - should call _ensure_required_labels
            daemon._poll()
            # Second poll - should NOT call _ensure_required_labels
            daemon._poll()
            # Third poll - should NOT call _ensure_required_labels
            daemon._poll()

        # Assert _ensure_required_labels was called only once for the repo
        assert ensure_labels_calls.count(test_repo) == 1


class TestEmptyProjectStartup:
    """Tests for daemon startup with empty projects."""

    def test_startup_with_empty_project(self, daemon):
        """Test daemon starts successfully with empty project."""
        # Mock get_board_items to return empty list
        daemon.ticket_client.get_board_metadata.return_value = {
            "project_id": "PVT_1",
            "status_field_id": "PVSSF_1",
            "status_options": {"Backlog": "opt_1", "Research": "opt_2"},
        }
        daemon.ticket_client.get_board_items.return_value = []

        # Clear any prior state
        daemon._repos_with_labels.clear()

        # Call _initialize_project_metadata - should not crash
        daemon._initialize_project_metadata()

        # Assert no crash occurred and _repos_with_labels is empty set
        assert daemon._repos_with_labels == set()

    def test_empty_project_metadata_stored(self, daemon):
        """Test that project metadata is stored even for empty projects."""
        project_url = daemon.config.project_urls[0]

        daemon.ticket_client.get_board_metadata.return_value = {
            "project_id": "PVT_1",
            "status_field_id": "PVSSF_1",
            "status_options": {"Backlog": "opt_1", "Research": "opt_2"},
        }
        daemon.ticket_client.get_board_items.return_value = []

        # Call _initialize_project_metadata
        daemon._initialize_project_metadata()

        # Assert metadata was stored for the project
        assert project_url in daemon._project_metadata
        # Empty project should have None as repo
        assert daemon._project_metadata[project_url].repo is None

    def test_labels_ensured_on_first_poll_after_empty_startup(self, daemon):
        """Test that labels are ensured when first item appears after empty startup."""
        # Setup: Initialize with empty project
        daemon.ticket_client.get_board_metadata.return_value = {
            "project_id": "PVT_1",
            "status_field_id": "PVSSF_1",
            "status_options": {"Backlog": "opt_1", "Research": "opt_2"},
        }
        daemon.ticket_client.get_board_items.return_value = []
        daemon._repos_with_labels.clear()
        daemon._initialize_project_metadata()

        # Verify: _repos_with_labels is empty after init with empty project
        assert daemon._repos_with_labels == set()

        # Now simulate first poll with items
        new_repo = "owner/first-repo"
        items = [make_ticket_item(repo=new_repo)]
        daemon.ticket_client.get_board_items.return_value = items
        daemon.ticket_client.get_repo_labels.return_value = []
        daemon.ticket_client.create_repo_label.return_value = True

        ensure_labels_calls = []
        original_ensure = daemon._ensure_required_labels

        def track_ensure_labels(repo):
            ensure_labels_calls.append(repo)
            original_ensure(repo)

        with patch.object(daemon, "_ensure_required_labels", side_effect=track_ensure_labels):
            daemon._poll()

        # Assert labels were ensured for the new repo
        assert new_repo in ensure_labels_calls
        assert new_repo in daemon._repos_with_labels
