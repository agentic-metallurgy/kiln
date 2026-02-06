"""Unit tests for Daemon RepoCredentialsManager integration.

These tests verify that the daemon correctly:
- Initializes RepoCredentialsManager at startup
- Calls copy_to_worktree in _process_item_workflow after MCP config write
- Handles credential copy failures without blocking workflow execution
"""

from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from src.daemon import Daemon
from src.integrations.repo_credentials import RepoCredentialsManager
from src.interfaces.ticket import TicketItem


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


@pytest.fixture
def base_config(temp_workspace_dir):
    """Fixture providing a base config for daemon tests."""
    config = MagicMock()
    config.poll_interval = 60
    config.watched_statuses = ["Research", "Plan", "Implement"]
    config.max_concurrent_workflows = 2
    config.database_path = f"{temp_workspace_dir}/test.db"
    config.workspace_dir = temp_workspace_dir
    config.project_urls = ["https://github.com/orgs/test/projects/1"]
    config.stage_models = {}
    config.github_enterprise_version = None
    config.github_enterprise_host = None
    config.github_token = None
    config.github_enterprise_token = None
    config.username_self = "test-bot"
    config.team_usernames = []
    config.ghes_logs_mask = False
    config.claude_code_enable_telemetry = False
    config.azure_tenant_id = None
    config.azure_client_id = None
    config.azure_username = None
    config.azure_password = None
    config.azure_scope = None
    return config


@pytest.fixture
def daemon_for_workflow(temp_workspace_dir):
    """Fixture providing Daemon with mocked dependencies for workflow tests."""
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
    config.ghes_logs_mask = False
    config.github_enterprise_host = None

    with patch("src.ticket_clients.github.GitHubTicketClient"):
        daemon = Daemon(config)
        daemon.ticket_client = MagicMock()
        # Mock get_label_actor to return our username for post-claim verification
        daemon.ticket_client.get_label_actor.return_value = "test-bot"
        daemon.runner = MagicMock()
        daemon.database = MagicMock()
        daemon.database.insert_run_record = MagicMock(return_value=1)
        daemon._run_workflow = MagicMock(return_value="session-123")

        # Create worktree directory so _auto_prepare_worktree is skipped
        worktree_base = Path(temp_workspace_dir) / "worktrees"
        worktree_base.mkdir(parents=True, exist_ok=True)

        yield daemon
        daemon.stop()


@pytest.mark.unit
class TestDaemonRepoCredentialsManagerInitialization:
    """Tests for Daemon RepoCredentialsManager initialization."""

    def test_repo_credentials_manager_initialized(self, base_config):
        """Test that RepoCredentialsManager is always initialized during Daemon.__init__."""
        with (
            patch("src.ticket_clients.github.GitHubTicketClient"),
            patch("src.daemon.MCPConfigManager") as mock_mcp_class,
        ):
            mock_mcp_instance = MagicMock()
            mock_mcp_instance.validate_config.return_value = []
            mock_mcp_instance.has_config.return_value = False
            mock_mcp_class.return_value = mock_mcp_instance

            daemon = Daemon(base_config)

            assert hasattr(daemon, "repo_credentials_manager")
            assert isinstance(daemon.repo_credentials_manager, RepoCredentialsManager)

            daemon.stop()

    def test_repo_credentials_manager_is_separate_from_mcp(self, base_config):
        """Test that RepoCredentialsManager is a distinct component from MCPConfigManager."""
        with (
            patch("src.ticket_clients.github.GitHubTicketClient"),
            patch("src.daemon.MCPConfigManager") as mock_mcp_class,
        ):
            mock_mcp_instance = MagicMock()
            mock_mcp_instance.validate_config.return_value = []
            mock_mcp_instance.has_config.return_value = False
            mock_mcp_class.return_value = mock_mcp_instance

            daemon = Daemon(base_config)

            assert daemon.repo_credentials_manager is not daemon.mcp_config_manager

            daemon.stop()


