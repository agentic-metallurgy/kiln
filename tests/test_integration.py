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

        # Standard org format
        hostname, entity_type, login, num = client._parse_board_url(
            "https://github.com/orgs/chronoboost/projects/6/views/2"
        )
        assert hostname == "github.com"
        assert entity_type == "organization"
        assert login == "chronoboost"
        assert num == 6

        # Without views part
        hostname, entity_type, login, num = client._parse_board_url(
            "https://github.com/orgs/myorg/projects/42"
        )
        assert hostname == "github.com"
        assert entity_type == "organization"
        assert login == "myorg"
        assert num == 42

        # With trailing slash
        hostname, entity_type, login, num = client._parse_board_url(
            "https://github.com/orgs/test-org/projects/123/views/1/"
        )
        assert hostname == "github.com"
        assert entity_type == "organization"
        assert login == "test-org"
        assert num == 123

        # User project
        hostname, entity_type, login, num = client._parse_board_url(
            "https://github.com/users/myuser/projects/5"
        )
        assert hostname == "github.com"
        assert entity_type == "user"
        assert login == "myuser"
        assert num == 5

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
# Daemon Clear Kiln Content Tests
# ============================================================================


@pytest.mark.integration
class TestDaemonClearKilnContent:
    """Tests for Daemon._clear_kiln_content() method."""

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
            yield daemon
            daemon.stop()

    def test_clear_kiln_content_legacy_research_marker(self, daemon):
        """Test clearing research block with legacy end marker <!-- /kiln -->."""
        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            title="Test Issue",
            repo="github.com/owner/repo",
            status="Research",
        )

        original_description = "This is the issue description."
        research_content = """
---
<!-- kiln:research -->
## Research Findings
Some research content here.
<!-- /kiln -->"""
        body_with_legacy_research = original_description + research_content

        daemon.ticket_client.get_ticket_body.return_value = body_with_legacy_research

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            daemon._clear_kiln_content(item)

            # Verify subprocess was called with cleaned body
            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            assert "gh" in call_args
            assert "issue" in call_args
            assert "edit" in call_args
            assert "--body" in call_args

            # Get the body that was passed to gh issue edit
            body_index = call_args.index("--body") + 1
            cleaned_body = call_args[body_index]

            # Verify research content was removed
            assert "kiln:research" not in cleaned_body
            assert "Research Findings" not in cleaned_body
            assert "<!-- /kiln -->" not in cleaned_body
            # Verify original description is preserved
            assert original_description in cleaned_body

    def test_clear_kiln_content_legacy_plan_marker(self, daemon):
        """Test clearing plan block with legacy end marker <!-- /kiln -->."""
        item = TicketItem(
            item_id="PVI_456",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=99,
            title="Test Issue with Plan",
            repo="github.com/owner/repo",
            status="Plan",
        )

        original_description = "My original issue description."
        plan_content = """
---
<!-- kiln:plan -->
## Implementation Plan
Step 1: Do something
Step 2: Do another thing
<!-- /kiln -->"""
        body_with_legacy_plan = original_description + plan_content

        daemon.ticket_client.get_ticket_body.return_value = body_with_legacy_plan

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            daemon._clear_kiln_content(item)

            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            body_index = call_args.index("--body") + 1
            cleaned_body = call_args[body_index]

            # Verify plan content was removed
            assert "kiln:plan" not in cleaned_body
            assert "Implementation Plan" not in cleaned_body
            assert "<!-- /kiln -->" not in cleaned_body
            # Verify original description is preserved
            assert original_description in cleaned_body

    def test_clear_kiln_content_mixed_markers(self, daemon):
        """Test clearing content with both legacy and new-style markers."""
        item = TicketItem(
            item_id="PVI_789",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=101,
            title="Test Issue with Mixed Markers",
            repo="github.com/owner/repo",
            status="Plan",
        )

        original_description = "Original description here."
        # Research with legacy end marker
        research_content = """
---
<!-- kiln:research -->
## Research
Research findings.
<!-- /kiln -->"""
        # Plan with new-style end marker
        plan_content = """
---
<!-- kiln:plan -->
## Plan
Implementation steps.
<!-- /kiln:plan -->"""

        body_with_mixed = original_description + research_content + plan_content

        daemon.ticket_client.get_ticket_body.return_value = body_with_mixed

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            daemon._clear_kiln_content(item)

            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            body_index = call_args.index("--body") + 1
            cleaned_body = call_args[body_index]

            # Verify both research and plan content were removed
            assert "kiln:research" not in cleaned_body
            assert "kiln:plan" not in cleaned_body
            assert "Research findings" not in cleaned_body
            assert "Implementation steps" not in cleaned_body
            assert "<!-- /kiln -->" not in cleaned_body
            assert "<!-- /kiln:plan -->" not in cleaned_body
            # Verify original description is preserved
            assert original_description in cleaned_body

    def test_clear_kiln_content_legacy_research_no_separator(self, daemon):
        """Test clearing research block with legacy marker but no separator."""
        item = TicketItem(
            item_id="PVI_111",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=55,
            title="Test Issue",
            repo="github.com/owner/repo",
            status="Research",
        )

        original_description = "Description without separator."
        # Research without --- separator
        research_content = """
<!-- kiln:research -->
## Research
Content here.
<!-- /kiln -->"""
        body = original_description + research_content

        daemon.ticket_client.get_ticket_body.return_value = body

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            daemon._clear_kiln_content(item)

            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            body_index = call_args.index("--body") + 1
            cleaned_body = call_args[body_index]

            # Verify research content was removed
            assert "kiln:research" not in cleaned_body
            assert "Content here" not in cleaned_body
            # Verify original description is preserved
            assert original_description in cleaned_body

    def test_clear_kiln_content_legacy_plan_no_separator(self, daemon):
        """Test clearing plan block with legacy marker but no separator."""
        item = TicketItem(
            item_id="PVI_222",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=66,
            title="Test Issue",
            repo="github.com/owner/repo",
            status="Plan",
        )

        original_description = "Another description."
        # Plan without --- separator
        plan_content = """
<!-- kiln:plan -->
## Plan
Plan steps here.
<!-- /kiln -->"""
        body = original_description + plan_content

        daemon.ticket_client.get_ticket_body.return_value = body

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            daemon._clear_kiln_content(item)

            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            body_index = call_args.index("--body") + 1
            cleaned_body = call_args[body_index]

            # Verify plan content was removed
            assert "kiln:plan" not in cleaned_body
            assert "Plan steps here" not in cleaned_body
            # Verify original description is preserved
            assert original_description in cleaned_body

    def test_clear_kiln_content_new_style_markers_still_work(self, daemon):
        """Test that new-style markers continue to work (regression test)."""
        item = TicketItem(
            item_id="PVI_333",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=77,
            title="Test Issue",
            repo="github.com/owner/repo",
            status="Plan",
        )

        original_description = "Original content."
        research_content = """
---
<!-- kiln:research -->
## Research
Research data.
<!-- /kiln:research -->"""
        plan_content = """
---
<!-- kiln:plan -->
## Plan
Plan data.
<!-- /kiln:plan -->"""
        body = original_description + research_content + plan_content

        daemon.ticket_client.get_ticket_body.return_value = body

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            daemon._clear_kiln_content(item)

            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            body_index = call_args.index("--body") + 1
            cleaned_body = call_args[body_index]

            # Verify both sections were removed
            assert "kiln:research" not in cleaned_body
            assert "kiln:plan" not in cleaned_body
            assert "Research data" not in cleaned_body
            assert "Plan data" not in cleaned_body
            # Verify original description is preserved
            assert original_description in cleaned_body

