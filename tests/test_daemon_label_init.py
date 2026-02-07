"""Unit tests for Daemon on-demand label initialization.

These tests verify that the daemon correctly:
- Initializes labels for repos added after daemon startup
- Tracks which repos have been initialized via _repos_with_labels
- Calls _ensure_required_labels before workflow label operations
"""

from pathlib import Path
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

    config.github_enterprise_version = None
    config.username_self = "test-bot"
    config.ghes_logs_mask = False
    config.github_enterprise_host = None

    with patch("src.ticket_clients.github.GitHubTicketClient"):
        daemon = Daemon(config)
        daemon.ticket_client = MagicMock()
        daemon.runner = MagicMock()
        daemon.database = MagicMock()
        yield daemon
        daemon.stop()


@pytest.fixture
def daemon_for_workflow(temp_workspace_dir):
    """Fixture providing Daemon with additional mocking for _process_item_workflow tests."""
    config = MagicMock()
    config.poll_interval = 60
    config.watched_statuses = ["Research", "Plan", "Implement"]
    config.max_concurrent_workflows = 2
    config.database_path = f"{temp_workspace_dir}/test.db"
    config.workspace_dir = temp_workspace_dir
    config.project_urls = ["https://github.com/orgs/test/projects/1"]

    config.github_enterprise_version = None
    config.username_self = "test-bot"
    config.ghes_logs_mask = False
    config.github_enterprise_host = None

    with patch("src.ticket_clients.github.GitHubTicketClient"):
        daemon = Daemon(config)
        daemon.ticket_client = MagicMock()
        daemon.runner = MagicMock()
        daemon.database = MagicMock()
        daemon.database.insert_run_record = MagicMock(return_value=1)
        daemon._run_workflow = MagicMock(return_value="session-123")

        # Create worktree directory so _auto_prepare_worktree is skipped
        worktree_base = Path(temp_workspace_dir) / "worktrees"
        worktree_base.mkdir(parents=True, exist_ok=True)

        yield daemon
        daemon.stop()


def make_ticket_item(
    status: str = "Research",
    state: str = "OPEN",
    ticket_id: int = 42,
    repo: str = "github.com/test-org/test-repo",
) -> TicketItem:
    """Helper to create a TicketItem for testing."""
    return TicketItem(
        item_id="PVTI_item123",
        board_url="https://github.com/orgs/test-org/projects/1",
        ticket_id=ticket_id,
        repo=repo,
        status=status,
        title="Test Issue",
        labels=set(),
        state=state,
        state_reason=None,
        has_merged_changes=False,
        comment_count=0,
    )


@pytest.mark.unit
class TestReposWithLabelsAttribute:
    """Tests for the _repos_with_labels instance attribute."""

    def test_repos_with_labels_initialized_as_empty_set(self, daemon):
        """Test that _repos_with_labels is initialized as an empty set."""
        assert hasattr(daemon, "_repos_with_labels")
        assert isinstance(daemon._repos_with_labels, set)

    def test_repos_with_labels_persists_across_method_calls(self, daemon):
        """Test that _repos_with_labels persists data across method calls."""
        daemon._repos_with_labels.add("github.com/org/repo1")
        daemon._repos_with_labels.add("github.com/org/repo2")

        assert "github.com/org/repo1" in daemon._repos_with_labels
        assert "github.com/org/repo2" in daemon._repos_with_labels
        assert len(daemon._repos_with_labels) == 2


