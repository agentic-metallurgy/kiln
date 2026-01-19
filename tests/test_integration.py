"""Integration tests for agentic-metallurgy components.

These tests verify that real components work together correctly,
while mocking external dependencies (GitHub API, Claude CLI, etc.)
to avoid network calls.
"""

import json
import tempfile
from datetime import UTC
from pathlib import Path
from unittest.mock import MagicMock, Mock, call, patch

import pytest

from src.claude_runner import ClaudeResult, ClaudeRunnerError, ClaudeTimeoutError, run_claude
from src.daemon import Daemon, WorkflowRunner
from src.interfaces import Comment, TicketItem
from src.labels import REQUIRED_LABELS, Labels
from src.ticket_clients.github import GitHubTicketClient
from src.workspace import WorkspaceError, WorkspaceManager


@pytest.fixture
def temp_workspace_dir():
    """Fixture providing a temporary workspace directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def mock_gh_subprocess():
    """Fixture for mocking subprocess calls to gh CLI."""
    with patch("subprocess.run") as mock_run:
        yield mock_run


@pytest.fixture
def mock_claude_subprocess():
    """Fixture for mocking subprocess.Popen for Claude CLI."""
    with patch("subprocess.Popen") as mock_popen:
        yield mock_popen


# ============================================================================
# GitHubTicketClient Integration Tests
# ============================================================================


@pytest.mark.integration
class TestGitHubTicketClientIntegration:
    """Integration tests for GitHubTicketClient."""

    def test_parse_board_url_valid_formats(self):
        """Test _parse_board_url with various valid URL formats."""
        client = GitHubTicketClient({"github.com": "fake_token"})

        # Standard format
        hostname, org, num = client._parse_board_url(
            "https://github.com/orgs/chronoboost/projects/6/views/2"
        )
        assert hostname == "github.com"
        assert org == "chronoboost"
        assert num == 6

        # Without views part
        hostname, org, num = client._parse_board_url("https://github.com/orgs/myorg/projects/42")
        assert hostname == "github.com"
        assert org == "myorg"
        assert num == 42

        # With trailing slash
        hostname, org, num = client._parse_board_url(
            "https://github.com/orgs/test-org/projects/123/views/1/"
        )
        assert hostname == "github.com"
        assert org == "test-org"
        assert num == 123

    def test_parse_board_url_invalid_formats(self):
        """Test _parse_board_url raises ValueError for invalid URLs."""
        client = GitHubTicketClient({"github.com": "fake_token"})

        # Invalid URLs
        with pytest.raises(ValueError, match="Invalid project URL format"):
            client._parse_board_url("https://github.com/owner/repo")

        with pytest.raises(ValueError, match="Invalid project URL format"):
            client._parse_board_url("https://github.com/projects/123")

        with pytest.raises(ValueError, match="Invalid project URL format"):
            client._parse_board_url("not a url")

    def test_parse_board_item_node_valid_issue(self):
        """Test _parse_board_item_node with valid issue node data."""
        client = GitHubTicketClient({"github.com": "fake_token"})

        node = {
            "id": "PVTI_item123",
            "content": {
                "number": 42,
                "title": "Test Issue",
                "repository": {"nameWithOwner": "owner/repo"},
            },
            "fieldValues": {"nodes": [{"field": {"name": "Status"}, "name": "Research"}]},
        }

        board_url = "https://github.com/orgs/test/projects/1"
        item = client._parse_board_item_node(node, board_url, "github.com")

        assert item is not None
        assert item.item_id == "PVTI_item123"
        assert item.board_url == board_url
        assert item.ticket_id == 42
        assert item.title == "Test Issue"
        assert item.repo == "github.com/owner/repo"
        assert item.status == "Research"

    def test_parse_board_item_node_non_issue(self):
        """Test _parse_board_item_node returns None for non-issue nodes."""
        client = GitHubTicketClient({"github.com": "fake_token"})

        # Node without issue content
        node = {"id": "PVTI_item456", "content": None, "fieldValues": {"nodes": []}}

        board_url = "https://github.com/orgs/test/projects/1"
        item = client._parse_board_item_node(node, board_url, "github.com")
        assert item is None

    def test_parse_board_item_node_missing_status(self):
        """Test _parse_board_item_node handles missing status field."""
        client = GitHubTicketClient({"github.com": "fake_token"})

        node = {
            "id": "PVTI_item789",
            "content": {
                "number": 99,
                "title": "No Status Issue",
                "repository": {"nameWithOwner": "owner/repo"},
            },
            "fieldValues": {"nodes": []},
        }

        board_url = "https://github.com/orgs/test/projects/1"
        item = client._parse_board_item_node(node, board_url, "github.com")

        assert item is not None
        assert item.status == "Unknown"

    def test_parse_board_item_node_repo_format_always_includes_hostname(self):
        """Test that repo format is always hostname/owner/repo."""
        client = GitHubTicketClient({"github.com": "fake_token"})

        node = {
            "id": "PVTI_item123",
            "content": {
                "number": 42,
                "title": "Test Issue",
                "repository": {"nameWithOwner": "myorg/myrepo"},
            },
            "fieldValues": {"nodes": []},
        }

        # Test github.com
        board_url = "https://github.com/orgs/test/projects/1"
        item = client._parse_board_item_node(node, board_url, "github.com")
        assert item.repo == "github.com/myorg/myrepo"
        # Verify format: should have exactly 2 slashes (hostname/owner/repo)
        assert item.repo.count("/") == 2
        # Verify hostname is first segment
        assert item.repo.split("/")[0] == "github.com"

    def test_execute_graphql_query_mocked(self, mock_gh_subprocess):
        """Test _execute_graphql_query with mocked subprocess."""
        client = GitHubTicketClient({"github.com": "test_token"})

        # Mock response
        mock_response = {"data": {"organization": {"projectV2": {"title": "Test Project"}}}}
        mock_gh_subprocess.return_value.stdout = json.dumps(mock_response)
        mock_gh_subprocess.return_value.returncode = 0

        query = "query { organization { projectV2 { title } } }"
        variables = {"org": "testorg", "projectNumber": 1}

        result = client._execute_graphql_query(query, variables)

        assert result == mock_response
        # Verify gh was called with correct arguments
        mock_gh_subprocess.assert_called_once()
        args = mock_gh_subprocess.call_args[0][0]
        assert args[0] == "gh"
        assert "api" in args
        assert "graphql" in args

    def test_execute_graphql_query_handles_errors(self, mock_gh_subprocess):
        """Test _execute_graphql_query handles GraphQL errors in response."""
        client = GitHubTicketClient({"github.com": "test_token"})

        # Mock response with errors
        mock_response = {
            "errors": [{"message": "Invalid query"}, {"message": "Authentication failed"}]
        }
        mock_gh_subprocess.return_value.stdout = json.dumps(mock_response)
        mock_gh_subprocess.return_value.returncode = 0

        query = "query { invalid }"
        variables = {}

        with pytest.raises(ValueError, match="GraphQL errors"):
            client._execute_graphql_query(query, variables)

    def test_execute_graphql_query_handles_invalid_json(self, mock_gh_subprocess):
        """Test _execute_graphql_query handles invalid JSON response."""
        client = GitHubTicketClient({"github.com": "test_token"})

        # Mock invalid JSON response
        mock_gh_subprocess.return_value.stdout = "not valid json"
        mock_gh_subprocess.return_value.returncode = 0

        query = "query { test }"
        variables = {}

        with pytest.raises(ValueError, match="Invalid JSON response"):
            client._execute_graphql_query(query, variables)


# ============================================================================
# WorkspaceManager Integration Tests
# ============================================================================


@pytest.mark.integration
class TestWorkspaceManagerIntegration:
    """Integration tests for WorkspaceManager."""

    def test_create_workspace_creates_directories(self, temp_workspace_dir):
        """Test create_workspace creates proper directory structure."""
        manager = WorkspaceManager(temp_workspace_dir)

        # Verify base directories exist
        assert Path(temp_workspace_dir).exists()
        # No .repos directory should exist - main repo goes directly in workspace_dir
        assert not (Path(temp_workspace_dir) / ".repos").exists()

    def test_cleanup_workspace_requires_repo(self, temp_workspace_dir):
        """Test cleanup_workspace raises error when main repo doesn't exist."""
        manager = WorkspaceManager(temp_workspace_dir)

        # Create a fake workspace directory manually (not a real worktree)
        worktree_name = "test-repo-issue-42"
        worktree_path = Path(temp_workspace_dir) / worktree_name
        worktree_path.mkdir()

        # Create a fake file inside
        (worktree_path / "test_file.txt").write_text("test content")

        # Verify it exists
        assert worktree_path.exists()
        assert (worktree_path / "test_file.txt").exists()

        # Clean up should raise error when main repo (test-repo) doesn't exist
        with pytest.raises(WorkspaceError, match="Cannot cleanup worktree: repository not found"):
            manager.cleanup_workspace("test-repo", 42)

    def test_cleanup_workspace_handles_nonexistent_workspace(self, temp_workspace_dir):
        """Test cleanup_workspace handles non-existent workspace gracefully."""
        manager = WorkspaceManager(temp_workspace_dir)

        # Should not raise an error
        manager.cleanup_workspace("nonexistent-repo", 999)

    def test_extract_repo_name_https_url(self):
        """Test _extract_repo_name parses HTTPS URLs."""
        manager = WorkspaceManager("/tmp/test")

        assert manager._extract_repo_name("https://github.com/org/repo") == "repo"
        assert manager._extract_repo_name("https://github.com/org/repo.git") == "repo"
        assert manager._extract_repo_name("https://github.com/org/my-repo.git") == "my-repo"

    def test_extract_repo_name_ssh_url(self):
        """Test _extract_repo_name parses SSH URLs."""
        manager = WorkspaceManager("/tmp/test")

        assert manager._extract_repo_name("git@github.com:org/repo.git") == "repo"
        assert manager._extract_repo_name("git@github.com:org/my-repo.git") == "my-repo"

    def test_extract_repo_name_trailing_slash(self):
        """Test _extract_repo_name handles trailing slashes."""
        manager = WorkspaceManager("/tmp/test")

        assert manager._extract_repo_name("https://github.com/org/repo/") == "repo"
        assert manager._extract_repo_name("https://github.com/org/repo.git/") == "repo"

    def test_get_workspace_path(self, temp_workspace_dir):
        """Test get_workspace_path returns expected path."""
        manager = WorkspaceManager(temp_workspace_dir)

        path = manager.get_workspace_path("test-repo", 123)

        # Use resolve() to handle symlinks (macOS /var -> /private/var)
        expected = str(Path(temp_workspace_dir).resolve() / "test-repo-issue-123")
        assert path == expected

    def test_run_git_command_success(self, temp_workspace_dir):
        """Test _run_git_command with successful git command."""
        manager = WorkspaceManager(temp_workspace_dir)

        # Run git --version (should always work)
        result = manager._run_git_command(["--version"])

        assert result.returncode == 0
        assert "git version" in result.stdout.lower()

    def test_run_git_command_failure(self, temp_workspace_dir):
        """Test _run_git_command raises WorkspaceError on failure."""
        manager = WorkspaceManager(temp_workspace_dir)

        # Run invalid git command
        with pytest.raises(WorkspaceError, match="Git command failed"):
            manager._run_git_command(["invalid-command"])

    def test_rebase_from_main_returns_false_for_nonexistent_worktree(self, temp_workspace_dir):
        """Test rebase_from_main returns False for non-existent worktree."""
        manager = WorkspaceManager(temp_workspace_dir)

        result = manager.rebase_from_main("/nonexistent/path")
        assert result is False

    def test_rebase_from_main_success(self, temp_workspace_dir):
        """Test rebase_from_main calls correct git commands on success."""
        manager = WorkspaceManager(temp_workspace_dir)

        # Create a fake worktree directory
        worktree_path = Path(temp_workspace_dir) / "test-worktree"
        worktree_path.mkdir()

        git_commands = []

        def mock_run_git_command(args, cwd=None, check=True):
            git_commands.append(args)
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch.object(manager, "_run_git_command", mock_run_git_command):
            result = manager.rebase_from_main(str(worktree_path))

        assert result is True
        assert len(git_commands) == 2
        assert git_commands[0] == ["fetch", "origin", "main"]
        assert git_commands[1] == ["rebase", "origin/main"]

    def test_rebase_from_main_handles_conflict(self, temp_workspace_dir):
        """Test rebase_from_main returns False and aborts on conflict."""
        manager = WorkspaceManager(temp_workspace_dir)

        # Create a fake worktree directory
        worktree_path = Path(temp_workspace_dir) / "test-worktree"
        worktree_path.mkdir()

        git_commands = []

        def mock_run_git_command(args, cwd=None, check=True):
            git_commands.append(args)
            if args == ["rebase", "origin/main"]:
                raise WorkspaceError("CONFLICT: could not apply")
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch.object(manager, "_run_git_command", mock_run_git_command):
            result = manager.rebase_from_main(str(worktree_path))

        assert result is False
        # Should have called fetch, rebase, and abort
        assert ["fetch", "origin", "main"] in git_commands
        assert ["rebase", "origin/main"] in git_commands
        assert ["rebase", "--abort"] in git_commands


class TestWorkspaceSecurityValidation:
    """Security tests for path traversal prevention."""

    def test_rejects_path_traversal_in_repo_name(self, temp_workspace_dir):
        """Test that path traversal in repo_name is rejected."""
        manager = WorkspaceManager(temp_workspace_dir)

        with pytest.raises(WorkspaceError, match="forbidden path component"):
            manager.get_workspace_path("../evil", 42)

        with pytest.raises(WorkspaceError, match="forbidden path component"):
            manager.get_workspace_path("foo/../bar", 42)

        with pytest.raises(WorkspaceError, match="forbidden path component"):
            manager.get_workspace_path("foo/bar", 42)

    def test_rejects_backslash_in_repo_name(self, temp_workspace_dir):
        """Test that backslash in repo_name is rejected."""
        manager = WorkspaceManager(temp_workspace_dir)

        with pytest.raises(WorkspaceError, match="forbidden path component"):
            manager.get_workspace_path("foo\\bar", 42)

    def test_validate_path_containment_rejects_escape(self, temp_workspace_dir):
        """Test that path containment validation works correctly."""
        manager = WorkspaceManager(temp_workspace_dir)

        # Create path that would escape
        evil_path = Path(temp_workspace_dir) / ".." / "evil"

        with pytest.raises(WorkspaceError, match="outside allowed directory"):
            manager._validate_path_containment(evil_path, Path(temp_workspace_dir), "test")

    def test_git_command_rejects_cwd_outside_workspace(self, temp_workspace_dir):
        """Test that git commands with cwd outside workspace are rejected."""
        manager = WorkspaceManager(temp_workspace_dir)

        with pytest.raises(WorkspaceError, match="outside workspace boundaries"):
            manager._run_git_command(["status"], cwd=Path("/tmp"))

    def test_cleanup_validates_paths(self, temp_workspace_dir):
        """Test that cleanup validates paths before operations."""
        manager = WorkspaceManager(temp_workspace_dir)

        with pytest.raises(WorkspaceError, match="forbidden path component"):
            manager.cleanup_workspace("../evil", 42)

    def test_validate_name_component_accepts_valid_names(self, temp_workspace_dir):
        """Test that valid repo names are accepted."""
        manager = WorkspaceManager(temp_workspace_dir)

        # These should not raise
        manager._validate_name_component("valid-repo", "test")
        manager._validate_name_component("repo_name", "test")
        manager._validate_name_component("repo123", "test")

    def test_validate_path_containment_accepts_valid_paths(self, temp_workspace_dir):
        """Test that valid paths are accepted."""
        manager = WorkspaceManager(temp_workspace_dir)

        valid_path = Path(temp_workspace_dir) / "valid-dir"
        result = manager._validate_path_containment(valid_path, Path(temp_workspace_dir), "test")
        assert result == valid_path.resolve()


# ============================================================================
# ClaudeRunner Tests (with mocked subprocess)
# ============================================================================


