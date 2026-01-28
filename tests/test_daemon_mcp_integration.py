"""Unit tests for Daemon MCP (Model Context Protocol) integration.

These tests verify that the daemon correctly:
- Initializes Azure OAuth client when configured
- Initializes MCP config manager at startup
- Writes MCP config to worktrees before workflow execution
- Passes MCP config path to Claude subprocesses via WorkflowRunner
"""

import json
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from src.daemon import Daemon, WorkflowRunner


@pytest.fixture
def config_with_azure():
    """Fixture providing a config with Azure OAuth configured."""
    config = MagicMock()
    config.poll_interval = 60
    config.watched_statuses = ["Research", "Plan", "Implement"]
    config.max_concurrent_workflows = 2
    config.workspace_dir = tempfile.mkdtemp()
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
    # Azure OAuth settings
    config.azure_tenant_id = "test-tenant-id"
    config.azure_client_id = "test-client-id"
    config.azure_username = "test@example.com"
    config.azure_password = "test-password"
    config.azure_scope = "https://api.example.com/.default"
    return config


@pytest.fixture
def config_without_azure():
    """Fixture providing a config without Azure OAuth."""
    config = MagicMock()
    config.poll_interval = 60
    config.watched_statuses = ["Research", "Plan", "Implement"]
    config.max_concurrent_workflows = 2
    config.workspace_dir = tempfile.mkdtemp()
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
    # No Azure OAuth settings
    config.azure_tenant_id = None
    config.azure_client_id = None
    config.azure_username = None
    config.azure_password = None
    config.azure_scope = None
    return config


@pytest.fixture
def temp_mcp_config(tmp_path):
    """Fixture providing a temporary MCP config file."""
    kiln_dir = tmp_path / ".kiln"
    kiln_dir.mkdir()
    mcp_config_path = kiln_dir / "mcp.json"

    config_data = {
        "mcpServers": {
            "test-server": {
                "command": "test-mcp-server",
                "args": ["--port", "8080"],
                "env": {"TOKEN": "${AZURE_BEARER_TOKEN}"}
            }
        }
    }
    mcp_config_path.write_text(json.dumps(config_data))

    return tmp_path


@pytest.mark.unit
class TestDaemonAzureOAuthInitialization:
    """Tests for Daemon Azure OAuth client initialization."""

    def test_azure_oauth_client_initialized_when_configured(self, config_with_azure):
        """Test that Azure OAuth client is created when all fields are configured."""
        with (
            patch("src.ticket_clients.github.GitHubTicketClient"),
            patch("src.daemon.AzureOAuthClient") as mock_oauth_class,
            patch("src.daemon.MCPConfigManager") as mock_mcp_class,
        ):
            mock_mcp_instance = MagicMock()
            mock_mcp_instance.validate_config.return_value = []
            mock_mcp_instance.has_config.return_value = False
            mock_mcp_class.return_value = mock_mcp_instance

            config_with_azure.database_path = f"{config_with_azure.workspace_dir}/test.db"

            daemon = Daemon(config_with_azure)

            # Verify Azure OAuth client was created with correct parameters
            mock_oauth_class.assert_called_once_with(
                tenant_id="test-tenant-id",
                client_id="test-client-id",
                username="test@example.com",
                password="test-password",
                scope="https://api.example.com/.default",
            )

            daemon.stop()

    def test_azure_oauth_client_not_initialized_when_not_configured(self, config_without_azure):
        """Test that Azure OAuth client is None when not configured."""
        with (
            patch("src.ticket_clients.github.GitHubTicketClient"),
            patch("src.daemon.AzureOAuthClient") as mock_oauth_class,
            patch("src.daemon.MCPConfigManager") as mock_mcp_class,
        ):
            mock_mcp_instance = MagicMock()
            mock_mcp_instance.validate_config.return_value = []
            mock_mcp_instance.has_config.return_value = False
            mock_mcp_class.return_value = mock_mcp_instance

            config_without_azure.database_path = f"{config_without_azure.workspace_dir}/test.db"

            daemon = Daemon(config_without_azure)

            # Verify Azure OAuth client was NOT created
            mock_oauth_class.assert_not_called()
            assert daemon.azure_oauth_client is None

            daemon.stop()


