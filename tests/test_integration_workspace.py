"""Integration tests for WorkspaceManager."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.workspace import WorkspaceError, WorkspaceManager


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


@pytest.mark.integration
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


@pytest.mark.integration
class TestGetWorktreeBranch:
    """Tests for _get_worktree_branch method."""

    def test_parses_porcelain_output_correctly(self, temp_workspace_dir):
        """Test _get_worktree_branch parses porcelain output correctly."""
        manager = WorkspaceManager(temp_workspace_dir)

        # Create repo and worktree paths for mock
        repo_path = Path(temp_workspace_dir) / "test-repo"
        repo_path.mkdir()
        worktree_path = Path(temp_workspace_dir) / "test-repo-issue-42"

        # Mock porcelain output format
        porcelain_output = (
            f"worktree {repo_path}\n"
            "HEAD abc123def456\n"
            "branch refs/heads/main\n"
            "\n"
            f"worktree {worktree_path}\n"
            "HEAD def456abc789\n"
            "branch refs/heads/162-reset-cleanup-feature\n"
            "\n"
        )

        def mock_run_git_command(args, cwd=None, check=True):
            if args == ["worktree", "list", "--porcelain"]:
                return MagicMock(returncode=0, stdout=porcelain_output, stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch.object(manager, "_run_git_command", mock_run_git_command):
            result = manager._get_worktree_branch(worktree_path, repo_path)

        assert result == "162-reset-cleanup-feature"

    def test_returns_none_for_nonexistent_worktree(self, temp_workspace_dir):
        """Test _get_worktree_branch returns None for non-existent worktree."""
        manager = WorkspaceManager(temp_workspace_dir)

        repo_path = Path(temp_workspace_dir) / "test-repo"
        repo_path.mkdir()
        worktree_path = Path(temp_workspace_dir) / "nonexistent-worktree"

        # Porcelain output that doesn't contain our worktree
        porcelain_output = (
            f"worktree {repo_path}\n"
            "HEAD abc123def456\n"
            "branch refs/heads/main\n"
            "\n"
        )

        def mock_run_git_command(args, cwd=None, check=True):
            if args == ["worktree", "list", "--porcelain"]:
                return MagicMock(returncode=0, stdout=porcelain_output, stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch.object(manager, "_run_git_command", mock_run_git_command):
            result = manager._get_worktree_branch(worktree_path, repo_path)

        assert result is None

    def test_returns_correct_branch_when_multiple_worktrees_exist(self, temp_workspace_dir):
        """Test _get_worktree_branch returns correct branch when multiple worktrees exist."""
        manager = WorkspaceManager(temp_workspace_dir)

        repo_path = Path(temp_workspace_dir) / "test-repo"
        repo_path.mkdir()
        worktree1 = Path(temp_workspace_dir) / "test-repo-issue-1"
        worktree2 = Path(temp_workspace_dir) / "test-repo-issue-2"
        worktree3 = Path(temp_workspace_dir) / "test-repo-issue-3"

        # Multiple worktrees in porcelain output
        porcelain_output = (
            f"worktree {repo_path}\n"
            "HEAD abc123\n"
            "branch refs/heads/main\n"
            "\n"
            f"worktree {worktree1}\n"
            "HEAD def456\n"
            "branch refs/heads/issue-1-branch\n"
            "\n"
            f"worktree {worktree2}\n"
            "HEAD ghi789\n"
            "branch refs/heads/issue-2-branch\n"
            "\n"
            f"worktree {worktree3}\n"
            "HEAD jkl012\n"
            "branch refs/heads/issue-3-branch\n"
            "\n"
        )

        def mock_run_git_command(args, cwd=None, check=True):
            if args == ["worktree", "list", "--porcelain"]:
                return MagicMock(returncode=0, stdout=porcelain_output, stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch.object(manager, "_run_git_command", mock_run_git_command):
            # Request branch for worktree2 - should get issue-2-branch, not others
            result = manager._get_worktree_branch(worktree2, repo_path)

        assert result == "issue-2-branch"

    def test_returns_none_on_git_command_error(self, temp_workspace_dir):
        """Test _get_worktree_branch returns None when git command fails."""
        manager = WorkspaceManager(temp_workspace_dir)

        repo_path = Path(temp_workspace_dir) / "test-repo"
        repo_path.mkdir()
        worktree_path = Path(temp_workspace_dir) / "test-worktree"

        def mock_run_git_command(args, cwd=None, check=True):
            raise WorkspaceError("Git command failed")

        with patch.object(manager, "_run_git_command", mock_run_git_command):
            result = manager._get_worktree_branch(worktree_path, repo_path)

        assert result is None


@pytest.mark.integration
class TestCleanupWorkspaceBranchDeletion:
    """Tests for branch deletion in cleanup_workspace."""

    def test_deletes_branch_after_worktree_removal(self, temp_workspace_dir):
        """Test cleanup_workspace deletes branch after worktree removal."""
        manager = WorkspaceManager(temp_workspace_dir)

        # Setup: create fake repo and worktree directories
        # Use resolve() to handle macOS symlink (/var -> /private/var)
        repo_path = (Path(temp_workspace_dir) / "test-repo").resolve()
        repo_path.mkdir()
        (repo_path / ".git").mkdir()  # Make it look like a git repo

        worktree_path = (Path(temp_workspace_dir) / "test-repo-issue-42").resolve()
        worktree_path.mkdir()

        git_commands = []

        def mock_run_git_command(args, cwd=None, check=True):
            git_commands.append((args, cwd))
            if args == ["worktree", "list", "--porcelain"]:
                # Return porcelain output with our worktree
                return MagicMock(
                    returncode=0,
                    stdout=(
                        f"worktree {repo_path}\n"
                        "HEAD abc123\n"
                        "branch refs/heads/main\n"
                        "\n"
                        f"worktree {worktree_path}\n"
                        "HEAD def456\n"
                        "branch refs/heads/42-feature-branch\n"
                        "\n"
                    ),
                    stderr="",
                )
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch.object(manager, "_run_git_command", mock_run_git_command):
            manager.cleanup_workspace("test-repo", 42)

        # Verify correct commands were called in order
        command_args = [cmd[0] for cmd in git_commands]
        assert ["worktree", "list", "--porcelain"] in command_args
        assert ["worktree", "remove", "--force", str(worktree_path)] in command_args
        assert ["branch", "-D", "42-feature-branch"] in command_args

        # Verify order: branch deletion comes after worktree removal
        porcelain_idx = command_args.index(["worktree", "list", "--porcelain"])
        remove_idx = command_args.index(["worktree", "remove", "--force", str(worktree_path)])
        branch_idx = command_args.index(["branch", "-D", "42-feature-branch"])
        assert porcelain_idx < remove_idx < branch_idx

    def test_continues_if_branch_deletion_fails(self, temp_workspace_dir):
        """Test cleanup_workspace continues if branch deletion fails."""
        manager = WorkspaceManager(temp_workspace_dir)

        # Setup: create fake repo and worktree directories
        # Use resolve() to handle macOS symlink (/var -> /private/var)
        repo_path = (Path(temp_workspace_dir) / "test-repo").resolve()
        repo_path.mkdir()
        (repo_path / ".git").mkdir()

        worktree_path = (Path(temp_workspace_dir) / "test-repo-issue-42").resolve()
        worktree_path.mkdir()

        git_commands = []

        def mock_run_git_command(args, cwd=None, check=True):
            git_commands.append((args, cwd))
            if args == ["worktree", "list", "--porcelain"]:
                return MagicMock(
                    returncode=0,
                    stdout=(
                        f"worktree {worktree_path}\n"
                        "HEAD def456\n"
                        "branch refs/heads/42-feature-branch\n"
                        "\n"
                    ),
                    stderr="",
                )
            if args == ["branch", "-D", "42-feature-branch"]:
                # Branch already deleted or doesn't exist
                raise WorkspaceError("error: branch '42-feature-branch' not found")
            return MagicMock(returncode=0, stdout="", stderr="")

        # Should not raise - error is handled gracefully
        with patch.object(manager, "_run_git_command", mock_run_git_command):
            manager.cleanup_workspace("test-repo", 42)

        # Verify all commands were called including failed branch deletion
        command_args = [cmd[0] for cmd in git_commands]
        assert ["worktree", "remove", "--force", str(worktree_path)] in command_args
        assert ["branch", "-D", "42-feature-branch"] in command_args

    def test_skips_branch_deletion_when_no_branch_found(self, temp_workspace_dir):
        """Test cleanup_workspace skips branch deletion when no branch is found."""
        manager = WorkspaceManager(temp_workspace_dir)

        # Setup - use resolve() to handle macOS symlink (/var -> /private/var)
        repo_path = (Path(temp_workspace_dir) / "test-repo").resolve()
        repo_path.mkdir()
        (repo_path / ".git").mkdir()

        worktree_path = (Path(temp_workspace_dir) / "test-repo-issue-42").resolve()
        worktree_path.mkdir()

        git_commands = []

        def mock_run_git_command(args, cwd=None, check=True):
            git_commands.append((args, cwd))
            if args == ["worktree", "list", "--porcelain"]:
                # Return empty or no matching worktree
                return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch.object(manager, "_run_git_command", mock_run_git_command):
            manager.cleanup_workspace("test-repo", 42)

        # Verify branch -D was NOT called since no branch was found
        command_args = [cmd[0] for cmd in git_commands]
        assert ["worktree", "remove", "--force", str(worktree_path)] in command_args
        # Verify no "branch" command was called
        branch_commands = [cmd for cmd in command_args if cmd[0] == "branch"]
        assert len(branch_commands) == 0