@pytest.mark.integration
class TestClaudeRunnerIntegration:
    """Integration tests for ClaudeRunner (run_claude function)."""

    def test_run_claude_handles_valid_json_stream(self, mock_claude_subprocess, temp_workspace_dir):
        """Test run_claude handles valid JSON stream responses."""
        # Mock process
        mock_process = Mock()
        mock_process.stdin = Mock()
        mock_process.stdout = Mock()
        mock_process.stderr = Mock()
        mock_process.poll = Mock(side_effect=[None, None, 0])  # Running, then finished
        mock_process.wait = Mock(return_value=0)
        mock_process.returncode = 0

        # Simulate streaming JSON output (Claude CLI stream-json format)
        json_lines = [
            json.dumps(
                {"type": "assistant", "message": {"content": [{"type": "text", "text": "Hello "}]}}
            )
            + "\n",
            json.dumps(
                {"type": "assistant", "message": {"content": [{"type": "text", "text": "World"}]}}
            )
            + "\n",
            json.dumps({"type": "result", "result": "!"}) + "\n",
            "",  # End of stream
        ]

        # Use an iterator that returns lines one by one
        line_iter = iter(json_lines)
        mock_process.stdout.readline = lambda: next(line_iter, "")
        mock_process.stderr.read = Mock(return_value="")

        mock_claude_subprocess.return_value = mock_process

        # Run Claude
        result = run_claude("test prompt", temp_workspace_dir)

        assert isinstance(result, ClaudeResult)
        assert result.response == "Hello World!"
        mock_process.stdin.write.assert_called_once_with("test prompt")
        mock_process.stdin.close.assert_called_once()

    def test_run_claude_handles_timeout(self, mock_claude_subprocess, temp_workspace_dir):
        """Test run_claude handles timeout scenarios."""
        # Mock process that never finishes
        mock_process = Mock()
        mock_process.stdin = Mock()
        mock_process.stdout = Mock()
        mock_process.stderr = Mock()
        mock_process.poll = Mock(return_value=None)  # Always running
        mock_process.kill = Mock()

        # Simulate hanging (no output)
        mock_process.stdout.readline = Mock(return_value="")

        mock_claude_subprocess.return_value = mock_process

        # Should timeout quickly (set timeout to 1 second)
        with pytest.raises(ClaudeTimeoutError, match="exceeded.*timeout"):
            run_claude("test prompt", temp_workspace_dir, timeout=1)

        # Verify process was killed
        mock_process.kill.assert_called_once()

    def test_run_claude_handles_error_response(self, mock_claude_subprocess, temp_workspace_dir):
        """Test run_claude handles error responses from Claude."""
        # Mock process
        mock_process = Mock()
        mock_process.stdin = Mock()
        mock_process.stdout = Mock()
        mock_process.stderr = Mock()
        mock_process.poll = Mock(return_value=0)
        mock_process.wait = Mock(return_value=0)

        # Simulate error response
        error_response = json.dumps({"type": "error", "message": "Something went wrong"})
        mock_process.stdout.readline = Mock(side_effect=[error_response, ""])
        mock_process.stderr.read = Mock(return_value="")

        mock_claude_subprocess.return_value = mock_process

        # Should raise ClaudeRunnerError
        with pytest.raises(ClaudeRunnerError, match="Claude error: Something went wrong"):
            run_claude("test prompt", temp_workspace_dir)

    def test_run_claude_handles_non_zero_exit_code(
        self, mock_claude_subprocess, temp_workspace_dir
    ):
        """Test run_claude handles non-zero exit codes."""
        # Mock process
        mock_process = Mock()
        mock_process.stdin = Mock()
        mock_process.stdout = Mock()
        mock_process.stderr = Mock()
        mock_process.poll = Mock(return_value=1)  # Failed
        mock_process.wait = Mock(return_value=1)
        mock_process.returncode = 1

        # No output
        mock_process.stdout.readline = Mock(return_value="")
        mock_process.stderr.read = Mock(return_value="Error: something failed")

        mock_claude_subprocess.return_value = mock_process

        # Should raise ClaudeRunnerError
        with pytest.raises(ClaudeRunnerError, match="failed with exit code 1"):
            run_claude("test prompt", temp_workspace_dir)

    def test_run_claude_handles_empty_response(self, mock_claude_subprocess, temp_workspace_dir):
        """Test run_claude handles empty response."""
        # Mock process
        mock_process = Mock()
        mock_process.stdin = Mock()
        mock_process.stdout = Mock()
        mock_process.stderr = Mock()
        mock_process.poll = Mock(return_value=0)
        mock_process.wait = Mock(return_value=0)
        mock_process.returncode = 0

        # No output at all
        mock_process.stdout.readline = Mock(return_value="")
        mock_process.stderr.read = Mock(return_value="")

        mock_claude_subprocess.return_value = mock_process

        # Should raise ClaudeRunnerError
        with pytest.raises(ClaudeRunnerError, match="No response received"):
            run_claude("test prompt", temp_workspace_dir)

    def test_run_claude_handles_malformed_json(self, mock_claude_subprocess, temp_workspace_dir):
        """Test run_claude handles malformed JSON gracefully."""
        # Mock process
        mock_process = Mock()
        mock_process.stdin = Mock()
        mock_process.stdout = Mock()
        mock_process.stderr = Mock()
        mock_process.poll = Mock(side_effect=[None, None, 0])
        mock_process.wait = Mock(return_value=0)
        mock_process.returncode = 0

        # Mix of malformed and valid JSON (Claude CLI stream-json format)
        lines = [
            "invalid json\n",
            json.dumps(
                {"type": "assistant", "message": {"content": [{"type": "text", "text": "Valid"}]}}
            )
            + "\n",
            "",  # End of stream
        ]

        # Use an iterator
        line_iter = iter(lines)
        mock_process.stdout.readline = lambda: next(line_iter, "")
        mock_process.stderr.read = Mock(return_value="")

        mock_claude_subprocess.return_value = mock_process

        # Should still extract the valid text
        result = run_claude("test prompt", temp_workspace_dir)
        assert isinstance(result, ClaudeResult)
        assert result.response == "Valid"


# ============================================================================
# Daemon Component Integration Tests
# ============================================================================


@pytest.mark.integration
class TestWorkflowRunnerIntegration:
    """Integration tests for WorkflowRunner."""

    def test_workflow_runner_executes_prompts_in_order(self, temp_workspace_dir):
        """Test WorkflowRunner executes prompts in order."""
        from src.config import Config
        from src.workflows import ResearchWorkflow, WorkflowContext

        config = Config(
            github_token="test_token", project_urls=["https://github.com/orgs/test/projects/1"]
        )
        runner = WorkflowRunner(config)

        # Create workflow context
        ctx = WorkflowContext(
            repo="owner/repo",
            issue_number=42,
            issue_title="Test Issue",
            workspace_path=temp_workspace_dir,
        )

        # Create workflow
        workflow = ResearchWorkflow()

        # Mock run_claude to track calls
        call_order = []

        def mock_run_claude(
            prompt,
            cwd,
            model=None,
            issue_context=None,
            resume_session=None,
            enable_telemetry=False,
            execution_stage=None,
        ):
            call_order.append(prompt[:50])  # Track first 50 chars
            return ClaudeResult(response=f"Response for prompt {len(call_order)}", metrics=None)

        with patch("src.daemon.run_claude", side_effect=mock_run_claude):
            runner.run(workflow, ctx, "Research")

        # Verify all prompts were executed
        prompts = workflow.init(ctx)
        assert len(call_order) == len(prompts)

        # Verify order by checking prompt content
        for i, prompt in enumerate(prompts):
            assert call_order[i] == prompt[:50]

    def test_workflow_runner_raises_on_failure(self, temp_workspace_dir):
        """Test WorkflowRunner raises exception when prompt fails."""
        from src.config import Config
        from src.workflows import PlanWorkflow, WorkflowContext

        config = Config(
            github_token="test_token", project_urls=["https://github.com/orgs/test/projects/1"]
        )
        runner = WorkflowRunner(config)

        ctx = WorkflowContext(
            repo="owner/repo",
            issue_number=123,
            issue_title="Test",
            workspace_path=temp_workspace_dir,
        )

        workflow = PlanWorkflow()

        # Mock run_claude to fail
        with patch("src.daemon.run_claude", side_effect=ClaudeRunnerError("Failed")):
            with pytest.raises(ClaudeRunnerError):
                runner.run(workflow, ctx, "Plan")