@pytest.mark.unit
class TestProcessItemWorkflowCredentials:
    """Tests for credential copy in _process_item_workflow."""

    def test_copy_to_worktree_called_when_config_exists(
        self, daemon_for_workflow, temp_workspace_dir
    ):
        """Test that copy_to_worktree is called when credentials config exists."""
        item = make_ticket_item(repo="github.com/test-org/test-repo")

        # Create worktree path
        worktree_path = Path(temp_workspace_dir) / "test-repo-issue-42"
        worktree_path.mkdir(parents=True, exist_ok=True)

        # Mock _ensure_required_labels
        daemon_for_workflow._ensure_required_labels = MagicMock()

        # Mock repo_credentials_manager
        daemon_for_workflow.repo_credentials_manager = MagicMock()
        daemon_for_workflow.repo_credentials_manager.has_config.return_value = True
        daemon_for_workflow.repo_credentials_manager.copy_to_worktree.return_value = (
            "/path/to/worktree/.env"
        )

        daemon_for_workflow._process_item_workflow(item)

        # Verify copy_to_worktree was called with correct args
        daemon_for_workflow.repo_credentials_manager.copy_to_worktree.assert_called_once_with(
            str(worktree_path), "github.com/test-org/test-repo"
        )

    def test_copy_to_worktree_not_called_when_no_config(
        self, daemon_for_workflow, temp_workspace_dir
    ):
        """Test that copy_to_worktree is skipped when no credentials config exists."""
        item = make_ticket_item(repo="github.com/test-org/test-repo")

        # Create worktree path
        worktree_path = Path(temp_workspace_dir) / "test-repo-issue-42"
        worktree_path.mkdir(parents=True, exist_ok=True)

        # Mock _ensure_required_labels
        daemon_for_workflow._ensure_required_labels = MagicMock()

        # Mock repo_credentials_manager with no config
        daemon_for_workflow.repo_credentials_manager = MagicMock()
        daemon_for_workflow.repo_credentials_manager.has_config.return_value = False

        daemon_for_workflow._process_item_workflow(item)

        # Verify copy_to_worktree was NOT called
        daemon_for_workflow.repo_credentials_manager.copy_to_worktree.assert_not_called()

    def test_credential_copy_happens_after_mcp_config_write(
        self, daemon_for_workflow, temp_workspace_dir
    ):
        """Test that credential copy occurs after MCP config write in workflow execution."""
        item = make_ticket_item(repo="github.com/test-org/test-repo")

        # Create worktree path
        worktree_path = Path(temp_workspace_dir) / "test-repo-issue-42"
        worktree_path.mkdir(parents=True, exist_ok=True)

        daemon_for_workflow._ensure_required_labels = MagicMock()

        call_order = []

        # Track MCP config write
        daemon_for_workflow.mcp_config_manager = MagicMock()
        daemon_for_workflow.mcp_config_manager.has_config.return_value = True

        def track_mcp_write(*args, **kwargs):
            call_order.append("mcp_write")
            return "/path/to/.mcp.kiln.json"

        daemon_for_workflow.mcp_config_manager.write_to_worktree = MagicMock(
            side_effect=track_mcp_write
        )

        # Track credential copy
        daemon_for_workflow.repo_credentials_manager = MagicMock()
        daemon_for_workflow.repo_credentials_manager.has_config.return_value = True

        def track_cred_copy(*args, **kwargs):
            call_order.append("cred_copy")
            return "/path/to/worktree/.env"

        daemon_for_workflow.repo_credentials_manager.copy_to_worktree = MagicMock(
            side_effect=track_cred_copy
        )

        daemon_for_workflow._process_item_workflow(item)

        # Verify MCP write happened before credential copy
        assert "mcp_write" in call_order
        assert "cred_copy" in call_order
        assert call_order.index("mcp_write") < call_order.index("cred_copy")

    def test_credential_copy_success_logged(
        self, daemon_for_workflow, temp_workspace_dir
    ):
        """Test that successful credential copy is logged."""
        item = make_ticket_item(repo="github.com/test-org/test-repo")

        # Create worktree path
        worktree_path = Path(temp_workspace_dir) / "test-repo-issue-42"
        worktree_path.mkdir(parents=True, exist_ok=True)

        daemon_for_workflow._ensure_required_labels = MagicMock()

        daemon_for_workflow.repo_credentials_manager = MagicMock()
        daemon_for_workflow.repo_credentials_manager.has_config.return_value = True
        daemon_for_workflow.repo_credentials_manager.copy_to_worktree.return_value = (
            "/path/to/worktree/.env"
        )

        with patch("src.daemon.logger") as mock_logger:
            daemon_for_workflow._process_item_workflow(item)

            # Verify success was logged
            info_calls = [str(c) for c in mock_logger.info.call_args_list]
            cred_log = next(
                (c for c in info_calls if "Copied credentials" in c), None
            )
            assert cred_log is not None, "Credential copy success should be logged"

    def test_no_log_when_copy_returns_none(
        self, daemon_for_workflow, temp_workspace_dir
    ):
        """Test that no credential log is emitted when copy_to_worktree returns None."""
        item = make_ticket_item(repo="github.com/test-org/test-repo")

        # Create worktree path
        worktree_path = Path(temp_workspace_dir) / "test-repo-issue-42"
        worktree_path.mkdir(parents=True, exist_ok=True)

        daemon_for_workflow._ensure_required_labels = MagicMock()

        daemon_for_workflow.repo_credentials_manager = MagicMock()
        daemon_for_workflow.repo_credentials_manager.has_config.return_value = True
        daemon_for_workflow.repo_credentials_manager.copy_to_worktree.return_value = None

        with patch("src.daemon.logger") as mock_logger:
            daemon_for_workflow._process_item_workflow(item)

            # Verify "Copied credentials" was NOT logged
            info_calls = [str(c) for c in mock_logger.info.call_args_list]
            cred_log = next(
                (c for c in info_calls if "Copied credentials" in c), None
            )
            assert cred_log is None, "No credential log should be emitted when copy returns None"


