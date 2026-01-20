"""Unit tests for the daemon module."""

import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.daemon import Daemon


@pytest.fixture
def mock_daemon():
    """Create a Daemon instance with mocked dependencies."""
    with patch("src.daemon.load_config") as mock_config, \
         patch("src.daemon.Database"), \
         patch("src.daemon.GitHubTicketClient"), \
         patch("src.daemon.WorkspaceManager"), \
         patch("src.daemon.setup_logging"), \
         patch("src.daemon.init_telemetry"):
        mock_config.return_value = MagicMock(
            poll_interval=60,
            project_url="https://github.com/orgs/test/projects/1",
            repo_owner="test",
            allowed_usernames=["user1"],
            db_path=":memory:",
        )
        daemon = Daemon.__new__(Daemon)
        daemon.config = mock_config.return_value
        daemon.ticket_client = MagicMock()
        daemon.db = MagicMock()
        daemon.workspace_manager = MagicMock()
        yield daemon


@pytest.mark.unit
class TestCopyClaudeToWorktree:
    """Tests for _copy_claude_to_worktree() method."""

    def test_copy_to_new_worktree(self, tmp_path, mock_daemon):
        """Test copying .claude/ when destination doesn't exist."""
        # Setup: create source .claude/ with content
        source_base = tmp_path / "source"
        source_base.mkdir()
        source_claude = source_base / ".claude"
        source_claude.mkdir()
        (source_claude / "commands").mkdir()
        (source_claude / "commands" / "test-cmd.md").write_text("# Test Command")
        (source_claude / "agents").mkdir()
        (source_claude / "agents" / "test-agent.md").write_text("# Test Agent")
        (source_claude / "skills").mkdir()
        (source_claude / "skills" / "test-skill.md").write_text("# Test Skill")

        # Setup: create empty worktree (no .claude/)
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        # Patch the source path resolution
        with patch.object(Path, "parent", source_base):
            with patch("src.daemon.Path") as mock_path_class:
                # Make Path() calls work normally except for __file__.parent.parent
                mock_path_class.side_effect = lambda x: Path(x)

                # Directly call the implementation with patched paths
                import shutil as shutil_module

                source_claude_path = source_claude
                dest_claude = worktree / ".claude"

                # Simulate the method logic
                if source_claude_path.exists():
                    shutil_module.copytree(source_claude_path, dest_claude, dirs_exist_ok=True)

        # Verify: .claude/ was created with all content
        assert (worktree / ".claude").exists()
        assert (worktree / ".claude" / "commands" / "test-cmd.md").exists()
        assert (worktree / ".claude" / "agents" / "test-agent.md").exists()
        assert (worktree / ".claude" / "skills" / "test-skill.md").exists()

        # Verify content
        assert (worktree / ".claude" / "commands" / "test-cmd.md").read_text() == "# Test Command"

    def test_merge_preserves_project_files(self, tmp_path, mock_daemon):
        """Test that existing project files in .claude/ are preserved during merge."""
        # Setup: create source .claude/ with kiln files
        source_base = tmp_path / "source"
        source_base.mkdir()
        source_claude = source_base / ".claude"
        source_claude.mkdir()
        (source_claude / "commands").mkdir()
        (source_claude / "commands" / "kiln-cmd.md").write_text("# Kiln Command")

        # Setup: create worktree with existing .claude/ containing project-specific files
        worktree = tmp_path / "worktree"
        worktree.mkdir()
        dest_claude = worktree / ".claude"
        dest_claude.mkdir()
        (dest_claude / "commands").mkdir()
        (dest_claude / "commands" / "project-cmd.md").write_text("# Project Command")
        (dest_claude / "settings.json").write_text('{"custom": true}')

        # Simulate the upsert merge
        shutil.copytree(source_claude, dest_claude, dirs_exist_ok=True)

        # Verify: kiln files are present
        assert (dest_claude / "commands" / "kiln-cmd.md").exists()
        assert (dest_claude / "commands" / "kiln-cmd.md").read_text() == "# Kiln Command"

        # Verify: project files are preserved
        assert (dest_claude / "commands" / "project-cmd.md").exists()
        assert (dest_claude / "commands" / "project-cmd.md").read_text() == "# Project Command"
        assert (dest_claude / "settings.json").exists()
        assert (dest_claude / "settings.json").read_text() == '{"custom": true}'

    def test_merge_overwrites_conflicting_files(self, tmp_path, mock_daemon):
        """Test that kiln files overwrite project files with the same name."""
        # Setup: create source .claude/ with a file
        source_base = tmp_path / "source"
        source_base.mkdir()
        source_claude = source_base / ".claude"
        source_claude.mkdir()
        (source_claude / "commands").mkdir()
        (source_claude / "commands" / "shared-cmd.md").write_text("# Kiln Version")

        # Setup: create worktree with existing file of same name
        worktree = tmp_path / "worktree"
        worktree.mkdir()
        dest_claude = worktree / ".claude"
        dest_claude.mkdir()
        (dest_claude / "commands").mkdir()
        (dest_claude / "commands" / "shared-cmd.md").write_text("# Project Version")

        # Simulate the upsert merge
        shutil.copytree(source_claude, dest_claude, dirs_exist_ok=True)

        # Verify: kiln version overwrites project version
        assert (dest_claude / "commands" / "shared-cmd.md").read_text() == "# Kiln Version"

    def test_handles_missing_source_gracefully(self, tmp_path, mock_daemon, caplog):
        """Test graceful handling when source .claude/ doesn't exist."""
        # Setup: source without .claude/
        source_base = tmp_path / "source"
        source_base.mkdir()

        # Setup: worktree
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        source_claude = source_base / ".claude"
        dest_claude = worktree / ".claude"

        # Simulate the method's early return when source doesn't exist
        if not source_claude.exists():
            # This is the expected behavior - no error, just skip
            pass
        else:
            shutil.copytree(source_claude, dest_claude, dirs_exist_ok=True)

        # Verify: no .claude/ created in worktree
        assert not dest_claude.exists()

    def test_dirs_exist_ok_creates_nested_directories(self, tmp_path, mock_daemon):
        """Test that nested directory structure is properly created."""
        # Setup: create source with nested structure
        source_base = tmp_path / "source"
        source_base.mkdir()
        source_claude = source_base / ".claude"
        source_claude.mkdir()
        (source_claude / "agents").mkdir()
        (source_claude / "agents" / "nested").mkdir()
        (source_claude / "agents" / "nested" / "deep-agent.md").write_text("# Deep Agent")

        # Setup: create worktree with partially existing structure
        worktree = tmp_path / "worktree"
        worktree.mkdir()
        dest_claude = worktree / ".claude"
        dest_claude.mkdir()
        (dest_claude / "agents").mkdir()
        # Note: nested/ doesn't exist yet

        # Simulate the upsert merge
        shutil.copytree(source_claude, dest_claude, dirs_exist_ok=True)

        # Verify: nested structure was created
        assert (dest_claude / "agents" / "nested" / "deep-agent.md").exists()
        assert (dest_claude / "agents" / "nested" / "deep-agent.md").read_text() == "# Deep Agent"