@pytest.mark.integration
class TestDaemonIntegration:
    """Integration tests for Daemon component."""

    @pytest.fixture
    def mock_config(self, temp_workspace_dir):
        """Fixture providing mock Config object."""
        from src.config import Config

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        config = Config(
            github_token="test_token",
            project_urls=["https://github.com/orgs/test/projects/1"],
            workspace_dir=temp_workspace_dir,
            database_path=db_path,
            poll_interval=60,
            watched_statuses=["Prepare", "Research", "Plan", "Implement"],
            allowed_username="allowed_user",
        )

        yield config

        # Cleanup
        Path(db_path).unlink(missing_ok=True)

    def test_daemon_should_trigger_workflow_new_item(self, mock_config, temp_workspace_dir):
        """Test Daemon._should_trigger_workflow returns True for new items (no labels) by allowed user."""
        daemon = Daemon(mock_config)

        # Create a test item
        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
        )

        # Mock get_last_status_actor to return an allowed user
        with patch.object(
            daemon.ticket_client, "get_last_status_actor", return_value="allowed_user"
        ):
            should_trigger = daemon._should_trigger_workflow(item)
            assert should_trigger is True

    def test_daemon_process_item_workflow_handles_new_item(self, mock_config, temp_workspace_dir):
        """Test Daemon._process_item_workflow handles new items correctly."""
        daemon = Daemon(mock_config)

        # Create a test item
        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
        )

        # Mock workflow execution and label methods
        with (
            patch.object(daemon, "_run_workflow") as mock_run_workflow,
            patch.object(daemon.ticket_client, "add_label"),
            patch.object(daemon.ticket_client, "remove_label"),
            patch.object(daemon.ticket_client, "get_comments", return_value=[]),
        ):
            daemon._process_item_workflow(item)

            # Verify workflow was triggered
            mock_run_workflow.assert_called_once()
            args = mock_run_workflow.call_args[0]
            assert args[0] == "Research"  # workflow_name
            assert args[1] == item  # item

        # Verify database was updated
        state = daemon.database.get_issue_state("owner/repo", 42)
        assert state is not None
        assert state.status == "Research"

    def test_daemon_should_trigger_workflow_no_labels(self, mock_config, temp_workspace_dir):
        """Test Daemon._should_trigger_workflow returns True when no labels present and allowed user."""
        daemon = Daemon(mock_config)

        # Create item in Plan status
        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Plan",
            title="Test Issue",
        )

        # Mock get_last_status_actor to return an allowed user
        with patch.object(
            daemon.ticket_client, "get_last_status_actor", return_value="allowed_user"
        ):
            should_trigger = daemon._should_trigger_workflow(item)
            assert should_trigger is True

    def test_daemon_process_item_workflow_handles_status_change(
        self, mock_config, temp_workspace_dir
    ):
        """Test Daemon._process_item_workflow handles status changes correctly."""
        daemon = Daemon(mock_config)

        # Add initial state to database
        daemon.database.update_issue_state("owner/repo", 42, "Research")

        # Create item with new status
        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Plan",
            title="Test Issue",
        )

        # Mock workflow execution and label methods
        with (
            patch.object(daemon, "_run_workflow") as mock_run_workflow,
            patch.object(daemon.ticket_client, "add_label"),
            patch.object(daemon.ticket_client, "remove_label"),
            patch.object(daemon.ticket_client, "get_comments", return_value=[]),
        ):
            daemon._process_item_workflow(item)

            # Verify workflow was triggered
            mock_run_workflow.assert_called_once()
            args = mock_run_workflow.call_args[0]
            assert args[0] == "Plan"  # new status

        # Verify database was updated
        state = daemon.database.get_issue_state("owner/repo", 42)
        assert state.status == "Plan"

    def test_daemon_should_trigger_workflow_skips_unwatched_status(self, mock_config):
        """Test Daemon._should_trigger_workflow returns False for unwatched status."""
        daemon = Daemon(mock_config)

        # Create item with unwatched status
        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Backlog",  # Not in watched_statuses
            title="Test Issue",
        )

        # Should not trigger workflow for unwatched status
        should_trigger = daemon._should_trigger_workflow(item)
        assert should_trigger is False

    def test_daemon_should_trigger_workflow_skips_complete_label(self, mock_config):
        """Test Daemon._should_trigger_workflow returns False when complete label present in cache."""
        daemon = Daemon(mock_config)

        # Create item in Research status with cached complete label
        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
            labels={"research_ready"},  # Cached complete label
        )

        # No mock needed - uses cached labels
        should_trigger = daemon._should_trigger_workflow(item)
        assert should_trigger is False

    def test_daemon_run_workflow_creates_context_and_runs(self, mock_config, temp_workspace_dir):
        """Test Daemon._run_workflow creates WorkflowContext and runs workflow."""
        daemon = Daemon(mock_config)

        # Item with cached research_ready label to skip rebase
        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
            labels={"research_ready"},  # Skip rebase
        )

        # No has_label mock needed - uses cached labels
        with patch.object(daemon.runner, "run") as mock_run:
            daemon._run_workflow("Research", item)

            # Verify runner was called
            mock_run.assert_called_once()

            # Verify workflow type
            workflow = mock_run.call_args[0][0]
            from src.workflows import ResearchWorkflow

            assert isinstance(workflow, ResearchWorkflow)

            # Verify context
            ctx = mock_run.call_args[0][1]
            assert ctx.repo == "owner/repo"
            assert ctx.issue_number == 42
            assert ctx.issue_title == "Test Issue"
            # Workspace path is now determined internally by _run_workflow
            assert ctx.workspace_path == daemon._get_worktree_path("owner/repo", 42)

    def test_daemon_handles_unknown_workflow(self, mock_config, temp_workspace_dir):
        """Test Daemon handles unknown workflow gracefully."""
        daemon = Daemon(mock_config)

        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="UnknownStatus",
            title="Test Issue",
        )

        # Should not raise, just log error and return early
        daemon._run_workflow("UnknownStatus", item)

        # No error should be raised

    def test_daemon_rebases_on_first_research_run(self, mock_config, temp_workspace_dir):
        """Test rebase happens on first Research run (no research_ready label in cache)."""
        daemon = Daemon(mock_config)
        rebase_calls = []

        def mock_rebase(path):
            rebase_calls.append(path)
            return True

        # Item without research_ready label in cache (first run)
        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
            labels=set(),  # No cached labels - first run
        )

        # No has_label mock needed - uses cached labels
        with (
            patch.object(daemon.workspace_manager, "rebase_from_main", mock_rebase),
            patch.object(daemon.runner, "run"),
        ):
            daemon._run_workflow("Research", item)
            assert len(rebase_calls) == 1  # Should rebase

    def test_daemon_no_rebase_on_research_rerun(self, mock_config, temp_workspace_dir):
        """Test no rebase when Research has research_ready label in cache (re-run)."""
        daemon = Daemon(mock_config)
        rebase_calls = []

        def mock_rebase(path):
            rebase_calls.append(path)
            return True

        # Item with research_ready label in cache (already ran before)
        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
            labels={"research_ready"},  # Has complete label - re-run
        )

        # No has_label mock needed - uses cached labels
        with (
            patch.object(daemon.workspace_manager, "rebase_from_main", mock_rebase),
            patch.object(daemon.runner, "run"),
        ):
            daemon._run_workflow("Research", item)
            assert len(rebase_calls) == 0  # Should NOT rebase

    def test_daemon_no_rebase_on_plan_or_implement(self, mock_config, temp_workspace_dir):
        """Test no rebase on Plan or Implement workflows."""
        daemon = Daemon(mock_config)
        rebase_calls = []

        def mock_rebase(path):
            rebase_calls.append(path)
            return True

        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Plan",
            title="Test Issue",
        )

        with (
            patch.object(daemon.workspace_manager, "rebase_from_main", mock_rebase),
            patch.object(daemon.runner, "run"),
        ):
            daemon._run_workflow("Plan", item)
            assert len(rebase_calls) == 0

            daemon._run_workflow("Implement", item)
            assert len(rebase_calls) == 0

    def test_daemon_rebase_failure_raises_workspace_error(self, mock_config, temp_workspace_dir):
        """Test rebase failure raises WorkspaceError."""
        from src.workspace import WorkspaceError

        daemon = Daemon(mock_config)

        def mock_rebase_fail(path):
            return False  # Simulate conflict

        # Item without research_ready label (first run, will attempt rebase)
        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
            labels=set(),  # No labels - first run
        )

        # No has_label mock needed - uses cached labels
        with patch.object(daemon.workspace_manager, "rebase_from_main", mock_rebase_fail):
            with pytest.raises(WorkspaceError, match="Rebase failed due to conflicts"):
                daemon._run_workflow("Research", item)

    def test_daemon_should_trigger_workflow_skips_with_running_label(self, mock_config):
        """Test _should_trigger_workflow returns False when running label is present in cached labels."""
        daemon = Daemon(mock_config)

        # Item with cached "researching" label
        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
            labels={"researching"},  # Cached running label
        )

        # No API mock needed - uses cached labels
        should_trigger = daemon._should_trigger_workflow(item)
        assert should_trigger is False

    def test_daemon_should_trigger_workflow_skips_with_complete_label_v2(self, mock_config):
        """Test _should_trigger_workflow returns False when complete label is present in cached labels."""
        daemon = Daemon(mock_config)

        # Item with cached "research_ready" complete label
        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
            labels={"research_ready"},  # Cached complete label
        )

        # No API mock needed - uses cached labels
        should_trigger = daemon._should_trigger_workflow(item)
        assert should_trigger is False

    def test_daemon_should_trigger_workflow_triggers_when_no_labels_v2(self, mock_config):
        """Test _should_trigger_workflow returns True when no workflow labels present in cache and allowed user."""
        daemon = Daemon(mock_config)

        # Item with no cached workflow labels
        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
            labels=set(),  # No cached labels
        )

        # Mock get_last_status_actor to return an allowed user
        with patch.object(
            daemon.ticket_client, "get_last_status_actor", return_value="allowed_user"
        ):
            should_trigger = daemon._should_trigger_workflow(item)
            assert should_trigger is True

    def test_daemon_should_trigger_workflow_blocked_user(self, mock_config):
        """Test _should_trigger_workflow returns False when actor does not match allowed_username."""
        daemon = Daemon(mock_config)

        # Item with no cached workflow labels
        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
            labels=set(),  # No cached labels
        )

        # Mock get_last_status_actor to return a non-allowed user
        with patch.object(
            daemon.ticket_client, "get_last_status_actor", return_value="blocked_user"
        ):
            should_trigger = daemon._should_trigger_workflow(item)
            assert should_trigger is False

    def test_daemon_should_trigger_workflow_unknown_actor(self, mock_config):
        """Test _should_trigger_workflow returns False when actor cannot be determined."""
        daemon = Daemon(mock_config)

        # Item with no cached workflow labels
        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
            labels=set(),  # No cached labels
        )

        # Mock get_last_status_actor to return None (unknown actor)
        with patch.object(daemon.ticket_client, "get_last_status_actor", return_value=None):
            should_trigger = daemon._should_trigger_workflow(item)
            assert should_trigger is False

    def test_daemon_process_item_workflow_adds_running_label(self, mock_config, temp_workspace_dir):
        """Test _process_item_workflow adds running label before workflow."""
        daemon = Daemon(mock_config)

        # Create worktree path so auto-prepare is skipped
        worktree_path = f"{temp_workspace_dir}/repo-issue-42"
        Path(worktree_path).mkdir(parents=True, exist_ok=True)

        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
            labels={"research_ready"},  # Already has complete label for rebase skip
        )

        label_calls = {"add": [], "remove": []}

        def mock_add_label(repo, issue, label, **kwargs):
            label_calls["add"].append(label)

        def mock_remove_label(repo, issue, label, **kwargs):
            label_calls["remove"].append(label)

        with (
            patch.object(daemon.ticket_client, "add_label", mock_add_label),
            patch.object(daemon.ticket_client, "remove_label", mock_remove_label),
            patch.object(daemon.ticket_client, "get_comments", return_value=[]),
            patch.object(daemon.runner, "run"),
        ):
            daemon._process_item_workflow(item)

        # Should have added "researching" then removed it and added "research_ready"
        assert "researching" in label_calls["add"]
        assert "researching" in label_calls["remove"]
        assert "research_ready" in label_calls["add"]

    def test_daemon_process_item_workflow_removes_label_on_failure(
        self, mock_config, temp_workspace_dir
    ):
        """Test _process_item_workflow removes running label on failure."""
        daemon = Daemon(mock_config)

        # Create worktree path so auto-prepare is skipped
        worktree_path = f"{temp_workspace_dir}/repo-issue-42"
        Path(worktree_path).mkdir(parents=True, exist_ok=True)

        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
            labels={"research_ready"},  # Already has complete label for rebase skip
        )

        label_calls = {"add": [], "remove": []}

        def mock_add_label(repo, issue, label, **kwargs):
            label_calls["add"].append(label)

        def mock_remove_label(repo, issue, label, **kwargs):
            label_calls["remove"].append(label)

        # Mock runner to raise an exception
        with (
            patch.object(daemon.ticket_client, "add_label", mock_add_label),
            patch.object(daemon.ticket_client, "remove_label", mock_remove_label),
            patch.object(daemon.runner, "run", side_effect=Exception("Workflow failed")),
            pytest.raises(Exception),
        ):
            daemon._process_item_workflow(item)

        # Should have added "researching" then removed it on failure
        assert "researching" in label_calls["add"]
        assert "researching" in label_calls["remove"]
        # Should NOT have added complete label
        assert "research_ready" not in label_calls["add"]

    def test_daemon_process_item_workflow_implement_moves_to_validate(
        self, mock_config, temp_workspace_dir
    ):
        """Test _process_item_workflow moves item to Validate for Implement."""
        daemon = Daemon(mock_config)

        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Implement",
            title="Test Issue",
        )

        status_updates = []

        def mock_update_status(item_id, new_status):
            status_updates.append((item_id, new_status))

        with (
            patch.object(daemon.ticket_client, "add_label"),
            patch.object(daemon.ticket_client, "remove_label"),
            patch.object(daemon.ticket_client, "update_item_status", mock_update_status),
            patch.object(daemon.ticket_client, "get_comments", return_value=[]),
            patch.object(daemon.runner, "run"),
        ):
            daemon._process_item_workflow(item)

        # Should have moved to Validate
        assert status_updates == [("PVTI_123", "Validate")]

    # NOTE: Reset logic has been disabled - Prepare no longer removes labels
    # Remove labels manually to re-run specific workflows

    def test_daemon_yolo_progression_research_to_plan(self, mock_config, temp_workspace_dir):
        """Test YOLO mode auto-advances from Research to Plan after workflow completes."""
        daemon = Daemon(mock_config)

        # Create item in Research status with yolo label (include research_ready to skip rebase)
        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
            labels={"yolo", "research_ready"},  # research_ready skips rebase
        )

        status_updates = []

        def mock_update_status(item_id, new_status):
            status_updates.append((item_id, new_status))

        worktree_path = daemon._get_worktree_path(item.repo, item.ticket_id)
        Path(worktree_path).mkdir(parents=True, exist_ok=True)

        with (
            patch.object(daemon.ticket_client, "add_label"),
            patch.object(daemon.ticket_client, "remove_label"),
            patch.object(daemon.ticket_client, "update_item_status", mock_update_status),
            patch.object(daemon.ticket_client, "get_comments", return_value=[]),
            patch.object(daemon.runner, "run"),
        ):
            daemon._process_item_workflow(item)

        # Should have auto-advanced to Plan (Research has no next_status)
        assert ("PVTI_123", "Plan") in status_updates

    def test_daemon_poll_handles_api_errors(self, mock_config, temp_workspace_dir):
        """Test daemon poll cycle handles API errors gracefully."""
        daemon = Daemon(mock_config)

        with patch.object(
            daemon.ticket_client, "get_board_items", side_effect=Exception("API error")
        ):
            # Should not raise, just log error
            daemon._poll()

    def test_daemon_poll_processes_multiple_boards(self, mock_config, temp_workspace_dir):
        """Test daemon poll cycle processes multiple project boards."""
        mock_config.project_urls = [
            "https://github.com/orgs/test/projects/1",
            "https://github.com/orgs/test/projects/2",
        ]
        daemon = Daemon(mock_config)

        board_items_calls = []

        def mock_get_board_items(url):
            board_items_calls.append(url)
            return []

        with patch.object(daemon.ticket_client, "get_board_items", mock_get_board_items):
            daemon._poll()

        assert len(board_items_calls) == 2
        assert "https://github.com/orgs/test/projects/1" in board_items_calls
        assert "https://github.com/orgs/test/projects/2" in board_items_calls

    def test_daemon_skips_closed_issues(self, mock_config, temp_workspace_dir):
        """Test daemon skips processing closed issues."""
        daemon = Daemon(mock_config)

        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Closed Issue",
            state="CLOSED",
        )

        should_trigger = daemon._should_trigger_workflow(item)
        assert should_trigger is False

    def test_daemon_skips_issues_with_blocked_label(self, mock_config, temp_workspace_dir):
        """Test daemon skips issues with kiln-blocked label."""
        daemon = Daemon(mock_config)

        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Blocked Issue",
            labels={"kiln-blocked"},
        )

        should_trigger = daemon._should_trigger_workflow(item)
        assert should_trigger is False

    def test_daemon_processes_yolo_labeled_issues(self, mock_config, temp_workspace_dir):
        """Test daemon processes issues with yolo label via label actor check."""
        daemon = Daemon(mock_config)

        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="YOLO Issue",
            labels={"yolo"},
        )

        # For yolo issues, the label actor is checked (get_label_actor)
        # and also the project status actor may be checked
        with (
            patch.object(daemon.ticket_client, "get_label_actor", return_value="allowed_user"),
            patch.object(
                daemon.ticket_client, "get_last_status_actor", return_value="allowed_user"
            ),
        ):
            should_trigger = daemon._should_trigger_workflow(item)
            assert should_trigger is True

    def test_daemon_has_comment_processor(self, mock_config, temp_workspace_dir):
        """Test that daemon initializes with a comment processor."""
        daemon = Daemon(mock_config)

        # Verify comment processor is initialized
        assert daemon.comment_processor is not None
        from src.comment_processor import CommentProcessor

        assert isinstance(daemon.comment_processor, CommentProcessor)

    def test_daemon_project_metadata_caching(self, mock_config, temp_workspace_dir):
        """Test that project metadata is cached after initialization."""
        # Metadata is stored in daemon._project_metadata dict after _initialize_project_metadata
        daemon = Daemon(mock_config)

        # Verify cache was populated during init
        project_url = "https://github.com/orgs/test/projects/1"
        # Access the private cache directly since there's no public getter
        assert daemon._project_metadata is not None

    def test_daemon_concurrent_workflow_limit(self, mock_config, temp_workspace_dir):
        """Test daemon respects max_concurrent_workflows limit."""
        mock_config.max_concurrent_workflows = 2
        daemon = Daemon(mock_config)

        # Verify thread pool size matches config
        assert daemon.executor._max_workers == 2

    def test_daemon_handles_prepare_workflow_missing_worktree(
        self, mock_config, temp_workspace_dir
    ):
        """Test daemon attempts rebase when worktree doesn't exist (first run)."""
        daemon = Daemon(mock_config)

        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
            labels=set(),  # No labels - triggers rebase on first Research run
        )

        rebase_calls = []

        def mock_rebase(path):
            rebase_calls.append(path)
            return True  # Success

        # Worktree doesn't exist, so rebase will be attempted
        with (
            patch.object(daemon.workspace_manager, "rebase_from_main", mock_rebase),
            patch.object(daemon.runner, "run"),
        ):
            daemon._run_workflow("Research", item)

        # Should have called rebase for first Research run (no research_ready label)
        assert len(rebase_calls) == 1

    def test_daemon_skips_merged_issues(self, mock_config, temp_workspace_dir):
        """Test daemon skips issues that have been closed by merged PR."""
        daemon = Daemon(mock_config)

        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Merged Issue",
            state="CLOSED",
            has_merged_changes=True,
        )

        should_trigger = daemon._should_trigger_workflow(item)
        assert should_trigger is False

    def test_daemon_error_recovery_removes_running_label(self, mock_config, temp_workspace_dir):
        """Test daemon removes running label when workflow errors during execution."""
        daemon = Daemon(mock_config)

        # Create worktree path so auto-prepare is skipped
        worktree_path = f"{temp_workspace_dir}/repo-issue-42"
        Path(worktree_path).mkdir(parents=True, exist_ok=True)

        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Plan",
            title="Test Issue",
            labels={"plan_ready"},  # Has complete label for rebase skip
        )

        removed_labels = []

        def mock_remove_label(repo, issue, label, **kwargs):
            removed_labels.append(label)

        # Simulate runner failing mid-workflow
        with (
            patch.object(daemon.ticket_client, "add_label"),
            patch.object(daemon.ticket_client, "remove_label", mock_remove_label),
            patch.object(daemon.runner, "run", side_effect=Exception("Workflow crashed")),
            pytest.raises(Exception),
        ):
            daemon._process_item_workflow(item)

        # Running label should be removed on error
        assert "planning" in removed_labels

    def test_daemon_yolo_progression_plan_to_implement(self, mock_config, temp_workspace_dir):
        """Test YOLO mode auto-advances from Plan to Implement after workflow completes."""
        daemon = Daemon(mock_config)

        # Create item in Plan status with yolo label
        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Plan",
            title="Test Issue",
            labels={"yolo"},
        )

        status_updates = []

        def mock_update_status(item_id, new_status):
            status_updates.append((item_id, new_status))

        with (
            patch.object(daemon.ticket_client, "add_label"),
            patch.object(daemon.ticket_client, "remove_label"),
            patch.object(daemon.ticket_client, "update_item_status", mock_update_status),
            patch.object(daemon.ticket_client, "get_comments", return_value=[]),
            patch.object(daemon.runner, "run"),
        ):
            daemon._process_item_workflow(item)

        # Should have auto-advanced to Implement (Plan has no next_status)
        assert ("PVTI_123", "Implement") in status_updates

    def test_daemon_yolo_backlog_trigger(self, mock_config, temp_workspace_dir):
        """Test YOLO mode moves Backlog issues to Research in poll when added by allowed user."""
        mock_config.allowed_username = "allowed_user"
        daemon = Daemon(mock_config)

        # Create item in Backlog status with yolo label
        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Backlog",
            title="Test Issue",
            labels={"yolo"},
        )

        status_updates = []

        def mock_update_status(item_id, new_status):
            status_updates.append((item_id, new_status))

        with (
            patch.object(daemon.ticket_client, "get_board_items", return_value=[item]),
            patch.object(daemon.ticket_client, "update_item_status", mock_update_status),
            patch.object(daemon.ticket_client, "get_label_actor", return_value="allowed_user"),
            patch.object(daemon, "_maybe_cleanup"),
            patch.object(daemon, "_maybe_archive_closed"),
            patch.object(daemon, "_maybe_move_to_done"),
            patch.object(daemon, "_maybe_set_backlog"),
            patch.object(daemon.comment_processor, "process"),
        ):
            daemon._poll()

        # Should have moved to Research
        assert ("PVTI_123", "Research") in status_updates

    def test_daemon_yolo_backlog_blocked_by_non_allowed_user(self, mock_config, temp_workspace_dir):
        """Test YOLO mode does NOT move Backlog when yolo label added by non-allowed user."""
        mock_config.allowed_username = "allowed_user"
        daemon = Daemon(mock_config)

        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Backlog",
            title="Test Issue",
            labels={"yolo"},
        )

        status_updates = []

        def mock_update_status(item_id, new_status):
            status_updates.append((item_id, new_status))

        with (
            patch.object(daemon.ticket_client, "get_board_items", return_value=[item]),
            patch.object(daemon.ticket_client, "update_item_status", mock_update_status),
            patch.object(daemon.ticket_client, "get_label_actor", return_value="blocked_user"),
            patch.object(daemon, "_maybe_cleanup"),
            patch.object(daemon, "_maybe_archive_closed"),
            patch.object(daemon, "_maybe_move_to_done"),
            patch.object(daemon, "_maybe_set_backlog"),
            patch.object(daemon.comment_processor, "process"),
        ):
            daemon._poll()

        # Should NOT have moved to Research
        assert ("PVTI_123", "Research") not in status_updates

    def test_daemon_yolo_backlog_blocked_by_unknown_actor(self, mock_config, temp_workspace_dir):
        """Test YOLO mode does NOT move Backlog when yolo label actor cannot be determined."""
        mock_config.allowed_username = "allowed_user"
        daemon = Daemon(mock_config)

        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Backlog",
            title="Test Issue",
            labels={"yolo"},
        )

        status_updates = []

        def mock_update_status(item_id, new_status):
            status_updates.append((item_id, new_status))

        with (
            patch.object(daemon.ticket_client, "get_board_items", return_value=[item]),
            patch.object(daemon.ticket_client, "update_item_status", mock_update_status),
            patch.object(daemon.ticket_client, "get_label_actor", return_value=None),
            patch.object(daemon, "_maybe_cleanup"),
            patch.object(daemon, "_maybe_archive_closed"),
            patch.object(daemon, "_maybe_move_to_done"),
            patch.object(daemon, "_maybe_set_backlog"),
            patch.object(daemon.comment_processor, "process"),
        ):
            daemon._poll()

        # Should NOT have moved to Research
        assert ("PVTI_123", "Research") not in status_updates

    def test_daemon_yolo_starts_fresh_session_for_plan(self, mock_config, temp_workspace_dir):
        """Test YOLO mode Plan workflow starts fresh session (like all main workflows)."""
        daemon = Daemon(mock_config)

        # First create issue state (required for set_workflow_session_id)
        daemon.database.update_issue_state("owner/repo", 42, "Research")

        # Then store a Research session ID
        daemon.database.set_workflow_session_id(
            "owner/repo", 42, "Research", "research-session-123"
        )

        # Create item in Plan status with yolo label
        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Plan",
            title="Test Issue",
            labels={"yolo"},
        )

        resume_sessions = []

        def mock_runner_run(workflow, ctx, workflow_name, resume_session=None):
            resume_sessions.append(resume_session)
            return "new-session-456"

        worktree_path = daemon._get_worktree_path(item.repo, item.ticket_id)
        Path(worktree_path).mkdir(parents=True, exist_ok=True)

        with patch.object(daemon.runner, "run", mock_runner_run):
            daemon._run_workflow("Plan", item)

        # Should start fresh (no session resumption for main workflows)
        assert resume_sessions == [None]

    def test_daemon_yolo_failure_removes_label(self, mock_config, temp_workspace_dir):
        """Test YOLO mode removes yolo label on workflow failure."""
        daemon = Daemon(mock_config)

        # Create item in Research status with yolo label
        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
            labels={"yolo"},
        )

        label_calls = {"add": [], "remove": []}

        def mock_add_label(repo, issue, label, **kwargs):
            label_calls["add"].append(label)

        def mock_remove_label(repo, issue, label, **kwargs):
            label_calls["remove"].append(label)

        with (
            patch.object(daemon.ticket_client, "add_label", mock_add_label),
            patch.object(daemon.ticket_client, "remove_label", mock_remove_label),
            patch.object(daemon.ticket_client, "get_comments", return_value=[]),
            patch.object(daemon.runner, "run", side_effect=Exception("Workflow failed")),
        ):
            with pytest.raises(Exception):
                daemon._process_item_workflow(item)

        # yolo should be removed
        assert "yolo" in label_calls["remove"]

    def test_daemon_yolo_failure_adds_failed_label(self, mock_config, temp_workspace_dir):
        """Test YOLO mode adds yolo_failed label on workflow failure."""
        daemon = Daemon(mock_config)

        # Create item in Research status with yolo label
        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
            labels={"yolo"},
        )

        label_calls = {"add": [], "remove": []}

        def mock_add_label(repo, issue, label, **kwargs):
            label_calls["add"].append(label)

        def mock_remove_label(repo, issue, label, **kwargs):
            label_calls["remove"].append(label)

        with (
            patch.object(daemon.ticket_client, "add_label", mock_add_label),
            patch.object(daemon.ticket_client, "remove_label", mock_remove_label),
            patch.object(daemon.ticket_client, "get_comments", return_value=[]),
            patch.object(daemon.runner, "run", side_effect=Exception("Workflow failed")),
        ):
            with pytest.raises(Exception):
                daemon._process_item_workflow(item)

        # yolo_failed should be added
        assert "yolo_failed" in label_calls["add"]

    def test_daemon_yolo_no_effect_without_label(self, mock_config, temp_workspace_dir):
        """Test normal flow unchanged without yolo label."""
        daemon = Daemon(mock_config)

        # Create item in Research status WITHOUT yolo label (include research_ready to skip rebase)
        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
            labels={"research_ready"},  # No yolo label, research_ready skips rebase
        )

        status_updates = []

        def mock_update_status(item_id, new_status):
            status_updates.append((item_id, new_status))

        worktree_path = daemon._get_worktree_path(item.repo, item.ticket_id)
        Path(worktree_path).mkdir(parents=True, exist_ok=True)

        with (
            patch.object(daemon.ticket_client, "add_label"),
            patch.object(daemon.ticket_client, "remove_label"),
            patch.object(daemon.ticket_client, "update_item_status", mock_update_status),
            patch.object(daemon.ticket_client, "get_comments", return_value=[]),
            patch.object(daemon.runner, "run"),
        ):
            daemon._process_item_workflow(item)

        # Should NOT have advanced to Plan (no yolo label)
        assert ("PVTI_123", "Plan") not in status_updates

    def test_daemon_yolo_no_effect_on_implement(self, mock_config, temp_workspace_dir):
        """Test YOLO mode doesn't interfere with Implement's existing transition."""
        daemon = Daemon(mock_config)

        # Create item in Implement status with yolo label
        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Implement",
            title="Test Issue",
            labels={"yolo"},
        )

        status_updates = []

        def mock_update_status(item_id, new_status):
            status_updates.append((item_id, new_status))

        with (
            patch.object(daemon.ticket_client, "add_label"),
            patch.object(daemon.ticket_client, "remove_label"),
            patch.object(daemon.ticket_client, "update_item_status", mock_update_status),
            patch.object(daemon.ticket_client, "get_comments", return_value=[]),
            patch.object(daemon.runner, "run"),
        ):
            daemon._process_item_workflow(item)

        # Should have moved to Validate (existing next_status), NOT triggered YOLO path
        assert status_updates == [("PVTI_123", "Validate")]

    def test_daemon_stores_session_id_for_new_issue(self, mock_config, temp_workspace_dir):
        """Test that session ID is stored for a brand new issue entering Research.

        This tests the fix for the session resume logic bug: the issue state must
        be created BEFORE the workflow runs, so set_workflow_session_id() can store
        the session ID successfully.
        """
        daemon = Daemon(mock_config)

        # Create item in Research status (no prior state exists)
        # research_ready label skips rebase which would require a real git repo
        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=99,
            repo="owner/repo",
            status="Research",
            title="New Issue",
            labels={"research_ready"},
        )

        # Verify no state exists initially
        assert daemon.database.get_issue_state("owner/repo", 99) is None

        def mock_runner_run(workflow, ctx, workflow_name, resume_session=None):
            return "test-session-abc123"

        worktree_path = daemon._get_worktree_path(item.repo, item.ticket_id)
        Path(worktree_path).mkdir(parents=True, exist_ok=True)

        # Use _process_item_workflow which creates state BEFORE running workflow
        with (
            patch.object(daemon.runner, "run", mock_runner_run),
            patch.object(daemon.ticket_client, "add_label"),
            patch.object(daemon.ticket_client, "remove_label"),
            patch.object(daemon.ticket_client, "get_comments", return_value=[]),
        ):
            daemon._process_item_workflow(item)

        # Verify session ID was stored
        state = daemon.database.get_issue_state("owner/repo", 99)
        assert state is not None, "Issue state should exist after workflow"
        assert state.research_session_id == "test-session-abc123", (
            f"Session ID should be stored. Got: {state.research_session_id}"
        )

    # ========================================================================
    # Reset Label Tests
    # ========================================================================

    def test_daemon_reset_clears_content_and_moves_to_backlog(
        self, mock_config, temp_workspace_dir
    ):
        """Test reset label clears kiln content, removes labels, and moves to Backlog."""
        mock_config.allowed_username = "allowed_user"
        daemon = Daemon(mock_config)

        # Create item with reset and various workflow labels
        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="github.com/owner/repo",
            status="Plan",
            title="Test Issue",
            labels={"reset", "research_ready", "plan_ready"},
        )

        label_calls = {"remove": []}
        status_calls = []

        def mock_remove_label(repo, issue, label):
            label_calls["remove"].append(label)

        def mock_update_status(item_id, status):
            status_calls.append((item_id, status))

        with (
            patch.object(daemon.ticket_client, "get_board_items", return_value=[item]),
            patch.object(daemon.ticket_client, "remove_label", mock_remove_label),
            patch.object(daemon.ticket_client, "update_item_status", mock_update_status),
            patch.object(daemon.ticket_client, "get_label_actor", return_value="allowed_user"),
            patch.object(
                daemon.ticket_client,
                "get_ticket_body",
                return_value="Original description\n\n---\n<!-- kiln:research -->\nResearch content\n<!-- /kiln:research -->\n\n---\n<!-- kiln:plan -->\nPlan content\n<!-- /kiln:plan -->",
            ),
            patch("subprocess.run") as mock_subprocess,
            patch.object(daemon, "_maybe_cleanup"),
            patch.object(daemon, "_maybe_archive_closed"),
            patch.object(daemon, "_maybe_cleanup_closed"),
            patch.object(daemon, "_maybe_move_to_done"),
            patch.object(daemon, "_maybe_set_backlog"),
            patch.object(daemon.comment_processor, "process"),
            patch.object(daemon, "_should_trigger_workflow", return_value=False),
        ):
            daemon._poll()

        # reset label should be removed first
        assert "reset" in label_calls["remove"]
        # workflow labels should be removed
        assert "research_ready" in label_calls["remove"]
        assert "plan_ready" in label_calls["remove"]
        # item should be moved to Backlog
        assert ("PVTI_123", "Backlog") in status_calls

    def test_daemon_reset_works_on_any_status(self, mock_config, temp_workspace_dir):
        """Test reset label works on any status column."""
        mock_config.allowed_username = "allowed_user"
        daemon = Daemon(mock_config)

        # Test from Implement status
        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="github.com/owner/repo",
            status="Implement",
            title="Test Issue",
            labels={"reset", "implementing"},
        )

        label_calls = {"remove": []}
        status_calls = []

        def mock_remove_label(repo, issue, label):
            label_calls["remove"].append(label)

        def mock_update_status(item_id, status):
            status_calls.append((item_id, status))

        with (
            patch.object(daemon.ticket_client, "get_board_items", return_value=[item]),
            patch.object(daemon.ticket_client, "remove_label", mock_remove_label),
            patch.object(daemon.ticket_client, "update_item_status", mock_update_status),
            patch.object(daemon.ticket_client, "get_label_actor", return_value="allowed_user"),
            patch.object(daemon.ticket_client, "get_ticket_body", return_value="Just description"),
            patch.object(daemon, "_maybe_cleanup"),
            patch.object(daemon, "_maybe_archive_closed"),
            patch.object(daemon, "_maybe_cleanup_closed"),
            patch.object(daemon, "_maybe_move_to_done"),
            patch.object(daemon, "_maybe_set_backlog"),
            patch.object(daemon.comment_processor, "process"),
            patch.object(daemon, "_should_trigger_workflow", return_value=False),
        ):
            daemon._poll()

        # reset and implementing labels should be removed
        assert "reset" in label_calls["remove"]
        assert "implementing" in label_calls["remove"]
        # item should be moved to Backlog
        assert ("PVTI_123", "Backlog") in status_calls

    def test_daemon_reset_blocked_by_non_allowed_user(self, mock_config, temp_workspace_dir):
        """Test reset is blocked when label added by non-allowed user."""
        mock_config.allowed_username = "allowed_user"
        daemon = Daemon(mock_config)

        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="github.com/owner/repo",
            status="Research",
            title="Test Issue",
            labels={"reset", "research_ready"},
        )

        label_calls = {"remove": []}
        status_calls = []

        def mock_remove_label(repo, issue, label):
            label_calls["remove"].append(label)

        def mock_update_status(item_id, status):
            status_calls.append((item_id, status))

        with (
            patch.object(daemon.ticket_client, "get_board_items", return_value=[item]),
            patch.object(daemon.ticket_client, "remove_label", mock_remove_label),
            patch.object(daemon.ticket_client, "update_item_status", mock_update_status),
            patch.object(daemon.ticket_client, "get_label_actor", return_value="blocked_user"),
            patch.object(daemon, "_maybe_cleanup"),
            patch.object(daemon, "_maybe_archive_closed"),
            patch.object(daemon, "_maybe_cleanup_closed"),
            patch.object(daemon, "_maybe_move_to_done"),
            patch.object(daemon, "_maybe_set_backlog"),
            patch.object(daemon.comment_processor, "process"),
            patch.object(daemon, "_should_trigger_workflow", return_value=False),
        ):
            daemon._poll()

        # reset should be removed (to prevent repeated warnings)
        assert "reset" in label_calls["remove"]
        # research_ready should NOT be removed (blocked)
        assert "research_ready" not in label_calls["remove"]
        # should NOT be moved to Backlog
        assert len(status_calls) == 0

    def test_daemon_reset_blocked_by_unknown_actor(self, mock_config, temp_workspace_dir):
        """Test reset is blocked when label actor cannot be determined."""
        mock_config.allowed_username = "allowed_user"
        daemon = Daemon(mock_config)

        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="github.com/owner/repo",
            status="Research",
            title="Test Issue",
            labels={"reset", "research_ready"},
        )

        label_calls = {"remove": []}
        status_calls = []

        def mock_remove_label(repo, issue, label):
            label_calls["remove"].append(label)

        def mock_update_status(item_id, status):
            status_calls.append((item_id, status))

        with (
            patch.object(daemon.ticket_client, "get_board_items", return_value=[item]),
            patch.object(daemon.ticket_client, "remove_label", mock_remove_label),
            patch.object(daemon.ticket_client, "update_item_status", mock_update_status),
            patch.object(daemon.ticket_client, "get_label_actor", return_value=None),
            patch.object(daemon, "_maybe_cleanup"),
            patch.object(daemon, "_maybe_archive_closed"),
            patch.object(daemon, "_maybe_cleanup_closed"),
            patch.object(daemon, "_maybe_move_to_done"),
            patch.object(daemon, "_maybe_set_backlog"),
            patch.object(daemon.comment_processor, "process"),
            patch.object(daemon, "_should_trigger_workflow", return_value=False),
        ):
            daemon._poll()

        # When actor is unknown, reset label is NOT removed (for security logging)
        assert "reset" not in label_calls["remove"]
        # research_ready should NOT be removed (blocked)
        assert "research_ready" not in label_calls["remove"]
        # should NOT be moved to Backlog
        assert len(status_calls) == 0

    def test_daemon_reset_skips_closed_issues(self, mock_config, temp_workspace_dir):
        """Test reset label is ignored on closed issues."""
        mock_config.allowed_username = "allowed_user"
        daemon = Daemon(mock_config)

        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="github.com/owner/repo",
            status="Research",
            title="Test Issue",
            labels={"reset", "research_ready"},
            state="CLOSED",
        )

        label_calls = {"remove": []}
        status_calls = []

        def mock_remove_label(repo, issue, label):
            label_calls["remove"].append(label)

        def mock_update_status(item_id, status):
            status_calls.append((item_id, status))

        with (
            patch.object(daemon.ticket_client, "get_board_items", return_value=[item]),
            patch.object(daemon.ticket_client, "remove_label", mock_remove_label),
            patch.object(daemon.ticket_client, "update_item_status", mock_update_status),
            patch.object(daemon.ticket_client, "get_label_actor", return_value="allowed_user"),
            patch.object(daemon, "_maybe_cleanup"),
            patch.object(daemon, "_maybe_archive_closed"),
            patch.object(daemon, "_maybe_cleanup_closed"),
            patch.object(daemon, "_maybe_move_to_done"),
            patch.object(daemon, "_maybe_set_backlog"),
            patch.object(daemon.comment_processor, "process"),
            patch.object(daemon, "_should_trigger_workflow", return_value=False),
        ):
            daemon._poll()

        # Closed issues should not have labels removed
        assert "reset" not in label_calls["remove"]
        assert "research_ready" not in label_calls["remove"]
        # should NOT be moved to Backlog
        assert len(status_calls) == 0

    def test_clear_kiln_content_removes_research_and_plan_sections(
        self, mock_config, temp_workspace_dir
    ):
        """Test _clear_kiln_content removes kiln sections from issue body."""
        mock_config.allowed_username = "allowed_user"
        daemon = Daemon(mock_config)

        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="github.com/owner/repo",
            status="Plan",
            title="Test Issue",
            labels=set(),
        )

        original_body = """Original description here

---
<!-- kiln:research -->
## Research Findings

This is the research content.

<!-- /kiln:research -->

---
<!-- kiln:plan -->
## Implementation Plan

This is the plan content.

<!-- /kiln:plan -->"""

        expected_body = "Original description here"
        captured_body = []

        def mock_subprocess_run(args, **kwargs):
            if args[0:3] == ["gh", "issue", "edit"]:
                # Capture the body argument
                body_idx = args.index("--body") + 1
                captured_body.append(args[body_idx])
            return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        with (
            patch.object(daemon.ticket_client, "get_ticket_body", return_value=original_body),
            patch("subprocess.run", mock_subprocess_run),
        ):
            daemon._clear_kiln_content(item)

        assert len(captured_body) == 1
        assert captured_body[0] == expected_body

    def test_clear_kiln_content_no_change_when_no_kiln_sections(
        self, mock_config, temp_workspace_dir
    ):
        """Test _clear_kiln_content does nothing when there are no kiln sections."""
        mock_config.allowed_username = "allowed_user"
        daemon = Daemon(mock_config)

        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="github.com/owner/repo",
            status="Backlog",
            title="Test Issue",
            labels=set(),
        )

        original_body = "Just the original description with no kiln content."
        subprocess_called = []

        def mock_subprocess_run(args, **kwargs):
            subprocess_called.append(args)
            return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        with (
            patch.object(daemon.ticket_client, "get_ticket_body", return_value=original_body),
            patch("subprocess.run", mock_subprocess_run),
        ):
            daemon._clear_kiln_content(item)

        # subprocess should not be called if body didn't change
        assert len(subprocess_called) == 0


