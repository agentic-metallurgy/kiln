"""Integration tests for worktree path collision prevention.

These tests verify that repositories with the same final name segment but
different owners get distinct worktree and main repo clone paths.

This addresses issue #250: Post-reset worktree issues caused by path collisions.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.daemon import Daemon
from src.interfaces import TicketItem
from src.workspace import WorkspaceManager


@pytest.mark.integration
class TestWorktreePathCollision:
    """Tests for preventing worktree path collisions between repos with same name."""

    def test_distinct_worktree_paths_for_repos_with_same_name(self, temp_workspace_dir):
        """Test that two repos with same final name get distinct worktree paths."""
        manager = WorkspaceManager(temp_workspace_dir)

        # Two repos with the same final name "my-app" but different owners
        repo1 = "github.com/org-a/my-app"
        repo2 = "github.com/org-b/my-app"

        path1 = manager.get_workspace_path(repo1, 123)
        path2 = manager.get_workspace_path(repo2, 123)

        # Paths should be distinct
        assert path1 != path2

        # Each path should contain the owner for uniqueness
        assert "org-a_my-app-issue-123" in path1
        assert "org-b_my-app-issue-123" in path2

    def test_distinct_worktree_paths_same_issue_number(self, temp_workspace_dir):
        """Test distinct paths when same issue number exists in different repos."""
        manager = WorkspaceManager(temp_workspace_dir)

        # Same issue number 42 in two different repos with same name
        repo1 = "github.com/team-alpha/service"
        repo2 = "github.com/team-beta/service"

        path1 = manager.get_workspace_path(repo1, 42)
        path2 = manager.get_workspace_path(repo2, 42)

        assert path1 != path2
        assert "team-alpha_service-issue-42" in path1
        assert "team-beta_service-issue-42" in path2

    def test_distinct_main_repo_clone_paths(self, temp_workspace_dir):
        """Test that main repo clone paths are distinct for repos with same name."""
        manager = WorkspaceManager(temp_workspace_dir)

        # Two repos with same final name
        repo1 = "github.com/org-a/my-app"
        repo2 = "github.com/org-b/my-app"

        # Get the identifiers used for clone paths
        id1 = manager._get_repo_identifier(repo1)
        id2 = manager._get_repo_identifier(repo2)

        # Clone paths should be distinct
        clone_path1 = Path(temp_workspace_dir) / id1
        clone_path2 = Path(temp_workspace_dir) / id2

        assert clone_path1 != clone_path2
        assert id1 == "org-a_my-app"
        assert id2 == "org-b_my-app"

    def test_enterprise_github_repos_with_same_name(self, temp_workspace_dir):
        """Test distinct paths for enterprise GitHub repos with same name."""
        manager = WorkspaceManager(temp_workspace_dir)

        # Enterprise GitHub URLs with same repo name
        repo1 = "github.mycompany.com/team-a/api"
        repo2 = "github.mycompany.com/team-b/api"

        path1 = manager.get_workspace_path(repo1, 1)
        path2 = manager.get_workspace_path(repo2, 1)

        assert path1 != path2
        assert "team-a_api-issue-1" in path1
        assert "team-b_api-issue-1" in path2

    def test_cleanup_works_with_new_format(self, temp_workspace_dir):
        """Test that cleanup_workspace works correctly with new path format."""
        manager = WorkspaceManager(temp_workspace_dir)

        # Setup: create fake repo and worktree directories using new format
        repo_id = manager._get_repo_identifier("github.com/test-org/my-app")
        repo_path = Path(temp_workspace_dir) / repo_id
        repo_path.mkdir()
        (repo_path / ".git").mkdir()

        worktree_path = Path(manager.get_workspace_path("github.com/test-org/my-app", 99))
        worktree_path.mkdir()
        (worktree_path / "test_file.txt").write_text("test content")

        git_commands = []

        def mock_run_git_command(args, cwd=None, check=True):
            git_commands.append((args, cwd))
            if args == ["worktree", "list", "--porcelain"]:
                return MagicMock(
                    returncode=0,
                    stdout=(
                        f"worktree {worktree_path}\nHEAD abc123\nbranch refs/heads/99-feature\n\n"
                    ),
                    stderr="",
                )
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch.object(manager, "_run_git_command", mock_run_git_command):
            manager.cleanup_workspace("github.com/test-org/my-app", 99)

        # Verify correct worktree path was used in cleanup
        remove_cmd = [cmd for cmd in git_commands if cmd[0][:2] == ["worktree", "remove"]]
        assert len(remove_cmd) == 1
        assert str(worktree_path) in remove_cmd[0][0]


@pytest.mark.integration
class TestResetFlowWithNewPaths:
    """Tests for reset flow with new path format."""

    @pytest.fixture
    def daemon(self, temp_workspace_dir):
        """Create a daemon instance for testing with mocked workspace_manager."""
        config = MagicMock()
        config.poll_interval = 60
        config.watched_statuses = ["Research", "Plan", "Implement"]
        config.max_concurrent_workflows = 2
        config.database_path = f"{temp_workspace_dir}/test.db"
        config.workspace_dir = temp_workspace_dir
        config.project_urls = ["https://github.com/orgs/test/projects/1"]
        config.github_enterprise_version = None
        config.team_usernames = []
        config.username_self = "kiln-bot"

        with patch("src.ticket_clients.github.GitHubTicketClient"):
            daemon = Daemon(config)
            daemon.ticket_client = MagicMock()
            # Mock the workspace_manager for reset tests
            daemon.workspace_manager = MagicMock()
            daemon.comment_processor.ticket_client = daemon.ticket_client
            yield daemon
            daemon.stop()

    def test_reset_cleans_correct_worktree_with_new_format(self, daemon, temp_workspace_dir):
        """Test that reset cleans up the correct worktree using new path format."""
        item = TicketItem(
            item_id="PVI_250",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=250,
            title="Test Reset with New Path Format",
            repo="github.com/owner/my-app",
            status="Research",
            labels=["reset"],
        )

        # Setup mocks
        daemon.ticket_client.get_label_actor.return_value = "kiln-bot"
        daemon.ticket_client.get_linked_prs.return_value = []
        daemon.ticket_client.get_ticket_body.return_value = "Issue body"

        # Configure workspace_manager mock to return expected path
        expected_path = str(Path(temp_workspace_dir) / "owner_my-app-issue-250")
        daemon.workspace_manager.get_workspace_path.return_value = expected_path

        # Create worktree with new format (owner_repo) so it exists
        worktree_path = Path(expected_path)
        worktree_path.mkdir()
        (worktree_path / "test_file.txt").write_text("content")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            daemon._maybe_handle_reset(item)

        # Verify workspace_manager.cleanup_workspace was called with correct args
        daemon.workspace_manager.cleanup_workspace.assert_called_once_with(
            "github.com/owner/my-app", 250
        )

    def test_reset_does_not_affect_other_repo_with_same_name(self, daemon, temp_workspace_dir):
        """Test that resetting one repo doesn't affect another with the same final name."""
        item_to_reset = TicketItem(
            item_id="PVI_100",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=100,
            title="Issue to Reset",
            repo="github.com/org-a/shared-name",
            status="Research",
            labels=["reset"],
        )

        # Setup mocks
        daemon.ticket_client.get_label_actor.return_value = "kiln-bot"
        daemon.ticket_client.get_linked_prs.return_value = []
        daemon.ticket_client.get_ticket_body.return_value = "Issue body"

        # Configure workspace_manager mock to return expected path for org-a
        expected_path = str(Path(temp_workspace_dir) / "org-a_shared-name-issue-100")
        daemon.workspace_manager.get_workspace_path.return_value = expected_path

        # Create worktrees for both repos with same final name
        worktree1 = Path(expected_path)
        worktree2 = Path(temp_workspace_dir) / "org-b_shared-name-issue-100"
        worktree1.mkdir()
        worktree2.mkdir()
        (worktree1 / "file1.txt").write_text("org-a content")
        (worktree2 / "file2.txt").write_text("org-b content")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            daemon._maybe_handle_reset(item_to_reset)

        # Verify cleanup was called for the correct repo
        daemon.workspace_manager.cleanup_workspace.assert_called_once_with(
            "github.com/org-a/shared-name", 100
        )

        # The other repo's worktree should still exist (unaffected)
        assert worktree2.exists()