@pytest.mark.unit
class TestCredentialCopyFailureHandling:
    """Tests for credential copy failure handling in _process_item_workflow."""

    def test_credential_copy_failure_does_not_block_workflow(
        self, daemon_for_workflow, temp_workspace_dir
    ):
        """Test that credential copy failure doesn't prevent workflow from running."""
        item = make_ticket_item(repo="github.com/test-org/test-repo")

        # Create worktree path
        worktree_path = Path(temp_workspace_dir) / "test-repo-issue-42"
        worktree_path.mkdir(parents=True, exist_ok=True)

        daemon_for_workflow._ensure_required_labels = MagicMock()

        # Make credential copy raise an exception
        daemon_for_workflow.repo_credentials_manager = MagicMock()
        daemon_for_workflow.repo_credentials_manager.has_config.return_value = True
        daemon_for_workflow.repo_credentials_manager.copy_to_worktree.side_effect = (
            Exception("Permission denied")
        )

        # Workflow should complete despite credential copy failure
        daemon_for_workflow._process_item_workflow(item)

        # Verify _run_workflow was still called
        daemon_for_workflow._run_workflow.assert_called_once()

    def test_credential_copy_failure_logged_as_warning(
        self, daemon_for_workflow, temp_workspace_dir
    ):
        """Test that credential copy failures are logged as warnings."""
        item = make_ticket_item(repo="github.com/test-org/test-repo")

        # Create worktree path
        worktree_path = Path(temp_workspace_dir) / "test-repo-issue-42"
        worktree_path.mkdir(parents=True, exist_ok=True)

        daemon_for_workflow._ensure_required_labels = MagicMock()

        # Make credential copy raise an exception
        daemon_for_workflow.repo_credentials_manager = MagicMock()
        daemon_for_workflow.repo_credentials_manager.has_config.return_value = True
        daemon_for_workflow.repo_credentials_manager.copy_to_worktree.side_effect = (
            Exception("Permission denied")
        )

        with patch("src.daemon.logger") as mock_logger:
            daemon_for_workflow._process_item_workflow(item)

            # Verify failure was logged as warning
            warning_calls = [str(c) for c in mock_logger.warning.call_args_list]
            cred_warning = next(
                (c for c in warning_calls if "Failed to copy credentials" in c), None
            )
            assert cred_warning is not None, (
                "Credential copy failure should be logged as warning"
            )
            assert "Permission denied" in cred_warning

    def test_credential_copy_os_error_does_not_block_workflow(
        self, daemon_for_workflow, temp_workspace_dir
    ):
        """Test that OSError during credential copy doesn't block workflow."""
        item = make_ticket_item(repo="github.com/test-org/test-repo")

        # Create worktree path
        worktree_path = Path(temp_workspace_dir) / "test-repo-issue-42"
        worktree_path.mkdir(parents=True, exist_ok=True)

        daemon_for_workflow._ensure_required_labels = MagicMock()

        # Make credential copy raise an OSError
        daemon_for_workflow.repo_credentials_manager = MagicMock()
        daemon_for_workflow.repo_credentials_manager.has_config.return_value = True
        daemon_for_workflow.repo_credentials_manager.copy_to_worktree.side_effect = (
            OSError("No such file or directory")
        )

        # Workflow should complete despite credential copy failure
        daemon_for_workflow._process_item_workflow(item)

        # Verify _run_workflow was still called
        daemon_for_workflow._run_workflow.assert_called_once()