# ============================================================================
# GitHubTicketClient Label Method Tests
# ============================================================================


@pytest.mark.integration
class TestGitHubTicketClientLabelMethods:
    """Integration tests for GitHubTicketClient label methods."""

    def test_add_label_mocked(self, mock_gh_subprocess):
        """Test add_label uses REST API via gh issue edit."""
        client = GitHubTicketClient({"github.com": "test_token"})

        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.returncode = 0
        mock_gh_subprocess.return_value = mock_result

        client.add_label("owner/repo", 42, "researching")

        # Should make single call to gh issue edit
        assert mock_gh_subprocess.call_count == 1
        call_args = mock_gh_subprocess.call_args[0][0]
        assert "issue" in call_args
        assert "edit" in call_args
        assert "--add-label" in call_args
        assert "researching" in call_args

    def test_remove_label_mocked(self, mock_gh_subprocess):
        """Test remove_label uses REST API via gh issue edit."""
        client = GitHubTicketClient({"github.com": "test_token"})

        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.returncode = 0
        mock_gh_subprocess.return_value = mock_result

        client.remove_label("owner/repo", 42, "researching")

        # Should make single call to gh issue edit
        assert mock_gh_subprocess.call_count == 1
        call_args = mock_gh_subprocess.call_args[0][0]
        assert "issue" in call_args
        assert "edit" in call_args
        assert "--remove-label" in call_args
        assert "researching" in call_args

    def test_remove_label_handles_missing_label(self, mock_gh_subprocess):
        """Test remove_label handles label not on issue gracefully."""
        import subprocess

        client = GitHubTicketClient({"github.com": "test_token"})

        # Simulate gh failing when label doesn't exist
        mock_gh_subprocess.side_effect = subprocess.CalledProcessError(1, "gh")

        # Should not raise - just logs debug message
        client.remove_label("owner/repo", 42, "nonexistent-label")

        assert mock_gh_subprocess.call_count == 1


# ============================================================================
# Daemon Comment Processing Tests
# ============================================================================