@pytest.mark.integration
class TestOldFormatWorktreeBackwardsCompatibility:
    """Tests for backwards compatibility with old-format worktrees."""

    def test_old_format_worktree_detected_as_valid(self, temp_workspace_dir):
        """Test that old-format worktrees (if valid) are detected as valid git worktrees."""
        manager = WorkspaceManager(temp_workspace_dir)

        # Create an old-format worktree path (just repo name, not owner_repo)
        old_worktree_path = Path(temp_workspace_dir) / "my-app-issue-42"
        old_worktree_path.mkdir()

        # Create a valid .git file (worktree format)
        git_file = old_worktree_path / ".git"
        git_file.write_text("gitdir: /path/to/main/repo/.git/worktrees/my-app-issue-42\n")

        # Old-format worktree should still be detected as valid
        assert manager.is_valid_worktree(str(old_worktree_path)) is True

    def test_old_format_invalid_worktree_triggers_auto_prepare(self, temp_workspace_dir):
        """Test that invalid old-format directory triggers auto-prepare."""
        manager = WorkspaceManager(temp_workspace_dir)

        # Create an old-format directory that's NOT a valid worktree
        old_path = Path(temp_workspace_dir) / "my-app-issue-42"
        old_path.mkdir()
        # No .git file - just an empty directory

        # Should be detected as invalid
        assert manager.is_valid_worktree(str(old_path)) is False

    def test_stale_old_format_directory_detected_as_invalid(self, temp_workspace_dir):
        """Test that stale old-format directories are detected as invalid."""
        manager = WorkspaceManager(temp_workspace_dir)

        # Create a stale directory with corrupt .git file
        stale_path = Path(temp_workspace_dir) / "legacy-repo-issue-99"
        stale_path.mkdir()
        git_file = stale_path / ".git"
        git_file.write_text("corrupted content without gitdir prefix")

        # Should be detected as invalid
        assert manager.is_valid_worktree(str(stale_path)) is False

    def test_migration_scenario_old_worktree_with_git_directory(self, temp_workspace_dir):
        """Test that old worktree with .git as directory (not file) is invalid."""
        manager = WorkspaceManager(temp_workspace_dir)

        # Old-style repo clone has .git as a directory (not a worktree)
        old_clone_path = Path(temp_workspace_dir) / "old-repo"
        old_clone_path.mkdir()
        (old_clone_path / ".git").mkdir()  # Directory, not file

        # Should NOT be considered a valid worktree
        assert manager.is_valid_worktree(str(old_clone_path)) is False