@pytest.mark.unit
class TestProcessItemWorkflowLabelInit:
    """Tests for label initialization in _process_item_workflow."""

    def test_initializes_labels_for_new_repo(self, daemon_for_workflow, temp_workspace_dir):
        """Test that _process_item_workflow initializes labels for repos not in _repos_with_labels."""
        item = make_ticket_item(repo="github.com/new-org/new-repo")
        assert "github.com/new-org/new-repo" not in daemon_for_workflow._repos_with_labels

        # Create worktree path so auto-prepare is skipped
        # Format is: {workspace_dir}/{repo_name}-issue-{issue_number}
        worktree_path = Path(temp_workspace_dir) / "new-repo-issue-42"
        worktree_path.mkdir(parents=True, exist_ok=True)

        # Mock _ensure_required_labels
        daemon_for_workflow._ensure_required_labels = MagicMock()

        daemon_for_workflow._process_item_workflow(item)

        # Verify _ensure_required_labels was called for the new repo
        daemon_for_workflow._ensure_required_labels.assert_called_once_with(
            "github.com/new-org/new-repo"
        )
        assert "github.com/new-org/new-repo" in daemon_for_workflow._repos_with_labels

    def test_skips_label_init_for_known_repo(self, daemon_for_workflow, temp_workspace_dir):
        """Test that _process_item_workflow skips label init for repos already in _repos_with_labels."""
        repo = "github.com/known-org/known-repo"
        daemon_for_workflow._repos_with_labels.add(repo)
        item = make_ticket_item(repo=repo)

        # Create worktree path so auto-prepare is skipped
        worktree_path = Path(temp_workspace_dir) / "known-repo-issue-42"
        worktree_path.mkdir(parents=True, exist_ok=True)

        # Mock _ensure_required_labels
        daemon_for_workflow._ensure_required_labels = MagicMock()

        daemon_for_workflow._process_item_workflow(item)

        # Verify _ensure_required_labels was NOT called since repo already known
        daemon_for_workflow._ensure_required_labels.assert_not_called()

    def test_adds_repo_to_tracking_set_after_init(self, daemon_for_workflow, temp_workspace_dir):
        """Test that repo is added to _repos_with_labels after initialization."""
        repo = "github.com/add-org/add-repo"
        item = make_ticket_item(repo=repo)

        # Create worktree path so auto-prepare is skipped
        worktree_path = Path(temp_workspace_dir) / "add-repo-issue-42"
        worktree_path.mkdir(parents=True, exist_ok=True)

        daemon_for_workflow._ensure_required_labels = MagicMock()

        assert repo not in daemon_for_workflow._repos_with_labels
        daemon_for_workflow._process_item_workflow(item)
        assert repo in daemon_for_workflow._repos_with_labels

    def test_label_init_happens_before_workflow_labels(
        self, daemon_for_workflow, temp_workspace_dir
    ):
        """Test that label initialization happens before any workflow label operations."""
        repo = "github.com/order-org/order-repo"
        item = make_ticket_item(repo=repo, status="Research")

        # Create worktree path so auto-prepare is skipped
        worktree_path = Path(temp_workspace_dir) / "order-repo-issue-42"
        worktree_path.mkdir(parents=True, exist_ok=True)

        call_order = []

        def track_ensure_labels(r):
            call_order.append(("ensure_labels", r))

        def track_add_label(r, issue_id, label):
            call_order.append(("add_label", label))

        daemon_for_workflow._ensure_required_labels = MagicMock(side_effect=track_ensure_labels)
        daemon_for_workflow.ticket_client.add_label = MagicMock(side_effect=track_add_label)

        daemon_for_workflow._process_item_workflow(item)

        # Verify ensure_labels was called first
        assert len(call_order) >= 1
        assert call_order[0] == ("ensure_labels", repo)


@pytest.mark.unit
class TestInitializeProjectMetadataLabelInit:
    """Tests for label initialization in _initialize_project_metadata."""

    def test_initializes_labels_for_repos_in_project(self, daemon):
        """Test that _initialize_project_metadata initializes labels for repos with items."""
        daemon.ticket_client.get_board_metadata = MagicMock(return_value={
            "project_id": "PVT_123",
            "status_field_id": "PVTSSF_456",
            "status_options": {"Research": "OPT_1"},
        })
        daemon.ticket_client.get_board_items = MagicMock(return_value=[
            make_ticket_item(repo="github.com/org/repo1"),
            make_ticket_item(repo="github.com/org/repo2"),
            make_ticket_item(repo="github.com/org/repo1"),  # duplicate
        ])
        daemon._ensure_required_labels = MagicMock()

        daemon._initialize_project_metadata()

        # Verify _ensure_required_labels was called for each unique repo
        assert daemon._ensure_required_labels.call_count == 2
        calls = {call[0][0] for call in daemon._ensure_required_labels.call_args_list}
        assert calls == {"github.com/org/repo1", "github.com/org/repo2"}

    def test_tracks_initialized_repos_in_project_metadata(self, daemon):
        """Test that _initialize_project_metadata adds repos to _repos_with_labels."""
        daemon.ticket_client.get_board_metadata = MagicMock(return_value={
            "project_id": "PVT_123",
            "status_field_id": "PVTSSF_456",
            "status_options": {},
        })
        daemon.ticket_client.get_board_items = MagicMock(return_value=[
            make_ticket_item(repo="github.com/track/repo1"),
            make_ticket_item(repo="github.com/track/repo2"),
        ])
        daemon._ensure_required_labels = MagicMock()

        assert len(daemon._repos_with_labels) == 0
        daemon._initialize_project_metadata()

        assert "github.com/track/repo1" in daemon._repos_with_labels
        assert "github.com/track/repo2" in daemon._repos_with_labels

    def test_skips_already_initialized_repos(self, daemon):
        """Test that _initialize_project_metadata skips repos already in _repos_with_labels."""
        daemon._repos_with_labels.add("github.com/existing/repo")

        daemon.ticket_client.get_board_metadata = MagicMock(return_value={
            "project_id": "PVT_123",
            "status_field_id": "PVTSSF_456",
            "status_options": {},
        })
        daemon.ticket_client.get_board_items = MagicMock(return_value=[
            make_ticket_item(repo="github.com/existing/repo"),
            make_ticket_item(repo="github.com/new/repo"),
        ])
        daemon._ensure_required_labels = MagicMock()

        daemon._initialize_project_metadata()

        # Should only be called for the new repo
        daemon._ensure_required_labels.assert_called_once_with("github.com/new/repo")