@pytest.mark.integration
class TestDaemonIsKilnResponse:
    """Tests for CommentProcessor._is_kiln_response() helper method."""

    @pytest.fixture
    def daemon(self, temp_workspace_dir):
        """Create a daemon instance for testing."""
        config = MagicMock()
        config.poll_interval = 60
        config.watched_statuses = ["Research", "Plan"]
        config.max_concurrent_workflows = 2
        config.database_path = f"{temp_workspace_dir}/test.db"
        config.workspace_dir = temp_workspace_dir
        config.project_urls = []
        config.stage_models = {}

        with patch("src.ticket_clients.github.GitHubTicketClient"):
            daemon = Daemon(config)
            daemon.ticket_client = MagicMock()
            daemon.comment_processor.ticket_client = daemon.ticket_client
            yield daemon
            daemon.stop()

    def test_is_kiln_response_with_response_marker(self, daemon):
        """Test detection of kiln response comment with marker."""
        body = "<!-- kiln:response -->\nApplied changes to **plan**:\n```diff\n+new line\n```"
        assert daemon.comment_processor._is_kiln_response(body) is True

    def test_is_kiln_response_with_whitespace_prefix(self, daemon):
        """Test that leading whitespace is stripped before checking."""
        body = "   \n\n<!-- kiln:response -->\nContent"
        assert daemon.comment_processor._is_kiln_response(body) is True

    def test_is_kiln_response_returns_false_for_user_comment(self, daemon):
        """Test that regular user comments are not detected as kiln responses."""
        body = "I think we should also consider option B"
        assert daemon.comment_processor._is_kiln_response(body) is False

    def test_is_kiln_response_returns_false_for_kiln_post(self, daemon):
        """Test that kiln posts (research/plan) are not detected as responses."""
        body = "<!-- kiln:research -->\n## Research Findings\nContent here"
        assert daemon.comment_processor._is_kiln_response(body) is False

    def test_is_kiln_response_returns_false_for_marker_in_middle(self, daemon):
        """Test that marker in middle of comment doesn't match (must be at start)."""
        body = "Some text\n<!-- kiln:response -->\nMore text"
        assert daemon.comment_processor._is_kiln_response(body) is False


@pytest.mark.integration
class TestDaemonGenerateDiff:
    """Tests for CommentProcessor._generate_diff() helper method."""

    @pytest.fixture
    def daemon(self, temp_workspace_dir):
        """Create a daemon instance for testing."""
        config = MagicMock()
        config.poll_interval = 60
        config.watched_statuses = ["Research", "Plan"]
        config.max_concurrent_workflows = 2
        config.database_path = f"{temp_workspace_dir}/test.db"
        config.workspace_dir = temp_workspace_dir
        config.project_urls = []
        config.stage_models = {}

        with patch("src.ticket_clients.github.GitHubTicketClient"):
            daemon = Daemon(config)
            daemon.ticket_client = MagicMock()
            daemon.comment_processor.ticket_client = daemon.ticket_client
            yield daemon
            daemon.stop()

    def test_generate_diff_with_additions(self, daemon):
        """Test diff generation with added lines."""
        before = "Line 1\nLine 2"
        after = "Line 1\nLine 2\nLine 3"
        result = daemon.comment_processor._generate_diff(before, after, "plan")

        assert "+Line 3" in result
        assert "-Line 3" not in result

    def test_generate_diff_with_removals(self, daemon):
        """Test diff generation with removed lines."""
        before = "Line 1\nLine 2\nLine 3"
        after = "Line 1\nLine 3"
        result = daemon.comment_processor._generate_diff(before, after, "research")

        assert "-Line 2" in result

    def test_generate_diff_with_modifications(self, daemon):
        """Test diff generation with modified lines."""
        before = "Old content here"
        after = "New content here"
        result = daemon.comment_processor._generate_diff(before, after, "description")

        assert "-Old content here" in result
        assert "+New content here" in result

    def test_generate_diff_no_changes(self, daemon):
        """Test diff generation returns empty string when content is identical."""
        content = "Same content\nNo changes"
        result = daemon.comment_processor._generate_diff(content, content, "plan")

        assert result == ""

    def test_generate_diff_empty_before(self, daemon):
        """Test diff generation from empty content."""
        before = ""
        after = "New content"
        result = daemon.comment_processor._generate_diff(before, after, "research")

        assert "+New content" in result

    def test_generate_diff_empty_after(self, daemon):
        """Test diff generation to empty content."""
        before = "Old content"
        after = ""
        result = daemon.comment_processor._generate_diff(before, after, "plan")

        assert "-Old content" in result


@pytest.mark.integration
class TestDaemonResponseComments:
    """Tests for response comment posting in CommentProcessor.process()."""

    @pytest.fixture
    def daemon(self, temp_workspace_dir):
        """Create a daemon instance for testing."""
        config = MagicMock()
        config.poll_interval = 60
        config.watched_statuses = ["Research", "Plan"]
        config.max_concurrent_workflows = 2
        config.database_path = f"{temp_workspace_dir}/test.db"
        config.workspace_dir = temp_workspace_dir
        config.project_urls = []
        config.stage_models = {}
        config.allowed_username = "real-user"

        with patch("src.ticket_clients.github.GitHubTicketClient"):
            daemon = Daemon(config)
            daemon.ticket_client = MagicMock()
            daemon.comment_processor.ticket_client = daemon.ticket_client
            yield daemon
            daemon.stop()

    def test_process_comments_posts_response_with_diff(self, daemon):
        """Test that a response comment with diff is posted after processing."""
        from datetime import datetime

        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
        )

        daemon.database.update_issue_state(
            "owner/repo",
            42,
            "Research",
            last_processed_comment_timestamp="2024-01-15T10:00:00+00:00",
        )

        user_comment = Comment(
            id="IC_1",
            database_id=100,
            body="Please expand on option A",
            created_at=datetime(2024, 1, 15, 11, 0, 0, tzinfo=UTC),
            author="real-user",
            is_processed=False,
        )

        # Mock the response comment that will be created
        response_comment = Comment(
            id="IC_response",
            database_id=200,
            body="<!-- kiln:response -->\nApplied changes",
            created_at=datetime(2024, 1, 15, 11, 5, 0, tzinfo=UTC),
            author="kiln-bot",
            is_processed=False,
        )

        daemon.ticket_client.get_comments_since.return_value = [user_comment]
        daemon.ticket_client.add_comment.return_value = response_comment

        # Mock section extraction (before and after)
        with (
            patch.object(daemon.comment_processor, "_extract_section_content") as mock_extract,
            patch.object(daemon.runner, "run"),
        ):
            mock_extract.side_effect = ["Before content", "After content"]
            daemon.comment_processor.process(item)

            # Verify response comment was posted
            daemon.ticket_client.add_comment.assert_called_once()
            call_args = daemon.ticket_client.add_comment.call_args
            assert call_args[0][0] == "owner/repo"
            assert call_args[0][1] == 42
            # Check that response contains marker and diff
            response_body = call_args[0][2]
            assert "<!-- kiln:response -->" in response_body
            assert '<pre lang="diff">' in response_body

    def test_process_comments_response_contains_diff_marker(self, daemon):
        """Test that response comment body contains the kiln:response marker."""
        from datetime import datetime

        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Plan",
            title="Test Issue",
        )

        daemon.database.update_issue_state(
            "owner/repo", 42, "Plan", last_processed_comment_timestamp="2024-01-15T10:00:00+00:00"
        )

        user_comment = Comment(
            id="IC_1",
            database_id=100,
            body="Update the plan",
            created_at=datetime(2024, 1, 15, 11, 0, 0, tzinfo=UTC),
            author="real-user",
            is_processed=False,
        )

        response_comment = Comment(
            id="IC_response",
            database_id=200,
            body="<!-- kiln:response -->\nApplied changes",
            created_at=datetime(2024, 1, 15, 11, 5, 0, tzinfo=UTC),
            author="kiln-bot",
            is_processed=False,
        )

        daemon.ticket_client.get_comments_since.return_value = [user_comment]
        daemon.ticket_client.add_comment.return_value = response_comment

        with (
            patch.object(daemon.comment_processor, "_extract_section_content") as mock_extract,
            patch.object(daemon.runner, "run"),
        ):
            mock_extract.side_effect = ["Old plan", "Updated plan"]
            daemon.comment_processor.process(item)

            response_body = daemon.ticket_client.add_comment.call_args[0][2]
            assert response_body.lstrip().startswith("<!-- kiln:response -->")

    def test_process_comments_diff_escapes_html(self, daemon):
        """Test that HTML in diff content is escaped to prevent breaking the details block."""
        from datetime import datetime

        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Plan",
            title="Test Issue",
        )

        daemon.database.update_issue_state(
            "owner/repo", 42, "Plan", last_processed_comment_timestamp="2024-01-15T10:00:00+00:00"
        )

        user_comment = Comment(
            id="IC_1",
            database_id=100,
            body="Update the plan",
            created_at=datetime(2024, 1, 15, 11, 0, 0, tzinfo=UTC),
            author="real-user",
            is_processed=False,
        )

        response_comment = Comment(
            id="IC_response",
            database_id=200,
            body="<!-- kiln:response -->\nApplied changes",
            created_at=datetime(2024, 1, 15, 11, 5, 0, tzinfo=UTC),
            author="kiln-bot",
            is_processed=False,
        )

        daemon.ticket_client.get_comments_since.return_value = [user_comment]
        daemon.ticket_client.add_comment.return_value = response_comment

        with (
            patch.object(daemon.comment_processor, "_extract_section_content") as mock_extract,
            patch.object(daemon.runner, "run"),
        ):
            # Simulate a diff where the content contains HTML that could break the details block
            before_content = "Old content\n\n</details>\n\n---\n\n<details open>"
            after_content = "New content\n\n</details>\n\n---\n\n<details open>\nMore stuff"
            mock_extract.side_effect = [before_content, after_content]
            daemon.comment_processor.process(item)

            response_body = daemon.ticket_client.add_comment.call_args[0][2]
            # The HTML should be escaped so it doesn't break the outer <details> block
            assert "&lt;/details&gt;" in response_body
            assert "&lt;details open&gt;" in response_body
            # The raw HTML should NOT appear (would break formatting)
            assert "</details>\n\n---" not in response_body

    def test_process_comments_timestamp_updated_to_response(self, daemon):
        """Test that timestamp is updated to the response comment's timestamp."""
        from datetime import datetime

        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
        )

        daemon.database.update_issue_state(
            "owner/repo",
            42,
            "Research",
            last_processed_comment_timestamp="2024-01-15T10:00:00+00:00",
        )

        user_comment = Comment(
            id="IC_1",
            database_id=100,
            body="Feedback",
            created_at=datetime(2024, 1, 15, 11, 0, 0, tzinfo=UTC),
            author="real-user",
            is_processed=False,
        )

        # Response is created AFTER user comment
        response_comment = Comment(
            id="IC_response",
            database_id=300,
            body="<!-- kiln:response -->\nApplied changes",
            created_at=datetime(2024, 1, 15, 11, 30, 0, tzinfo=UTC),
            author="kiln-bot",
            is_processed=False,
        )

        daemon.ticket_client.get_comments_since.return_value = [user_comment]
        daemon.ticket_client.add_comment.return_value = response_comment

        with (
            patch.object(daemon.comment_processor, "_extract_section_content") as mock_extract,
            patch.object(daemon.runner, "run"),
        ):
            mock_extract.side_effect = ["Before", "After"]
            daemon.comment_processor.process(item)

        # Verify timestamp is set to response comment's timestamp (not user comment's)
        state = daemon.database.get_issue_state("owner/repo", 42)
        assert state.last_processed_comment_timestamp == "2024-01-15T11:30:00+00:00"

    def test_response_comments_are_filtered_out(self, daemon):
        """Test that kiln response comments are not processed as user feedback."""
        from datetime import datetime

        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
        )

        daemon.database.update_issue_state(
            "owner/repo",
            42,
            "Research",
            last_processed_comment_timestamp="2024-01-15T10:00:00+00:00",
        )

        # Only a kiln response comment - should be filtered out
        response_comment = Comment(
            id="IC_1",
            database_id=100,
            body="<!-- kiln:response -->\nApplied changes to **research**:\n```diff\n+new\n```",
            created_at=datetime(2024, 1, 15, 11, 0, 0, tzinfo=UTC),
            author="real-user",  # Even from a non-bot user
            is_processed=False,
        )

        daemon.ticket_client.get_comments_since.return_value = [response_comment]

        with patch.object(daemon.runner, "run") as mock_run:
            daemon.comment_processor.process(item)

            # Workflow should NOT be run (response comment filtered out)
            mock_run.assert_not_called()

    def test_process_comments_no_diff_message(self, daemon):
        """Test that message is posted when no textual changes are detected."""
        from datetime import datetime

        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Plan",
            title="Test Issue",
        )

        daemon.database.update_issue_state(
            "owner/repo", 42, "Plan", last_processed_comment_timestamp="2024-01-15T10:00:00+00:00"
        )

        user_comment = Comment(
            id="IC_1",
            database_id=100,
            body="Make a small formatting change",
            created_at=datetime(2024, 1, 15, 11, 0, 0, tzinfo=UTC),
            author="real-user",
            is_processed=False,
        )

        response_comment = Comment(
            id="IC_response",
            database_id=200,
            body="<!-- kiln:response -->\nNo changes",
            created_at=datetime(2024, 1, 15, 11, 5, 0, tzinfo=UTC),
            author="kiln-bot",
            is_processed=False,
        )

        daemon.ticket_client.get_comments_since.return_value = [user_comment]
        daemon.ticket_client.add_comment.return_value = response_comment

        # Same content before and after (no diff)
        with (
            patch.object(daemon.comment_processor, "_extract_section_content") as mock_extract,
            patch.object(daemon.runner, "run"),
        ):
            mock_extract.side_effect = ["Same content", "Same content"]
            daemon.comment_processor.process(item)

            response_body = daemon.ticket_client.add_comment.call_args[0][2]
            assert "<!-- kiln:response -->" in response_body
            assert "No textual changes detected" in response_body


@pytest.mark.integration
class TestDaemonIsKilnPost:
    """Tests for CommentProcessor._is_kiln_post() helper method."""

    @pytest.fixture
    def daemon(self, temp_workspace_dir):
        """Create a daemon instance for testing."""
        config = MagicMock()
        config.poll_interval = 60
        config.watched_statuses = ["Research", "Plan"]
        config.max_concurrent_workflows = 2
        config.database_path = f"{temp_workspace_dir}/test.db"
        config.workspace_dir = temp_workspace_dir
        config.project_urls = []
        config.stage_models = {}

        with patch("src.ticket_clients.github.GitHubTicketClient"):
            daemon = Daemon(config)
            daemon.ticket_client = MagicMock()
            daemon.comment_processor.ticket_client = daemon.ticket_client
            yield daemon
            daemon.stop()

    def test_is_kiln_post_with_research_marker(self, daemon):
        """Test detection of research post with HTML marker."""
        body = "<!-- kiln:research -->\n## Research Findings\nContent here"
        markers = tuple(daemon.comment_processor.KILN_POST_MARKERS.values())

        assert daemon.comment_processor._is_kiln_post(body, markers) is True

    def test_is_kiln_post_with_plan_marker(self, daemon):
        """Test detection of plan post with HTML marker."""
        body = "<!-- kiln:plan -->\n## Implementation Plan\nContent here"
        markers = tuple(daemon.comment_processor.KILN_POST_MARKERS.values())

        assert daemon.comment_processor._is_kiln_post(body, markers) is True

    def test_is_kiln_post_with_legacy_research_marker(self, daemon):
        """Test detection of legacy research post."""
        body = "## Research Findings\n\nSome research content"
        markers = tuple(daemon.comment_processor.KILN_POST_LEGACY_MARKERS.values())

        assert daemon.comment_processor._is_kiln_post(body, markers) is True

    def test_is_kiln_post_with_legacy_plan_marker(self, daemon):
        """Test detection of legacy plan post."""
        body = "## Implementation Plan:\n\nStep 1..."
        markers = tuple(daemon.comment_processor.KILN_POST_LEGACY_MARKERS.values())

        assert daemon.comment_processor._is_kiln_post(body, markers) is True

    def test_is_kiln_post_with_whitespace_prefix(self, daemon):
        """Test that leading whitespace is stripped before checking."""
        body = "   \n\n<!-- kiln:research -->\nContent"
        markers = tuple(daemon.comment_processor.KILN_POST_MARKERS.values())

        assert daemon.comment_processor._is_kiln_post(body, markers) is True

    def test_is_kiln_post_returns_false_for_user_comment(self, daemon):
        """Test that regular user comments are not detected as kiln posts."""
        body = "I think we should also consider option B"
        markers = tuple(daemon.comment_processor.KILN_POST_MARKERS.values()) + tuple(
            daemon.comment_processor.KILN_POST_LEGACY_MARKERS.values()
        )

        assert daemon.comment_processor._is_kiln_post(body, markers) is False

    def test_is_kiln_post_returns_false_for_marker_in_middle(self, daemon):
        """Test that marker in middle of comment doesn't match (must be at start)."""
        body = "Some text\n<!-- kiln:research -->\nMore text"
        markers = tuple(daemon.comment_processor.KILN_POST_MARKERS.values())

        assert daemon.comment_processor._is_kiln_post(body, markers) is False