@pytest.mark.integration
class TestAutoPrepareWithValidation:
    """Tests for auto-prepare triggering based on worktree validation."""

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
        config.github_enterprise_version = None
        config.team_usernames = []
        config.username_self = "kiln-bot"

        with patch("src.ticket_clients.github.GitHubTicketClient"):
            daemon = Daemon(config)
            daemon.ticket_client = MagicMock()
            yield daemon
            daemon.stop()

    def test_auto_prepare_triggers_for_nonexistent_worktree(self, daemon, temp_workspace_dir):
        """Test that auto-prepare triggers when worktree doesn't exist."""
        item = TicketItem(
            item_id="PVI_300",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=300,
            title="New Issue - No Worktree",
            repo="github.com/owner/repo",
            status="Research",
            labels=[],
        )

        # Get expected worktree path (doesn't exist)
        worktree_path = daemon._get_worktree_path(item.repo, item.ticket_id)
        assert not Path(worktree_path).exists()

        # Verify is_valid_worktree returns False for non-existent path
        assert daemon.workspace_manager.is_valid_worktree(worktree_path) is False

    def test_auto_prepare_triggers_for_invalid_directory(self, daemon, temp_workspace_dir):
        """Test that auto-prepare triggers when directory exists but is invalid."""
        item = TicketItem(
            item_id="PVI_301",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=301,
            title="Issue with Stale Directory",
            repo="github.com/owner/repo",
            status="Research",
            labels=[],
        )

        # Create an invalid directory at the expected worktree path
        worktree_path = daemon._get_worktree_path(item.repo, item.ticket_id)
        Path(worktree_path).mkdir(parents=True)
        # No .git file - invalid worktree

        # Verify is_valid_worktree returns False for invalid directory
        assert daemon.workspace_manager.is_valid_worktree(worktree_path) is False

    def test_auto_prepare_skips_for_valid_worktree(self, daemon, temp_workspace_dir):
        """Test that auto-prepare is skipped when valid worktree exists."""
        item = TicketItem(
            item_id="PVI_302",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=302,
            title="Issue with Valid Worktree",
            repo="github.com/owner/repo",
            status="Research",
            labels=[],
        )

        # Create a valid worktree at the expected path
        worktree_path = Path(daemon._get_worktree_path(item.repo, item.ticket_id))
        worktree_path.mkdir(parents=True)
        git_file = worktree_path / ".git"
        git_file.write_text("gitdir: /some/valid/path/.git/worktrees/test\n")

        # Verify is_valid_worktree returns True
        assert daemon.workspace_manager.is_valid_worktree(str(worktree_path)) is True


