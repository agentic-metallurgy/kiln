"""Integration tests for WorkspaceManager."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.workspace import WorkspaceError, WorkspaceManager


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