@pytest.mark.integration
class TestDaemonInitializeCommentTimestamp:
    """Tests for CommentProcessor._initialize_comment_timestamp() method."""

    @pytest.fixture
    def daemon(self, temp_workspace_dir):
        """Create a daemon instance for testing."""
        config = MagicMock()
        config.poll_interval = 60
        config.watched_statuses = ["Research", "Plan"]
        config.max_concurrent_workflows = 2
        config.database_path = f"{temp_workspace_dir}/test.db"
        config.workspace_dir = temp_workspace_dir
        config.project_urls = []
        config.stage_models = {}

        with patch("src.ticket_clients.github.GitHubTicketClient"):
            daemon = Daemon(config)
            daemon.ticket_client = MagicMock()
            daemon.comment_processor.ticket_client = daemon.ticket_client
            yield daemon
            daemon.stop()

    def test_initialize_returns_none_for_empty_comments(self, daemon):
        """Test that empty comment list returns None."""

        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
        )

        result = daemon.comment_processor._initialize_comment_timestamp(item, [])
        assert result is None

    def test_initialize_finds_kiln_post_timestamp(self, daemon):
        """Test that kiln post timestamp is returned."""
        from datetime import datetime

        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
        )

        comments = [
            Comment(
                id="IC_1",
                database_id=100,
                body="User question",
                created_at=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
                author="user1",
                is_processed=False,
            ),
            Comment(
                id="IC_2",
                database_id=200,
                body="<!-- kiln:research -->\n## Research\nFindings here<!-- /kiln -->",
                created_at=datetime(2024, 1, 15, 11, 0, 0, tzinfo=UTC),
                author="kiln-bot",
                is_processed=False,
            ),
        ]

        result = daemon.comment_processor._initialize_comment_timestamp(item, comments)
        assert result == "2024-01-15T11:00:00+00:00"

    def test_initialize_finds_thumbs_up_comment_timestamp(self, daemon):
        """Test that already-processed (thumbs up) comment timestamp is returned."""
        from datetime import datetime

        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
        )

        comments = [
            Comment(
                id="IC_1",
                database_id=100,
                body="Old feedback",
                created_at=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
                author="user1",
                is_processed=True,  # Already processed
            ),
            Comment(
                id="IC_2",
                database_id=200,
                body="New feedback",
                created_at=datetime(2024, 1, 15, 11, 0, 0, tzinfo=UTC),
                author="user2",
                is_processed=False,  # Not yet processed
            ),
        ]

        # Should return the thumbs-up comment (newest processed)
        result = daemon.comment_processor._initialize_comment_timestamp(item, comments)
        assert result == "2024-01-15T10:00:00+00:00"

    def test_initialize_prefers_newest_processed_comment(self, daemon):
        """Test that the newest kiln/thumbs-up comment is selected."""
        from datetime import datetime

        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Plan",
            title="Test Issue",
        )

        comments = [
            Comment(
                id="IC_1",
                database_id=100,
                body="<!-- kiln:research -->\nResearch<!-- /kiln -->",
                created_at=datetime(2024, 1, 15, 9, 0, 0, tzinfo=UTC),
                author="kiln-bot",
                is_processed=False,
            ),
            Comment(
                id="IC_2",
                database_id=200,
                body="Processed feedback",
                created_at=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
                author="user1",
                is_processed=True,
            ),
            Comment(
                id="IC_3",
                database_id=300,
                body="<!-- kiln:plan -->\nPlan<!-- /kiln -->",
                created_at=datetime(2024, 1, 15, 11, 0, 0, tzinfo=UTC),
                author="kiln-bot",
                is_processed=False,
            ),
        ]

        # Should return the newest kiln post (plan)
        result = daemon.comment_processor._initialize_comment_timestamp(item, comments)
        assert result == "2024-01-15T11:00:00+00:00"

    def test_initialize_returns_none_when_no_processed_comments(self, daemon):
        """Test that None is returned when no kiln posts or thumbs-up comments exist."""
        from datetime import datetime

        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
        )

        comments = [
            Comment(
                id="IC_1",
                database_id=100,
                body="Just a regular comment",
                created_at=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
                author="user1",
                is_processed=False,
            ),
        ]

        result = daemon.comment_processor._initialize_comment_timestamp(item, comments)
        assert result is None


@pytest.mark.integration
class TestDaemonProcessCommentsForItem:
    """Tests for CommentProcessor.process() method."""

    @pytest.fixture
    def daemon(self, temp_workspace_dir):
        """Create a daemon instance for testing."""
        config = MagicMock()
        config.poll_interval = 60
        config.watched_statuses = ["Research", "Plan"]
        config.max_concurrent_workflows = 2
        config.database_path = f"{temp_workspace_dir}/test.db"
        config.workspace_dir = temp_workspace_dir
        config.project_urls = []
        config.stage_models = {}
        config.allowed_username = "real-user"

        with patch("src.ticket_clients.github.GitHubTicketClient"):
            daemon = Daemon(config)
            daemon.ticket_client = MagicMock()
            daemon.comment_processor.ticket_client = daemon.ticket_client
            yield daemon
            daemon.stop()

    def test_process_comments_skips_bot_comments(self, daemon):
        """Test that bot comments are filtered out."""
        from datetime import datetime

        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
        )

        # Set up stored state with a timestamp
        daemon.database.update_issue_state(
            "owner/repo",
            42,
            "Research",
            last_processed_comment_timestamp="2024-01-15T10:00:00+00:00",
        )

        # Bot comments should be filtered
        bot_comments = [
            Comment(
                id="IC_1",
                database_id=100,
                body="Automated message",
                created_at=datetime(2024, 1, 15, 11, 0, 0, tzinfo=UTC),
                author="github-actions[bot]",
                is_processed=False,
            ),
            Comment(
                id="IC_2",
                database_id=200,
                body="Kiln status update",
                created_at=datetime(2024, 1, 15, 11, 30, 0, tzinfo=UTC),
                author="kiln-bot",
                is_processed=False,
            ),
        ]

        daemon.ticket_client.get_comments_since.return_value = bot_comments
        daemon.ticket_client.find_kiln_comment.return_value = None

        # Should not call add_reaction (no user comments to process)
        daemon.comment_processor.process(item)
        daemon.ticket_client.add_reaction.assert_not_called()

    def test_process_comments_skips_kiln_posts(self, daemon):
        """Test that kiln-generated posts are filtered out."""
        from datetime import datetime

        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
        )

        daemon.database.update_issue_state(
            "owner/repo",
            42,
            "Research",
            last_processed_comment_timestamp="2024-01-15T10:00:00+00:00",
        )

        # Kiln posts should be filtered even if from a different author
        kiln_posts = [
            Comment(
                id="IC_1",
                database_id=100,
                body="<!-- kiln:research -->\n## Research\nFindings<!-- /kiln -->",
                created_at=datetime(2024, 1, 15, 11, 0, 0, tzinfo=UTC),
                author="some-user",  # Even non-bot author
                is_processed=False,
            ),
        ]

        daemon.ticket_client.get_comments_since.return_value = kiln_posts
        daemon.ticket_client.find_kiln_comment.return_value = None

        daemon.comment_processor.process(item)
        daemon.ticket_client.add_reaction.assert_not_called()

    def test_process_comments_processes_user_feedback(self, daemon):
        """Test that valid user comments trigger workflow and get thumbs up."""
        from datetime import datetime

        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
        )

        daemon.database.update_issue_state(
            "owner/repo",
            42,
            "Research",
            last_processed_comment_timestamp="2024-01-15T10:00:00+00:00",
        )

        user_comment = Comment(
            id="IC_1",
            database_id=100,
            body="Please add more detail about option A",
            created_at=datetime(2024, 1, 15, 11, 0, 0, tzinfo=UTC),
            author="real-user",
            is_processed=False,
        )

        daemon.ticket_client.get_comments_since.return_value = [user_comment]
        daemon.ticket_client.find_kiln_comment.return_value = None

        with patch.object(daemon.runner, "run") as mock_run:
            daemon.comment_processor.process(item)

            # Should have run the workflow
            mock_run.assert_called_once()
            # Should have added eyes (processing) and thumbs up (done) reactions
            calls = daemon.ticket_client.add_reaction.call_args_list
            assert call("IC_1", "EYES", repo="owner/repo") in calls
            assert call("IC_1", "THUMBS_UP", repo="owner/repo") in calls

    def test_process_comments_updates_timestamp_after_processing(self, daemon):
        """Test that last_processed_comment_timestamp is updated to response comment's timestamp."""
        from datetime import datetime

        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
        )

        daemon.database.update_issue_state(
            "owner/repo",
            42,
            "Research",
            last_processed_comment_timestamp="2024-01-15T10:00:00+00:00",
        )

        user_comment = Comment(
            id="IC_1",
            database_id=100,
            body="User feedback",
            created_at=datetime(2024, 1, 15, 11, 30, 0, tzinfo=UTC),
            author="real-user",
            is_processed=False,
        )

        # Response comment is created after user comment
        response_comment = Comment(
            id="IC_response",
            database_id=200,
            body="<!-- kiln:response -->\nApplied changes",
            created_at=datetime(2024, 1, 15, 11, 35, 0, tzinfo=UTC),
            author="kiln-bot",
            is_processed=False,
        )

        daemon.ticket_client.get_comments_since.return_value = [user_comment]
        daemon.ticket_client.find_kiln_comment.return_value = None
        daemon.ticket_client.add_comment.return_value = response_comment

        with (
            patch.object(daemon.comment_processor, "_extract_section_content") as mock_extract,
            patch.object(daemon.runner, "run"),
        ):
            mock_extract.side_effect = ["Before", "After"]
            daemon.comment_processor.process(item)

        # Check that timestamp was updated to response comment's timestamp
        state = daemon.database.get_issue_state("owner/repo", 42)
        assert state.last_processed_comment_timestamp == "2024-01-15T11:35:00+00:00"

    def test_process_comments_skips_already_processed_thumbs_up(self, daemon):
        """Test that comments with thumbs-up reactions (already processed) are filtered out.

        This is critical: GitHub's 'since' API returns comments >= timestamp (inclusive),
        so we may get back comments we've already processed. The thumbs-up reaction
        serves as a marker that the comment was already handled.
        """
        from datetime import datetime

        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Plan",
            title="Test Issue",
        )

        daemon.database.update_issue_state(
            "owner/repo", 42, "Plan", last_processed_comment_timestamp="2024-01-15T10:00:00+00:00"
        )

        # Mix of already-processed (has thumbs up) and new comments
        # All comments must be from allowed_username ("real-user") to pass the filter
        comments = [
            Comment(
                id="IC_1",
                database_id=100,
                body="Old feedback already processed",
                created_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
                author="real-user",
                is_processed=True,  # Already processed!
            ),
            Comment(
                id="IC_2",
                database_id=200,
                body="Another old one",
                created_at=datetime(2024, 1, 15, 10, 45, 0, tzinfo=UTC),
                author="real-user",
                is_processed=True,  # Already processed!
            ),
            Comment(
                id="IC_3",
                database_id=300,
                body="New feedback to process",
                created_at=datetime(2024, 1, 15, 11, 0, 0, tzinfo=UTC),
                author="real-user",
                is_processed=False,  # NOT processed yet
            ),
        ]

        daemon.ticket_client.get_comments_since.return_value = comments
        daemon.ticket_client.find_kiln_comment.return_value = MagicMock(body="<!-- kiln:plan -->")

        with patch.object(daemon.runner, "run") as mock_run:
            daemon.comment_processor.process(item)

            # Should only process the ONE comment without thumbs up
            mock_run.assert_called_once()
            # Should only react to the new comment (eyes then thumbs up)
            calls = daemon.ticket_client.add_reaction.call_args_list
            assert call("IC_3", "EYES", repo="owner/repo") in calls
            assert call("IC_3", "THUMBS_UP", repo="owner/repo") in calls
            # Should NOT have reacted to already-processed comments
            assert call("IC_1", "EYES") not in calls
            assert call("IC_2", "EYES") not in calls

    def test_process_comments_skips_all_when_all_have_thumbs_up(self, daemon):
        """Test that no processing happens when all comments already have thumbs-up."""
        from datetime import datetime

        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
        )

        daemon.database.update_issue_state(
            "owner/repo",
            42,
            "Research",
            last_processed_comment_timestamp="2024-01-15T10:00:00+00:00",
        )

        # All comments already processed
        comments = [
            Comment(
                id="IC_1",
                database_id=100,
                body="Old feedback",
                created_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
                author="user1",
                is_processed=True,
            ),
            Comment(
                id="IC_2",
                database_id=200,
                body="More old feedback",
                created_at=datetime(2024, 1, 15, 10, 45, 0, tzinfo=UTC),
                author="user2",
                is_processed=True,
            ),
        ]

        daemon.ticket_client.get_comments_since.return_value = comments

        with patch.object(daemon.runner, "run") as mock_run:
            daemon.comment_processor.process(item)

            # Should NOT run any workflow
            mock_run.assert_not_called()
            # Should NOT add any reactions
            daemon.ticket_client.add_reaction.assert_not_called()

    def test_process_comments_skips_comments_with_eyes_reaction(self, daemon):
        """Test that comments with eyes reaction (being processed by another thread) are filtered out.

        The eyes reaction indicates another daemon thread has already picked up the comment
        and is currently processing it. This prevents duplicate processing.
        """
        from datetime import datetime

        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
        )

        daemon.database.update_issue_state(
            "owner/repo",
            42,
            "Research",
            last_processed_comment_timestamp="2024-01-15T10:00:00+00:00",
        )

        # Mix of comments being processed (has eyes) and new comments
        # All comments must be from allowed_username ("real-user") to pass the filter
        comments = [
            Comment(
                id="IC_1",
                database_id=100,
                body="Comment being processed by another thread",
                created_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
                author="real-user",
                is_processed=False,
                is_processing=True,  # Being processed by another thread!
            ),
            Comment(
                id="IC_2",
                database_id=200,
                body="New comment to process",
                created_at=datetime(2024, 1, 15, 11, 0, 0, tzinfo=UTC),
                author="real-user",
                is_processed=False,
                is_processing=False,  # Not yet picked up
            ),
        ]

        daemon.ticket_client.get_comments_since.return_value = comments
        daemon.ticket_client.find_kiln_comment.return_value = MagicMock(
            body="<!-- kiln:research -->"
        )

        with patch.object(daemon.runner, "run") as mock_run:
            daemon.comment_processor.process(item)

            # Should run workflow once (only for the comment without eyes)
            mock_run.assert_called_once()
            # Should only react to the new comment (eyes then thumbs up)
            calls = daemon.ticket_client.add_reaction.call_args_list
            assert call("IC_2", "EYES", repo="owner/repo") in calls
            assert call("IC_2", "THUMBS_UP", repo="owner/repo") in calls
            # Should NOT have reacted to comment being processed by another thread
            assert call("IC_1", "EYES") not in calls
            assert call("IC_1", "THUMBS_UP") not in calls

    def test_process_comments_skips_all_when_all_have_eyes(self, daemon):
        """Test that no processing happens when all comments have eyes reaction."""
        from datetime import datetime

        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Plan",
            title="Test Issue",
        )

        daemon.database.update_issue_state(
            "owner/repo", 42, "Plan", last_processed_comment_timestamp="2024-01-15T10:00:00+00:00"
        )

        # All comments being processed by other threads
        comments = [
            Comment(
                id="IC_1",
                database_id=100,
                body="Being processed",
                created_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
                author="user1",
                is_processed=False,
                is_processing=True,
            ),
            Comment(
                id="IC_2",
                database_id=200,
                body="Also being processed",
                created_at=datetime(2024, 1, 15, 10, 45, 0, tzinfo=UTC),
                author="user2",
                is_processed=False,
                is_processing=True,
            ),
        ]

        daemon.ticket_client.get_comments_since.return_value = comments

        with patch.object(daemon.runner, "run") as mock_run:
            daemon.comment_processor.process(item)

            # Should NOT run any workflow
            mock_run.assert_not_called()
            # Should NOT add any reactions
            daemon.ticket_client.add_reaction.assert_not_called()

    def test_process_comments_merges_multiple_comments(self, daemon):
        """Test that multiple comments are merged with later ones taking precedence."""
        from datetime import datetime

        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Plan",
            title="Test Issue",
        )

        daemon.database.update_issue_state(
            "owner/repo", 42, "Plan", last_processed_comment_timestamp="2024-01-15T10:00:00+00:00"
        )

        # Multiple comments to merge
        # All comments must be from allowed_username ("real-user") to pass the filter
        comments = [
            Comment(
                id="IC_1",
                database_id=100,
                body="Use approach A",
                created_at=datetime(2024, 1, 15, 11, 0, 0, tzinfo=UTC),
                author="real-user",
                is_processed=False,
            ),
            Comment(
                id="IC_2",
                database_id=200,
                body="Actually, use approach B instead",
                created_at=datetime(2024, 1, 15, 11, 30, 0, tzinfo=UTC),
                author="real-user",
                is_processed=False,
            ),
        ]

        daemon.ticket_client.get_comments_since.return_value = comments
        daemon.ticket_client.find_kiln_comment.return_value = MagicMock(body="<!-- kiln:plan -->")

        with patch.object(daemon.runner, "run") as mock_run:
            daemon.comment_processor.process(item)

            # Should run workflow once with merged comments
            mock_run.assert_called_once()

            # Check the context passed to the workflow
            call_args = mock_run.call_args
            workflow = call_args[0][0]  # First positional arg
            context = call_args[0][1]  # Second positional arg

            # The merged body should contain both comments with guidance
            assert "Multiple user comments" in context.comment_body
            assert "prefer the LATER comments" in context.comment_body
            assert "Use approach A" in context.comment_body
            assert "Actually, use approach B instead" in context.comment_body
            assert "[Comment 1 of 2]" in context.comment_body
            assert "[Comment 2 of 2]" in context.comment_body

            # Should add eyes and thumbs up to ALL comments
            calls = daemon.ticket_client.add_reaction.call_args_list
            assert call("IC_1", "EYES", repo="owner/repo") in calls
            assert call("IC_2", "EYES", repo="owner/repo") in calls
            assert call("IC_1", "THUMBS_UP", repo="owner/repo") in calls
            assert call("IC_2", "THUMBS_UP", repo="owner/repo") in calls