@pytest.mark.integration
class TestConcurrentReposWithSameName:
    """Tests for concurrent handling of repos with same final name."""

    def test_multiple_repos_same_name_distinct_paths(self, temp_workspace_dir):
        """Test that multiple repos with same final name all get distinct paths."""
        manager = WorkspaceManager(temp_workspace_dir)

        repos = [
            "github.com/org-1/common-lib",
            "github.com/org-2/common-lib",
            "github.com/org-3/common-lib",
            "github.enterprise.com/team/common-lib",
        ]

        issue_number = 42
        paths = [manager.get_workspace_path(repo, issue_number) for repo in repos]

        # All paths should be unique
        assert len(paths) == len(set(paths))

        # Each path should contain the owner prefix
        assert "org-1_common-lib-issue-42" in paths[0]
        assert "org-2_common-lib-issue-42" in paths[1]
        assert "org-3_common-lib-issue-42" in paths[2]
        assert "team_common-lib-issue-42" in paths[3]

    def test_repo_identifiers_are_consistent(self, temp_workspace_dir):
        """Test that repo identifier is consistent across multiple calls."""
        manager = WorkspaceManager(temp_workspace_dir)

        repo = "github.com/test-owner/test-repo"

        # Multiple calls should return the same identifier
        id1 = manager._get_repo_identifier(repo)
        id2 = manager._get_repo_identifier(repo)
        id3 = manager._get_repo_identifier(repo)

        assert id1 == id2 == id3 == "test-owner_test-repo"

    def test_workspace_paths_are_deterministic(self, temp_workspace_dir):
        """Test that workspace paths are deterministic for same inputs."""
        manager = WorkspaceManager(temp_workspace_dir)

        repo = "github.com/my-org/my-repo"
        issue = 123

        # Multiple calls should return the same path
        path1 = manager.get_workspace_path(repo, issue)
        path2 = manager.get_workspace_path(repo, issue)
        path3 = manager.get_workspace_path(repo, issue)

        assert path1 == path2 == path3
