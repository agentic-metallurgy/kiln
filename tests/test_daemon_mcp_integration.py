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


@pytest.mark.integration
class TestDaemonMCPStartupLogging:
    """Integration tests for MCP startup logging behavior.

    These tests verify that the daemon correctly logs per-server MCP status
    with tool lists at startup, matching the spec format:
    - Success: "  Jenkins MCP loaded successfully. Tools: tool1, tool2"
    - Failure: "  Jenkins MCP: connection failed (timeout after 30s)"
    """

    @pytest.fixture
    def mock_mcp_config(self, tmp_path):
        """Create a temporary MCP config with multiple servers."""
        kiln_dir = tmp_path / ".kiln"
        kiln_dir.mkdir()
        mcp_config_path = kiln_dir / "mcp.json"

        config_data = {
            "mcpServers": {
                "jenkins": {
                    "url": "https://jenkins.example.com/mcp",
                    "env": {"AUTHORIZATION": "Bearer test-token"},
                },
                "filesystem": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/fs-server"],
                },
            }
        }
        mcp_config_path.write_text(json.dumps(config_data))

        # Change to this directory so MCPConfigManager finds the config
        import os
        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        yield tmp_path
        os.chdir(original_cwd)

    @pytest.fixture
    def base_config(self, tmp_path):
        """Base configuration without Azure OAuth."""
        config = MagicMock()
        config.poll_interval = 60
        config.watched_statuses = ["Research", "Plan", "Implement"]
        config.max_concurrent_workflows = 2
        config.workspace_dir = str(tmp_path)
        config.database_path = str(tmp_path / "test.db")
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

    def test_daemon_logs_successful_mcp_connections(self, base_config, mock_mcp_config):
        """Test that daemon logs per-server success with tool lists."""
        from src.integrations.mcp_client import MCPTestResult

        # Mock check_all_mcp_servers to return successful results
        mock_results = [
            MCPTestResult(
                server_name="jenkins",
                success=True,
                tools=["build_job", "get_logs", "list_jobs"],
            ),
            MCPTestResult(
                server_name="filesystem",
                success=True,
                tools=["read_file", "write_file"],
            ),
        ]

        with (
            patch("src.ticket_clients.github.GitHubTicketClient"),
            patch("src.daemon.check_all_mcp_servers", return_value=mock_results) as mock_check,
            patch("src.daemon.logger") as mock_logger,
        ):
            daemon = Daemon(base_config)

            # Verify check_all_mcp_servers was called
            mock_check.assert_called_once()

            # Verify per-server success was logged with tool lists
            info_calls = [str(call) for call in mock_logger.info.call_args_list]
            jenkins_log = next((c for c in info_calls if "jenkins" in c.lower()), None)
            filesystem_log = next((c for c in info_calls if "filesystem" in c.lower()), None)

            assert jenkins_log is not None, "Jenkins MCP success should be logged"
            assert "loaded successfully" in jenkins_log
            assert "build_job" in jenkins_log or "Tools:" in jenkins_log

            assert filesystem_log is not None, "Filesystem MCP success should be logged"
            assert "loaded successfully" in filesystem_log

            daemon.stop()

    def test_daemon_logs_failing_mcp_connections(self, base_config, mock_mcp_config):
        """Test that daemon logs per-server failures with error messages."""
        from src.integrations.mcp_client import MCPTestResult

        # Mock check_all_mcp_servers to return failure results
        mock_results = [
            MCPTestResult(
                server_name="jenkins",
                success=False,
                error="timeout after 30s",
            ),
            MCPTestResult(
                server_name="filesystem",
                success=False,
                error="command not found",
            ),
        ]

        with (
            patch("src.ticket_clients.github.GitHubTicketClient"),
            patch("src.daemon.check_all_mcp_servers", return_value=mock_results),
            patch("src.daemon.logger") as mock_logger,
        ):
            daemon = Daemon(base_config)

            # Verify failures are logged as warnings
            warning_calls = [str(call) for call in mock_logger.warning.call_args_list]
            jenkins_warning = next((c for c in warning_calls if "jenkins" in c.lower()), None)
            filesystem_warning = next((c for c in warning_calls if "filesystem" in c.lower()), None)

            assert jenkins_warning is not None, "Jenkins MCP failure should be logged as warning"
            assert "timeout" in jenkins_warning

            assert filesystem_warning is not None, "Filesystem MCP failure should be logged as warning"
            assert "command not found" in filesystem_warning

            daemon.stop()

    def test_daemon_logs_mixed_mcp_results(self, base_config, mock_mcp_config):
        """Test that daemon correctly logs mix of successful and failing servers."""
        from src.integrations.mcp_client import MCPTestResult

        # Mock check_all_mcp_servers to return mixed results
        mock_results = [
            MCPTestResult(
                server_name="jenkins",
                success=True,
                tools=["build_job", "get_logs"],
            ),
            MCPTestResult(
                server_name="filesystem",
                success=False,
                error="connection refused",
            ),
        ]

        with (
            patch("src.ticket_clients.github.GitHubTicketClient"),
            patch("src.daemon.check_all_mcp_servers", return_value=mock_results),
            patch("src.daemon.logger") as mock_logger,
        ):
            daemon = Daemon(base_config)

            # Verify successful connection is logged as info
            info_calls = [str(call) for call in mock_logger.info.call_args_list]
            jenkins_log = next((c for c in info_calls if "jenkins" in c.lower()), None)
            assert jenkins_log is not None, "Jenkins MCP success should be logged as info"
            assert "loaded successfully" in jenkins_log

            # Verify failure is logged as warning
            warning_calls = [str(call) for call in mock_logger.warning.call_args_list]
            filesystem_warning = next((c for c in warning_calls if "filesystem" in c.lower()), None)
            assert filesystem_warning is not None, "Filesystem MCP failure should be logged as warning"
            assert "connection refused" in filesystem_warning

            daemon.stop()

    def test_daemon_skips_mcp_testing_when_no_config(self, base_config):
        """Test that daemon doesn't call check_all_mcp_servers when no MCP config."""
        with (
            patch("src.ticket_clients.github.GitHubTicketClient"),
            patch("src.daemon.check_all_mcp_servers") as mock_check,
            patch("src.daemon.MCPConfigManager") as mock_mcp_class,
        ):
            mock_mcp_instance = MagicMock()
            mock_mcp_instance.validate_config.return_value = []
            mock_mcp_instance.load_config.return_value = None
            mock_mcp_class.return_value = mock_mcp_instance

            daemon = Daemon(base_config)

            # Verify check_all_mcp_servers was NOT called
            mock_check.assert_not_called()

            daemon.stop()

    def test_daemon_logs_tools_as_comma_separated_list(self, base_config, mock_mcp_config):
        """Test that tool lists are formatted as comma-separated strings."""
        from src.integrations.mcp_client import MCPTestResult

        # Mock check_all_mcp_servers to return results with multiple tools
        mock_results = [
            MCPTestResult(
                server_name="jenkins",
                success=True,
                tools=["build_job", "get_logs", "list_jobs"],
            ),
        ]

        with (
            patch("src.ticket_clients.github.GitHubTicketClient"),
            patch("src.daemon.check_all_mcp_servers", return_value=mock_results),
            patch("src.daemon.logger") as mock_logger,
        ):
            daemon = Daemon(base_config)

            # Check the format: "Tools: build_job, get_logs, list_jobs"
            info_calls = [str(call) for call in mock_logger.info.call_args_list]
            jenkins_log = next((c for c in info_calls if "jenkins" in c.lower()), None)
            assert jenkins_log is not None
            # Verify comma-separated format
            assert "build_job, get_logs, list_jobs" in jenkins_log or all(
                tool in jenkins_log for tool in ["build_job", "get_logs", "list_jobs"]
            )

            daemon.stop()

    def test_daemon_logs_none_when_no_tools(self, base_config, mock_mcp_config):
        """Test that 'none' is logged when server has no tools."""
        from src.integrations.mcp_client import MCPTestResult

        # Mock check_all_mcp_servers to return results with empty tools
        mock_results = [
            MCPTestResult(
                server_name="empty-server",
                success=True,
                tools=[],
            ),
        ]

        with (
            patch("src.ticket_clients.github.GitHubTicketClient"),
            patch("src.daemon.check_all_mcp_servers", return_value=mock_results),
            patch("src.daemon.logger") as mock_logger,
        ):
            daemon = Daemon(base_config)

            # Check that "Tools: none" is logged
            info_calls = [str(call) for call in mock_logger.info.call_args_list]
            empty_log = next((c for c in info_calls if "empty-server" in c.lower()), None)
            assert empty_log is not None
            assert "Tools: none" in empty_log

            daemon.stop()

    def test_daemon_continues_startup_on_mcp_failures(self, base_config, mock_mcp_config):
        """Test that daemon startup completes even when all MCP servers fail."""
        from src.integrations.mcp_client import MCPTestResult

        # Mock check_all_mcp_servers to return all failures
        mock_results = [
            MCPTestResult(
                server_name="jenkins",
                success=False,
                error="network unreachable",
            ),
            MCPTestResult(
                server_name="filesystem",
                success=False,
                error="command not found",
            ),
        ]

        with (
            patch("src.ticket_clients.github.GitHubTicketClient"),
            patch("src.daemon.check_all_mcp_servers", return_value=mock_results),
            patch("src.daemon.logger"),
        ):
            # Daemon should initialize successfully despite all MCP failures
            daemon = Daemon(base_config)
            assert daemon is not None
            assert daemon._running is False  # Not started yet, just initialized

            daemon.stop()

    def test_daemon_logs_mcp_server_count_before_details(self, base_config, mock_mcp_config):
        """Test that daemon logs total server count before per-server details."""
        from src.integrations.mcp_client import MCPTestResult

        mock_results = [
            MCPTestResult(server_name="server1", success=True, tools=["tool1"]),
            MCPTestResult(server_name="server2", success=True, tools=["tool2"]),
        ]

        with (
            patch("src.ticket_clients.github.GitHubTicketClient"),
            patch("src.daemon.check_all_mcp_servers", return_value=mock_results),
            patch("src.daemon.logger") as mock_logger,
        ):
            daemon = Daemon(base_config)

            # Verify server count is logged
            info_calls = [str(call) for call in mock_logger.info.call_args_list]
            count_log = next(
                (c for c in info_calls if "server(s)" in c.lower() or "2 server" in c.lower()),
                None
            )
            assert count_log is not None, "MCP server count should be logged"

            daemon.stop()