@pytest.mark.unit
class TestDaemonEnsureRequiredLabels:
    """Tests for Daemon._ensure_required_labels()."""

    @pytest.fixture
    def mock_config(self, temp_workspace_dir):
        """Fixture providing mock Config object."""
        from src.config import Config

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        config = Config(
            github_token="test_token",
            project_urls=["https://github.com/orgs/test/projects/1"],
            workspace_dir=temp_workspace_dir,
            database_path=db_path,
            poll_interval=60,
            watched_statuses=["Prepare", "Research", "Plan", "Implement"],
        )

        yield config

        Path(db_path).unlink(missing_ok=True)

    def test_ensure_required_labels_creates_missing(self, mock_config):
        """Test that missing labels are created."""
        daemon = Daemon(mock_config)

        # Simulate repo with only some labels
        existing_labels = ["bug", "enhancement"]

        with (
            patch.object(daemon.ticket_client, "get_repo_labels", return_value=existing_labels),
            patch.object(
                daemon.ticket_client, "create_repo_label", return_value=True
            ) as mock_create,
        ):
            daemon._ensure_required_labels("owner/repo")

            # Should create all required labels (none exist)
            assert mock_create.call_count == len(REQUIRED_LABELS)

            # Verify each required label was created
            created_labels = [call_args[0][1] for call_args in mock_create.call_args_list]
            for label_name in REQUIRED_LABELS:
                assert label_name in created_labels

    def test_ensure_required_labels_skips_existing(self, mock_config):
        """Test that existing labels are not recreated."""
        daemon = Daemon(mock_config)

        # Simulate repo already has some required labels
        existing_labels = ["researching", "research_ready", "planning"]

        with (
            patch.object(daemon.ticket_client, "get_repo_labels", return_value=existing_labels),
            patch.object(
                daemon.ticket_client, "create_repo_label", return_value=True
            ) as mock_create,
        ):
            daemon._ensure_required_labels("owner/repo")

            # Should only create the missing labels
            created_labels = [call_args[0][1] for call_args in mock_create.call_args_list]
            assert "researching" not in created_labels
            assert "research_ready" not in created_labels
            assert "planning" not in created_labels
            assert "plan_ready" in created_labels
            assert "implementing" in created_labels
            assert "cleaned_up" in created_labels

    def test_ensure_required_labels_all_exist(self, mock_config):
        """Test that no labels are created when all exist."""
        daemon = Daemon(mock_config)

        # All required labels already exist
        existing_labels = list(REQUIRED_LABELS.keys())

        with (
            patch.object(daemon.ticket_client, "get_repo_labels", return_value=existing_labels),
            patch.object(
                daemon.ticket_client, "create_repo_label", return_value=True
            ) as mock_create,
        ):
            daemon._ensure_required_labels("owner/repo")

            # No labels should be created
            mock_create.assert_not_called()

    def test_ensure_required_labels_passes_description_and_color(self, mock_config):
        """Test that labels are created with correct description and color."""
        daemon = Daemon(mock_config)

        with (
            patch.object(daemon.ticket_client, "get_repo_labels", return_value=[]),
            patch.object(
                daemon.ticket_client, "create_repo_label", return_value=True
            ) as mock_create,
        ):
            daemon._ensure_required_labels("owner/repo")

            # Find the call for "researching" label and verify params
            for call_args in mock_create.call_args_list:
                if call_args[0][1] == "researching":
                    assert call_args[1]["description"] == "Research workflow in progress"
                    assert call_args[1]["color"] == "FFA500"  # Orange for in-progress
                    break
            else:
                pytest.fail("researching label not created")

    def test_ensure_required_labels_includes_editing(self, mock_config):
        """Test that editing label is included in required labels."""
        # Verify editing label is in REQUIRED_LABELS (imported from src.labels)
        assert Labels.EDITING in REQUIRED_LABELS
        assert REQUIRED_LABELS[Labels.EDITING]["description"] == "Processing user comment"
        assert REQUIRED_LABELS[Labels.EDITING]["color"] == "1D76DB"  # Blue

    def test_ensure_required_labels_includes_reviewing(self, mock_config):
        """Test that reviewing label is included in required labels."""
        assert Labels.REVIEWING in REQUIRED_LABELS
        assert REQUIRED_LABELS[Labels.REVIEWING]["description"] == "PR under internal review"
        assert REQUIRED_LABELS[Labels.REVIEWING]["color"] == "1D76DB"  # Blue


@pytest.mark.unit
class TestDaemonInitializeProjectMetadataMultiRepo:
    """Tests for multi-repo label initialization in _initialize_project_metadata()."""

    @pytest.fixture
    def mock_config(self, temp_workspace_dir):
        """Fixture providing mock Config object."""
        from src.config import Config

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        config = Config(
            github_token="test_token",
            project_urls=["https://github.com/orgs/test/projects/1"],
            workspace_dir=temp_workspace_dir,
            database_path=db_path,
            poll_interval=60,
            watched_statuses=["Prepare", "Research", "Plan", "Implement"],
        )

        yield config

        Path(db_path).unlink(missing_ok=True)

    def test_initialize_ensures_labels_in_all_repos(self, mock_config):
        """Test that labels are created in all repos with project items."""
        daemon = Daemon(mock_config)

        # Create mock project items from multiple repos
        items = [
            TicketItem(
                item_id="item1",
                board_url="https://github.com/orgs/test/projects/1",
                ticket_id=1,
                repo="owner/repo-a",
                status="Research",
                title="Issue 1",
            ),
            TicketItem(
                item_id="item2",
                board_url="https://github.com/orgs/test/projects/1",
                ticket_id=2,
                repo="owner/repo-b",
                status="Plan",
                title="Issue 2",
            ),
            TicketItem(
                item_id="item3",
                board_url="https://github.com/orgs/test/projects/1",
                ticket_id=3,
                repo="owner/repo-a",
                status="Research",
                title="Issue 3",
            ),
        ]

        repos_called = []

        def track_ensure_labels(repo):
            repos_called.append(repo)

        with (
            patch.object(daemon.ticket_client, "get_board_items", return_value=items),
            patch.object(daemon.ticket_client, "get_board_metadata", return_value={}),
            patch.object(daemon, "_ensure_required_labels", side_effect=track_ensure_labels),
        ):
            daemon._initialize_project_metadata()

            # Both repos should have labels created
            assert "owner/repo-a" in repos_called
            assert "owner/repo-b" in repos_called
            # Each repo should only be called once (deduplication works)
            assert repos_called.count("owner/repo-a") == 1
            assert repos_called.count("owner/repo-b") == 1

    def test_always_fetches_fresh_metadata(self, mock_config):
        """Test that metadata is always fetched fresh, never using stale cache."""
        from src.database import ProjectMetadata

        daemon = Daemon(mock_config)

        # Pre-populate cache with stale metadata
        stale_metadata = ProjectMetadata(
            project_url="https://github.com/orgs/test/projects/1",
            repo="owner/repo-a",
            project_id="stale_project",
            status_field_id="stale_field",
            status_options={"Research": "stale_opt1", "Plan": "stale_opt2"},
        )
        daemon.database.upsert_project_metadata(stale_metadata)

        # Items include two repos
        items = [
            TicketItem(
                item_id="item1",
                board_url="https://github.com/orgs/test/projects/1",
                ticket_id=1,
                repo="owner/repo-a",
                status="Research",
                title="Issue 1",
            ),
            TicketItem(
                item_id="item2",
                board_url="https://github.com/orgs/test/projects/1",
                ticket_id=2,
                repo="owner/repo-b",
                status="Plan",
                title="Issue 2",
            ),
        ]

        # Fresh metadata from GitHub
        fresh_metadata = {
            "project_id": "fresh_project",
            "status_field_id": "fresh_field",
            "status_options": {"Research": "fresh_opt1", "Plan": "fresh_opt2"},
        }

        repos_called = []

        def track_ensure_labels(repo):
            repos_called.append(repo)

        with (
            patch.object(daemon.ticket_client, "get_board_items", return_value=items),
            patch.object(
                daemon.ticket_client, "get_board_metadata", return_value=fresh_metadata
            ) as mock_fetch,
            patch.object(daemon, "_ensure_required_labels", side_effect=track_ensure_labels),
        ):
            daemon._initialize_project_metadata()

            # get_board_metadata should always be called (not skipped due to cache)
            mock_fetch.assert_called_once()

            # Both repos should have labels ensured
            assert "owner/repo-a" in repos_called
            assert "owner/repo-b" in repos_called

            # In-memory cache should have fresh data, not stale cache
            metadata = daemon._project_metadata.get("https://github.com/orgs/test/projects/1")
            assert metadata is not None
            assert metadata.project_id == "fresh_project"
            assert metadata.status_field_id == "fresh_field"
            assert metadata.status_options == {
                "Research": "fresh_opt1",
                "Plan": "fresh_opt2",
            }


@pytest.mark.unit
class TestDaemonEditingLabel:
    """Tests for editing label during comment processing."""

    @pytest.fixture
    def mock_config(self, temp_workspace_dir):
        """Fixture providing mock Config object."""
        from src.config import Config

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        config = Config(
            github_token="test_token",
            project_urls=["https://github.com/orgs/test/projects/1"],
            workspace_dir=temp_workspace_dir,
            database_path=db_path,
            poll_interval=60,
            watched_statuses=["Prepare", "Research", "Plan", "Implement"],
            allowed_username="testuser",
        )

        yield config

        Path(db_path).unlink(missing_ok=True)

    def test_editing_label_added_during_comment_processing(self, mock_config, temp_workspace_dir):
        """Test that editing label is added when processing comments."""
        from datetime import datetime

        daemon = Daemon(mock_config)

        # Create test item
        item = TicketItem(
            item_id="item1",
            ticket_id=42,
            title="Test Issue",
            status="Research",
            repo="owner/repo",
            board_url="https://github.com/orgs/test/projects/1",
            labels=set(),
            comment_count=1,
        )

        # Create test comment
        test_comment = Comment(
            id="comment_node_id",
            database_id=123,
            body="Please update the research",
            created_at=datetime.now(UTC),
            author="testuser",
            is_processed=False,
        )

        # Create worktree directory
        worktree_path = Path(temp_workspace_dir) / "repo-issue-42"
        worktree_path.mkdir(parents=True)

        # Track label operations
        label_ops = []

        def mock_add_label(repo, issue, label, **kwargs):
            label_ops.append(("add", label))

        def mock_remove_label(repo, issue, label, **kwargs):
            label_ops.append(("remove", label))

        with (
            patch.object(daemon.database, "get_issue_state", return_value=None),
            patch.object(daemon.ticket_client, "get_comments", return_value=[]),
            patch.object(daemon.ticket_client, "get_comments_since", return_value=[test_comment]),
            patch.object(daemon.ticket_client, "add_label", side_effect=mock_add_label),
            patch.object(daemon.ticket_client, "remove_label", side_effect=mock_remove_label),
            patch.object(daemon.ticket_client, "add_reaction"),
            patch.object(daemon.ticket_client, "add_comment", return_value=test_comment),
            patch.object(daemon.database, "update_issue_state"),
            patch.object(daemon.comment_processor, "_apply_comment_to_kiln_post"),
            patch.object(daemon.comment_processor, "_extract_section_content", return_value=""),
        ):
            daemon.comment_processor.process(item)

        # Verify editing label was added then removed
        assert ("add", "editing") in label_ops
        assert ("remove", "editing") in label_ops
        # Verify add happened before remove
        add_idx = label_ops.index(("add", "editing"))
        remove_idx = label_ops.index(("remove", "editing"))
        assert add_idx < remove_idx

    def test_editing_label_removed_on_error(self, mock_config, temp_workspace_dir):
        """Test that editing label is removed even if processing fails."""
        from datetime import datetime

        daemon = Daemon(mock_config)

        item = TicketItem(
            item_id="item1",
            ticket_id=42,
            title="Test Issue",
            status="Research",
            repo="owner/repo",
            board_url="https://github.com/orgs/test/projects/1",
            labels=set(),
            comment_count=1,
        )

        test_comment = Comment(
            id="comment_node_id",
            database_id=123,
            body="Please update the research",
            created_at=datetime.now(UTC),
            author="testuser",
            is_processed=False,
        )

        worktree_path = Path(temp_workspace_dir) / "repo-issue-42"
        worktree_path.mkdir(parents=True)

        label_ops = []

        def mock_add_label(repo, issue, label, **kwargs):
            label_ops.append(("add", label))

        def mock_remove_label(repo, issue, label, **kwargs):
            label_ops.append(("remove", label))

        with (
            patch.object(daemon.database, "get_issue_state", return_value=None),
            patch.object(daemon.ticket_client, "get_comments", return_value=[]),
            patch.object(daemon.ticket_client, "get_comments_since", return_value=[test_comment]),
            patch.object(daemon.ticket_client, "add_label", side_effect=mock_add_label),
            patch.object(daemon.ticket_client, "remove_label", side_effect=mock_remove_label),
            patch.object(daemon.ticket_client, "add_reaction"),
            patch.object(
                daemon.comment_processor,
                "_apply_comment_to_kiln_post",
                side_effect=Exception("Simulated error"),
            ),
            patch.object(daemon.comment_processor, "_extract_section_content", return_value=""),
        ):
            daemon.comment_processor.process(item)

        # Verify editing label was still removed despite error
        assert ("add", "editing") in label_ops
        assert ("remove", "editing") in label_ops


# ============================================================================
# Daemon Move-to-Done Tests
# ============================================================================


class TestDaemonMaybeMoveToDone:
    """Tests for Daemon._maybe_move_to_done() method."""

    @pytest.fixture
    def mock_config(self, temp_workspace_dir):
        """Fixture providing mock Config object."""
        from src.config import Config

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        config = Config(
            github_token="test_token",
            project_urls=["https://github.com/orgs/test/projects/1"],
            workspace_dir=temp_workspace_dir,
            database_path=db_path,
            poll_interval=60,
            watched_statuses=["Research", "Plan", "Implement"],
        )

        yield config

        Path(db_path).unlink(missing_ok=True)

    def test_moves_validate_with_merged_pr_and_closed(self, mock_config):
        """Test that Validate + merged PR + closed moves to Done."""
        daemon = Daemon(mock_config)

        item = TicketItem(
            item_id="ITEM_1",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="test/repo",
            status="Validate",
            title="Test Issue",
            has_merged_changes=True,
            state="CLOSED",
            state_reason="COMPLETED",
        )

        with patch.object(daemon.ticket_client, "update_item_status") as mock_update:
            daemon._maybe_move_to_done(item)
            mock_update.assert_called_once_with("ITEM_1", "Done")

    def test_skips_validate_without_merged_pr(self, mock_config):
        """Test that Validate without merged PR is skipped."""
        daemon = Daemon(mock_config)

        item = TicketItem(
            item_id="ITEM_1",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="test/repo",
            status="Validate",
            title="Test Issue",
            has_merged_changes=False,
            state="CLOSED",
        )

        with patch.object(daemon.ticket_client, "update_item_status") as mock_update:
            daemon._maybe_move_to_done(item)
            mock_update.assert_not_called()

    def test_skips_validate_with_merged_pr_but_open(self, mock_config):
        """Test that Validate + merged PR but still open is skipped."""
        daemon = Daemon(mock_config)

        item = TicketItem(
            item_id="ITEM_1",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="test/repo",
            status="Validate",
            title="Test Issue",
            has_merged_changes=True,
            state="OPEN",
        )

        with patch.object(daemon.ticket_client, "update_item_status") as mock_update:
            daemon._maybe_move_to_done(item)
            mock_update.assert_not_called()

    def test_moves_from_any_status_with_merged_pr_and_closed(self, mock_config):
        """Test that any status with merged PR + closed + COMPLETED moves to Done."""
        daemon = Daemon(mock_config)

        for status in ["Backlog", "Research", "Plan", "Implement", "Validate"]:
            item = TicketItem(
                item_id="ITEM_1",
                board_url="https://github.com/orgs/test/projects/1",
                ticket_id=42,
                repo="test/repo",
                status=status,
                title="Test Issue",
                has_merged_changes=True,
                state="CLOSED",
                state_reason="COMPLETED",
            )

            with patch.object(daemon.ticket_client, "update_item_status") as mock_update:
                daemon._maybe_move_to_done(item)
                mock_update.assert_called_once_with("ITEM_1", "Done")

    def test_skips_already_done_status(self, mock_config):
        """Test that items already in Done are skipped."""
        daemon = Daemon(mock_config)

        item = TicketItem(
            item_id="ITEM_1",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="test/repo",
            status="Done",
            title="Test Issue",
            has_merged_changes=True,
            state="CLOSED",
        )

        with patch.object(daemon.ticket_client, "update_item_status") as mock_update:
            daemon._maybe_move_to_done(item)
            mock_update.assert_not_called()

    def test_skips_non_completed_issues(self, mock_config):
        """Test that non-COMPLETED issues are skipped (handled by archive)."""
        daemon = Daemon(mock_config)

        # Test NOT_PLANNED
        item = TicketItem(
            item_id="ITEM_1",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="test/repo",
            status="Implement",
            title="Test Issue",
            has_merged_changes=True,
            state="CLOSED",
            state_reason="NOT_PLANNED",
        )

        with patch.object(daemon.ticket_client, "update_item_status") as mock_update:
            daemon._maybe_move_to_done(item)
            mock_update.assert_not_called()

        # Test DUPLICATE
        item_dup = TicketItem(
            item_id="ITEM_2",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=43,
            repo="test/repo",
            status="Implement",
            title="Test Issue",
            has_merged_changes=True,
            state="CLOSED",
            state_reason="DUPLICATE",
        )

        with patch.object(daemon.ticket_client, "update_item_status") as mock_update:
            daemon._maybe_move_to_done(item_dup)
            mock_update.assert_not_called()

        # Test manual close (null state_reason)
        item_manual = TicketItem(
            item_id="ITEM_3",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=44,
            repo="test/repo",
            status="Implement",
            title="Test Issue",
            has_merged_changes=True,
            state="CLOSED",
            state_reason=None,
        )

        with patch.object(daemon.ticket_client, "update_item_status") as mock_update:
            daemon._maybe_move_to_done(item_manual)
            mock_update.assert_not_called()