@pytest.mark.unit
class TestDaemonMCPConfigManagerInitialization:
    """Tests for Daemon MCP config manager initialization."""

    def test_mcp_config_manager_initialized(self, config_without_azure):
        """Test that MCP config manager is always initialized."""
        with (
            patch("src.ticket_clients.github.GitHubTicketClient"),
            patch("src.daemon.MCPConfigManager") as mock_mcp_class,
        ):
            mock_mcp_instance = MagicMock()
            mock_mcp_instance.validate_config.return_value = []
            mock_mcp_instance.has_config.return_value = False
            mock_mcp_class.return_value = mock_mcp_instance

            config_without_azure.database_path = f"{config_without_azure.workspace_dir}/test.db"

            daemon = Daemon(config_without_azure)

            # Verify MCP config manager was created with azure_client=None
            mock_mcp_class.assert_called_once_with(azure_client=None)
            assert daemon.mcp_config_manager is mock_mcp_instance

            daemon.stop()

    def test_mcp_config_manager_initialized_with_azure_client(self, config_with_azure):
        """Test that MCP config manager receives the Azure OAuth client."""
        with (
            patch("src.ticket_clients.github.GitHubTicketClient"),
            patch("src.daemon.AzureOAuthClient") as mock_oauth_class,
            patch("src.daemon.MCPConfigManager") as mock_mcp_class,
        ):
            mock_oauth_instance = MagicMock()
            mock_oauth_class.return_value = mock_oauth_instance

            mock_mcp_instance = MagicMock()
            mock_mcp_instance.validate_config.return_value = []
            mock_mcp_instance.has_config.return_value = False
            mock_mcp_class.return_value = mock_mcp_instance

            config_with_azure.database_path = f"{config_with_azure.workspace_dir}/test.db"

            daemon = Daemon(config_with_azure)

            # Verify MCP config manager was created with Azure client
            mock_mcp_class.assert_called_once_with(azure_client=mock_oauth_instance)

            daemon.stop()

    def test_mcp_config_validation_warnings_logged(self, config_without_azure):
        """Test that MCP config validation warnings are logged."""
        with (
            patch("src.ticket_clients.github.GitHubTicketClient"),
            patch("src.daemon.MCPConfigManager") as mock_mcp_class,
            patch("src.daemon.logger") as mock_logger,
        ):
            mock_mcp_instance = MagicMock()
            mock_mcp_instance.validate_config.return_value = [
                "Warning 1: Missing field",
                "Warning 2: Invalid config",
            ]
            mock_mcp_instance.has_config.return_value = False
            mock_mcp_class.return_value = mock_mcp_instance

            config_without_azure.database_path = f"{config_without_azure.workspace_dir}/test.db"

            daemon = Daemon(config_without_azure)

            # Verify warnings were logged
            warning_calls = [call for call in mock_logger.warning.call_args_list
                          if "MCP config warning" in str(call)]
            assert len(warning_calls) == 2

            daemon.stop()


@pytest.mark.unit
class TestWorkflowRunnerMCPConfig:
    """Tests for WorkflowRunner MCP config path handling."""

    def test_run_passes_mcp_config_path_to_run_claude(self):
        """Test that WorkflowRunner.run() passes mcp_config_path to run_claude()."""
        config = MagicMock()
        config.stage_models = {"Research": "haiku"}
        config.claude_code_enable_telemetry = False

        runner = WorkflowRunner(config)

        mock_workflow = MagicMock()
        mock_workflow.name = "test-workflow"
        mock_workflow.init.return_value = ["test prompt"]

        mock_ctx = MagicMock()
        mock_ctx.repo = "test/repo"
        mock_ctx.issue_number = 123
        mock_ctx.workspace_path = "/path/to/workspace"

        with patch("src.daemon.run_claude") as mock_run_claude:
            mock_result = MagicMock()
            mock_result.response = "test response"
            mock_result.metrics = None
            mock_run_claude.return_value = mock_result

            runner.run(
                mock_workflow,
                mock_ctx,
                "Research",
                resume_session=None,
                mcp_config_path="/path/to/.mcp.kiln.json",
            )

            # Verify run_claude was called with mcp_config_path
            mock_run_claude.assert_called_once()
            call_kwargs = mock_run_claude.call_args
            assert call_kwargs.kwargs.get("mcp_config_path") == "/path/to/.mcp.kiln.json"

    def test_run_passes_none_when_no_mcp_config(self):
        """Test that WorkflowRunner.run() passes None when no MCP config."""
        config = MagicMock()
        config.stage_models = {"Research": "haiku"}
        config.claude_code_enable_telemetry = False

        runner = WorkflowRunner(config)

        mock_workflow = MagicMock()
        mock_workflow.name = "test-workflow"
        mock_workflow.init.return_value = ["test prompt"]

        mock_ctx = MagicMock()
        mock_ctx.repo = "test/repo"
        mock_ctx.issue_number = 123
        mock_ctx.workspace_path = "/path/to/workspace"

        with patch("src.daemon.run_claude") as mock_run_claude:
            mock_result = MagicMock()
            mock_result.response = "test response"
            mock_result.metrics = None
            mock_run_claude.return_value = mock_result

            runner.run(
                mock_workflow,
                mock_ctx,
                "Research",
                resume_session=None,
                # No mcp_config_path provided
            )

            # Verify run_claude was called with mcp_config_path=None
            mock_run_claude.assert_called_once()
            call_kwargs = mock_run_claude.call_args
            assert call_kwargs.kwargs.get("mcp_config_path") is None