# ============================================================================
# Daemon Set-to-Backlog Tests
# ============================================================================


class TestDaemonMaybeSetBacklog:
    """Tests for Daemon._maybe_set_backlog() method."""

    @pytest.fixture
    def mock_config(self, temp_workspace_dir):
        """Fixture providing mock Config object."""
        from src.config import Config

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        config = Config(
            github_token="test_token",
            project_urls=["https://github.com/orgs/test/projects/1"],
            workspace_dir=temp_workspace_dir,
            database_path=db_path,
            poll_interval=60,
            watched_statuses=["Research", "Plan", "Implement"],
        )

        yield config

        Path(db_path).unlink(missing_ok=True)

    def test_sets_unknown_status_to_backlog(self, mock_config):
        """Test that Unknown status gets set to Backlog."""
        daemon = Daemon(mock_config)

        item = TicketItem(
            item_id="ITEM_1",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="test/repo",
            status="Unknown",
            title="Test Issue",
        )

        with patch.object(daemon.ticket_client, "update_item_status") as mock_update:
            daemon._maybe_set_backlog(item)
            mock_update.assert_called_once_with("ITEM_1", "Backlog")

    def test_skips_closed_issues(self, mock_config):
        """Test that closed issues with Unknown status are skipped."""
        daemon = Daemon(mock_config)

        item = TicketItem(
            item_id="ITEM_1",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="test/repo",
            status="Unknown",
            title="Test Issue",
            state="CLOSED",
        )

        with patch.object(daemon.ticket_client, "update_item_status") as mock_update:
            daemon._maybe_set_backlog(item)
            mock_update.assert_not_called()

    def test_skips_items_with_status(self, mock_config):
        """Test that items with existing status are skipped."""
        daemon = Daemon(mock_config)

        item = TicketItem(
            item_id="ITEM_1",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="test/repo",
            status="Research",
            title="Test Issue",
        )

        with patch.object(daemon.ticket_client, "update_item_status") as mock_update:
            daemon._maybe_set_backlog(item)
            mock_update.assert_not_called()


@pytest.mark.integration
class TestDaemonBackoff:
    """Tests for daemon exponential backoff behavior using tenacity."""

    @pytest.fixture
    def mock_config(self, temp_workspace_dir):
        """Fixture providing mock Config object."""
        from src.config import Config

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        config = Config(
            github_token="test_token",
            project_urls=["https://github.com/orgs/test/projects/1"],
            workspace_dir=temp_workspace_dir,
            database_path=db_path,
            poll_interval=60,
            watched_statuses=["Research", "Plan", "Implement"],
        )

        yield config

        Path(db_path).unlink(missing_ok=True)

    @pytest.fixture
    def daemon(self, mock_config):
        """Fixture providing Daemon with mocked dependencies."""
        daemon = Daemon(mock_config)
        daemon.ticket_client = MagicMock()
        # Also update the ticket_client reference in comment_processor
        daemon.comment_processor.ticket_client = daemon.ticket_client
        yield daemon
        daemon.stop()

    def test_backoff_increases_on_consecutive_failures(self, daemon):
        """Test that backoff increases exponentially on failures using tenacity."""
        wait_timeouts = []

        # Mock Event.wait to track timeout values and return False (not interrupted)
        def mock_wait(timeout=None):
            wait_timeouts.append(timeout)
            return False  # Not interrupted

        # Fail twice then request shutdown on the second failure
        call_count = [0]

        def mock_poll():
            call_count[0] += 1
            if call_count[0] >= 2:
                daemon._shutdown_requested = True
            raise Exception("Simulated failure")

        with (
            patch.object(daemon, "_poll", side_effect=mock_poll),
            patch.object(daemon, "_initialize_project_metadata"),
            patch.object(daemon._shutdown_event, "wait", mock_wait),
        ):
            daemon.run()

        # First failure: 2^1 = 2 seconds backoff
        # Second failure: 2^2 = 4 seconds backoff (then shutdown detected on loop check)
        # Uses Event.wait with the full timeout (not 1-second loops)
        assert wait_timeouts == [2.0, 4.0]

    def test_backoff_resets_on_success(self, daemon):
        """Test that consecutive failure count resets after successful poll."""
        wait_timeouts = []

        def mock_wait(timeout=None):
            wait_timeouts.append(timeout)
            return False  # Not interrupted

        # Fail once, succeed, fail once, then shutdown on the third failure
        call_count = [0]

        def mock_poll():
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("First failure")
            elif call_count[0] == 2:
                pass  # Success
            elif call_count[0] == 3:
                daemon._shutdown_requested = True
                raise Exception("Third call failure triggers shutdown")

        with (
            patch.object(daemon, "_poll", side_effect=mock_poll),
            patch.object(daemon, "_initialize_project_metadata"),
            patch.object(daemon._shutdown_event, "wait", mock_wait),
        ):
            daemon.run()

        # First failure: 2s backoff (consecutive_failures=1)
        # Success: 60s poll interval wait (consecutive_failures reset to 0)
        # Third failure: 2s backoff (consecutive_failures=1, reset after success)
        assert wait_timeouts == [2.0, 60, 2.0]

    def test_backoff_caps_at_maximum(self, daemon):
        """Test that backoff caps at 300 seconds using tenacity."""
        wait_timeouts = []

        call_count = [0]

        def mock_poll():
            call_count[0] += 1
            # Shutdown on the 10th call to get exactly 10 backoffs
            if call_count[0] >= 10:
                daemon._shutdown_requested = True
            raise Exception("Simulated failure")

        def mock_wait(timeout=None):
            wait_timeouts.append(timeout)
            return False  # Not interrupted

        with (
            patch.object(daemon, "_poll", side_effect=mock_poll),
            patch.object(daemon, "_initialize_project_metadata"),
            patch.object(daemon._shutdown_event, "wait", mock_wait),
        ):
            daemon.run()

        # Expected backoffs: 2, 4, 8, 16, 32, 64, 128, 256, 300, 300
        # (2^1 through 2^8=256, then capped at 300 by tenacity for 2^9=512 and beyond)
        expected = [2.0, 4.0, 8.0, 16.0, 32.0, 64.0, 128.0, 256.0, 300.0, 300.0]
        assert wait_timeouts == expected

    def test_backoff_interruptible_for_shutdown(self, daemon):
        """Test that backoff sleep is interruptible during shutdown via Event."""
        wait_count = [0]

        def mock_poll():
            raise Exception("Always fail")

        def mock_wait(timeout=None):
            wait_count[0] += 1
            # Return True on first wait to indicate shutdown was signaled
            return True

        with (
            patch.object(daemon, "_poll", side_effect=mock_poll),
            patch.object(daemon, "_initialize_project_metadata"),
            patch.object(daemon._shutdown_event, "wait", mock_wait),
        ):
            daemon.run()

        # Should have only 1 wait call before shutdown was detected
        assert wait_count[0] == 1


# ============================================================================
# Daemon Cleanup for Closed Issues Tests
# ============================================================================


class TestDaemonMaybeCleanupClosed:
    """Tests for Daemon._maybe_cleanup_closed() method."""

    @pytest.fixture
    def mock_config(self, temp_workspace_dir):
        """Fixture providing mock Config object."""
        from src.config import Config

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        config = Config(
            github_token="test_token",
            project_urls=["https://github.com/orgs/test/projects/1"],
            workspace_dir=temp_workspace_dir,
            database_path=db_path,
            poll_interval=60,
            watched_statuses=["Research", "Plan", "Implement"],
        )

        yield config

        Path(db_path).unlink(missing_ok=True)

    def test_cleans_up_closed_issue_with_worktree(self, mock_config, temp_workspace_dir):
        """Test that closed issues with worktrees get cleaned up."""
        daemon = Daemon(mock_config)

        # Create a fake worktree directory
        worktree_path = Path(temp_workspace_dir) / "repo-issue-42"
        worktree_path.mkdir(parents=True)
        (worktree_path / "test_file.txt").write_text("test")

        item = TicketItem(
            item_id="ITEM_1",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
            state="CLOSED",
            labels=set(),
        )

        with (
            patch.object(daemon.workspace_manager, "cleanup_workspace") as mock_cleanup,
            patch.object(daemon.ticket_client, "add_label") as mock_add_label,
        ):
            daemon._maybe_cleanup_closed(item)
            mock_cleanup.assert_called_once_with("repo", 42)
            mock_add_label.assert_called_once_with("owner/repo", 42, "cleaned_up")

    def test_skips_open_issues(self, mock_config):
        """Test that open issues are not cleaned up."""
        daemon = Daemon(mock_config)

        item = TicketItem(
            item_id="ITEM_1",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
            state="OPEN",
            labels=set(),
        )

        with (
            patch.object(daemon.workspace_manager, "cleanup_workspace") as mock_cleanup,
            patch.object(daemon.ticket_client, "add_label") as mock_add_label,
        ):
            daemon._maybe_cleanup_closed(item)
            mock_cleanup.assert_not_called()
            mock_add_label.assert_not_called()

    def test_skips_already_cleaned_up(self, mock_config):
        """Test that issues with cleaned_up label are skipped."""
        daemon = Daemon(mock_config)

        item = TicketItem(
            item_id="ITEM_1",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
            state="CLOSED",
            labels={"cleaned_up"},
        )

        with (
            patch.object(daemon.workspace_manager, "cleanup_workspace") as mock_cleanup,
            patch.object(daemon.ticket_client, "add_label") as mock_add_label,
        ):
            daemon._maybe_cleanup_closed(item)
            mock_cleanup.assert_not_called()
            mock_add_label.assert_not_called()

    def test_adds_label_even_when_no_worktree(self, mock_config):
        """Test that cleaned_up label is added even if no worktree exists."""
        daemon = Daemon(mock_config)

        item = TicketItem(
            item_id="ITEM_1",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
            state="CLOSED",
            labels=set(),
        )

        # No worktree exists (default temp_workspace_dir is empty)
        with (
            patch.object(daemon.workspace_manager, "cleanup_workspace") as mock_cleanup,
            patch.object(daemon.ticket_client, "add_label") as mock_add_label,
        ):
            daemon._maybe_cleanup_closed(item)
            mock_cleanup.assert_not_called()  # No worktree to clean
            mock_add_label.assert_called_once_with("owner/repo", 42, "cleaned_up")

    def test_handles_not_planned_issues(self, mock_config, temp_workspace_dir):
        """Test that NOT_PLANNED closed issues are also cleaned up."""
        daemon = Daemon(mock_config)

        # Create a fake worktree directory
        worktree_path = Path(temp_workspace_dir) / "repo-issue-42"
        worktree_path.mkdir(parents=True)

        item = TicketItem(
            item_id="ITEM_1",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
            state="CLOSED",
            state_reason="NOT_PLANNED",
            labels=set(),
        )

        with (
            patch.object(daemon.workspace_manager, "cleanup_workspace") as mock_cleanup,
            patch.object(daemon.ticket_client, "add_label") as mock_add_label,
        ):
            daemon._maybe_cleanup_closed(item)
            mock_cleanup.assert_called_once_with("repo", 42)
            mock_add_label.assert_called_once()

    def test_handles_cleanup_failure_gracefully(self, mock_config, temp_workspace_dir):
        """Test that cleanup failures don't prevent label from being added."""
        daemon = Daemon(mock_config)

        # Create a fake worktree directory
        worktree_path = Path(temp_workspace_dir) / "repo-issue-42"
        worktree_path.mkdir(parents=True)

        item = TicketItem(
            item_id="ITEM_1",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
            state="CLOSED",
            labels=set(),
        )

        with (
            patch.object(
                daemon.workspace_manager,
                "cleanup_workspace",
                side_effect=Exception("Cleanup error"),
            ) as mock_cleanup,
            patch.object(daemon.ticket_client, "add_label") as mock_add_label,
        ):
            daemon._maybe_cleanup_closed(item)
            mock_cleanup.assert_called_once()
            # Label should still be added even after cleanup failure
            mock_add_label.assert_called_once_with("owner/repo", 42, "cleaned_up")


# ============================================================================
# Daemon GitHub Connection Validation Tests
# ============================================================================


@pytest.mark.integration
@pytest.mark.skip_auto_mock_validation
class TestDaemonValidateGitHubConnections:
    """Tests for Daemon._validate_github_connections() method."""

    @pytest.fixture
    def mock_config(self, temp_workspace_dir):
        """Fixture providing mock Config object."""
        from src.config import Config

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        config = Config(
            github_token="test_token",
            project_urls=["https://github.com/orgs/test/projects/1"],
            workspace_dir=temp_workspace_dir,
            database_path=db_path,
            poll_interval=60,
            watched_statuses=["Research", "Plan", "Implement"],
        )

        yield config

        Path(db_path).unlink(missing_ok=True)

    def test_validates_github_com_on_startup(self, mock_config):
        """Test that github.com connection is validated on daemon init."""
        mock_config.project_urls = ["https://github.com/orgs/test/projects/1"]

        with patch.object(GitHubTicketClient, "validate_connection") as mock_validate:
            daemon = Daemon(mock_config)
            # Verify validate_connection was called for github.com
            mock_validate.assert_called_once_with("github.com")
            daemon.stop()

    def test_validates_unique_hosts_only(self, mock_config):
        """Test that duplicate hosts are only validated once."""
        mock_config.project_urls = [
            "https://github.com/orgs/test1/projects/1",
            "https://github.com/orgs/test2/projects/2",
            "https://github.com/orgs/test3/projects/3",
        ]

        validated_hosts = []

        def track_validation(hostname):
            validated_hosts.append(hostname)
            return True

        with patch.object(GitHubTicketClient, "validate_connection", side_effect=track_validation):
            daemon = Daemon(mock_config)
            # github.com should only be validated once
            assert validated_hosts == ["github.com"]
            daemon.stop()

    def test_raises_on_validation_failure(self, mock_config):
        """Test that RuntimeError from validation propagates."""
        mock_config.project_urls = ["https://github.com/orgs/test/projects/1"]

        with patch.object(
            GitHubTicketClient,
            "validate_connection",
            side_effect=RuntimeError("Authentication failed"),
        ):
            with pytest.raises(RuntimeError, match="Authentication failed"):
                Daemon(mock_config)

    def test_validation_called_before_poll(self, mock_config):
        """Test that validation happens during init, before any polling."""
        mock_config.project_urls = ["https://github.com/orgs/test/projects/1"]

        call_order = []

        def track_validate(hostname):
            call_order.append("validate")
            return True

        with patch.object(GitHubTicketClient, "validate_connection", side_effect=track_validate):
            daemon = Daemon(mock_config)
            # Validation should happen during __init__
            assert "validate" in call_order
            daemon.stop()

    def test_handles_empty_project_urls(self, mock_config):
        """Test graceful handling when no project URLs configured."""
        mock_config.project_urls = []

        with patch.object(GitHubTicketClient, "validate_connection") as mock_validate:
            daemon = Daemon(mock_config)
            # Should not call validate_connection when no URLs
            mock_validate.assert_not_called()
            daemon.stop()

    def test_handles_invalid_url_format(self, mock_config):
        """Test that invalid URLs are skipped during validation."""
        mock_config.project_urls = [
            "not-a-url",
            "https://github.com/orgs/test/projects/1",
        ]

        validated_hosts = []

        def track_validation(hostname):
            validated_hosts.append(hostname)
            return True

        with patch.object(GitHubTicketClient, "validate_connection", side_effect=track_validation):
            daemon = Daemon(mock_config)
            # Only valid URL should be validated
            assert validated_hosts == ["github.com"]
            daemon.stop()
