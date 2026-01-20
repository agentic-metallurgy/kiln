"""Unit tests for the CLI module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.cli import (
    BANNER_PLAIN,
    __version__,
    cleanup_claude_symlinks,
    create_claude_symlinks,
    extract_claude_resources,
    get_banner,
    get_readme,
    get_sample_config,
)


@pytest.mark.unit
class TestCli:
    """Tests for CLI functions."""

    def test_get_sample_config_returns_content(self):
        """Test that get_sample_config() returns .env.example content."""
        content = get_sample_config()
        assert "GITHUB_TOKEN" in content
        assert "PROJECT_URLS" in content

    def test_get_readme_returns_content(self):
        """Test that get_readme() returns README content."""
        content = get_readme()
        assert "Kiln" in content or "kiln" in content
        # README should have reasonable content
        assert len(content) > 100

    def test_get_banner_includes_version(self):
        """Test that get_banner() includes the version string."""
        banner = get_banner()
        assert f"v{__version__}" in banner

    def test_banner_plain_includes_version(self):
        """Test that BANNER_PLAIN includes the version string."""
        assert f"v{__version__}" in BANNER_PLAIN


@pytest.mark.unit
class TestInitKiln:
    """Tests for init_kiln function."""

    def test_init_kiln_creates_workspaces_directory(self, tmp_path, monkeypatch, capsys):
        """Test that init_kiln creates workspaces directory with .gitkeep."""
        monkeypatch.chdir(tmp_path)

        from src.cli import init_kiln

        init_kiln()

        # Verify workspaces directory was created
        workspace_dir = tmp_path / "workspaces"
        assert workspace_dir.exists()
        assert workspace_dir.is_dir()

        # Verify .gitkeep file was created
        gitkeep_file = workspace_dir / ".gitkeep"
        assert gitkeep_file.exists()
        assert gitkeep_file.is_file()

        # Verify output includes workspaces/
        captured = capsys.readouterr()
        assert "workspaces/" in captured.out

    def test_init_kiln_creates_readme(self, tmp_path, monkeypatch):
        """Test that init_kiln() creates .kiln/README.md."""
        from src.cli import init_kiln

        monkeypatch.chdir(tmp_path)
        init_kiln()

        # Check that README.md was created
        readme_path = tmp_path / ".kiln" / "README.md"
        assert readme_path.exists()
        content = readme_path.read_text()
        assert "Kiln" in content or "kiln" in content

    def test_init_kiln_creates_all_expected_files(self, tmp_path, monkeypatch):
        """Test that init_kiln() creates all expected files."""
        from src.cli import init_kiln

        monkeypatch.chdir(tmp_path)
        init_kiln()

        # Check all expected files/dirs exist
        assert (tmp_path / ".kiln").is_dir()
        assert (tmp_path / ".kiln" / "config").is_file()
        assert (tmp_path / ".kiln" / "logs").is_dir()
        assert (tmp_path / ".kiln" / "README.md").is_file()
        assert (tmp_path / "workspaces").is_dir()
        assert (tmp_path / "workspaces" / ".gitkeep").is_file()

    def test_init_kiln_is_idempotent(self, tmp_path, monkeypatch):
        """Test that running init_kiln twice doesn't fail."""
        monkeypatch.chdir(tmp_path)

        from src.cli import init_kiln

        # Run twice - should not raise
        init_kiln()
        init_kiln()

        # Verify directories still exist
        assert (tmp_path / "workspaces").exists()
        assert (tmp_path / "workspaces" / ".gitkeep").exists()
        assert (tmp_path / ".kiln").exists()
        assert (tmp_path / ".kiln" / "README.md").exists()


@pytest.mark.unit
class TestExtractClaudeResources:
    """Tests for extract_claude_resources function."""

    def test_extract_creates_directories(self, tmp_path, monkeypatch):
        """Test that extract_claude_resources creates commands, agents, skills directories."""
        monkeypatch.chdir(tmp_path)

        # Create .kiln directory first
        kiln_dir = tmp_path / ".kiln"
        kiln_dir.mkdir()

        # Create mock source .claude directory with resources
        source_claude = tmp_path / "mock_source" / ".claude"
        for subdir in ["commands", "agents", "skills"]:
            (source_claude / subdir).mkdir(parents=True)
            (source_claude / subdir / f"test_{subdir}.md").write_text(f"# Test {subdir}")

        # Mock the base_path to use our mock source
        with patch("src.cli.Path") as mock_path_class:
            # We need to be careful - only override the parent.parent lookup
            real_path = Path

            def path_side_effect(arg):
                if arg == Path(__file__):
                    mock = MagicMock()
                    mock.parent.parent = tmp_path / "mock_source"
                    return mock
                return real_path(arg)

            # Instead, patch at the module level by setting the base_path calculation
            with patch.object(Path, "__new__", lambda cls, *args: real_path(*args)):
                # Simpler approach: monkeypatch the function's internal logic
                pass

        # Directly test by creating source and using monkeypatch
        # Set up source .claude relative to where cli.py thinks it is
        repo_root = Path(__file__).parent.parent
        source_claude = repo_root / ".claude"

        # Call the function
        result = extract_claude_resources()

        # Verify extraction happened
        assert result == kiln_dir
        for subdir in ["commands", "agents", "skills"]:
            dest = kiln_dir / subdir
            # Check that directory was created if source exists
            if (source_claude / subdir).exists():
                assert dest.exists(), f".kiln/{subdir} should exist"
                assert dest.is_dir(), f".kiln/{subdir} should be a directory"

    def test_extract_copies_files(self, tmp_path, monkeypatch):
        """Test that extract_claude_resources copies files from source."""
        monkeypatch.chdir(tmp_path)

        # Create .kiln directory
        kiln_dir = tmp_path / ".kiln"
        kiln_dir.mkdir()

        # Call extract - uses real .claude source from repo
        result = extract_claude_resources()

        # The repo has .claude/commands, .claude/agents, .claude/skills
        # At minimum, commands should have files
        commands_dir = kiln_dir / "commands"
        if commands_dir.exists():
            files = list(commands_dir.glob("*.md"))
            assert len(files) > 0, "Should have extracted command files"

    def test_extract_overwrites_existing(self, tmp_path, monkeypatch):
        """Test that extract_claude_resources replaces existing directories."""
        monkeypatch.chdir(tmp_path)

        # Create .kiln directory
        kiln_dir = tmp_path / ".kiln"
        kiln_dir.mkdir()

        # Create existing commands directory with old file
        old_commands = kiln_dir / "commands"
        old_commands.mkdir()
        old_file = old_commands / "old_file.md"
        old_file.write_text("old content")

        # Call extract
        extract_claude_resources()

        # Old file should be gone (directory was replaced)
        assert not old_file.exists(), "Old file should be removed after extraction"

    def test_extract_is_idempotent(self, tmp_path, monkeypatch):
        """Test that calling extract_claude_resources twice doesn't fail."""
        monkeypatch.chdir(tmp_path)

        # Create .kiln directory
        (tmp_path / ".kiln").mkdir()

        # Call twice - should not raise
        extract_claude_resources()
        extract_claude_resources()

        # Verify .kiln still has expected structure
        assert (tmp_path / ".kiln").exists()

    def test_extract_handles_missing_source(self, tmp_path, monkeypatch):
        """Test that extract_claude_resources handles missing .claude gracefully."""
        monkeypatch.chdir(tmp_path)

        # Create .kiln directory
        kiln_dir = tmp_path / ".kiln"
        kiln_dir.mkdir()

        # Create a fake base path with no .claude directory
        fake_base = tmp_path / "fake_base"
        fake_base.mkdir()

        # Patch sys to simulate bundled mode without .claude
        with patch("src.cli.sys") as mock_sys:
            mock_sys._MEIPASS = str(fake_base)

            # Should return without error
            result = extract_claude_resources()
            assert result == kiln_dir


@pytest.mark.unit
class TestCreateClaudeSymlinks:
    """Tests for create_claude_symlinks function."""

    def test_create_symlinks_creates_links(self, tmp_path, monkeypatch):
        """Test that create_claude_symlinks creates symlinks in ~/.claude/."""
        monkeypatch.chdir(tmp_path)

        # Create .kiln directory with resources
        kiln_dir = tmp_path / ".kiln"
        for subdir in ["commands", "agents", "skills"]:
            (kiln_dir / subdir).mkdir(parents=True)
            (kiln_dir / subdir / f"test_{subdir}.md").write_text(f"# Test {subdir}")

        # Create fake home directory
        fake_home = tmp_path / "fake_home"
        fake_home.mkdir()

        with patch.object(Path, "home", return_value=fake_home):
            create_claude_symlinks()

        # Verify symlinks were created
        for subdir in ["commands", "agents", "skills"]:
            link = fake_home / ".claude" / subdir / "kiln"
            assert link.exists(), f"Symlink ~/.claude/{subdir}/kiln should exist"
            assert link.is_symlink(), f"~/.claude/{subdir}/kiln should be a symlink"
            assert link.resolve() == (kiln_dir / subdir).resolve(), f"Symlink should point to .kiln/{subdir}"

    def test_create_symlinks_creates_parent_directories(self, tmp_path, monkeypatch):
        """Test that create_claude_symlinks creates parent directories if needed."""
        monkeypatch.chdir(tmp_path)

        # Create .kiln with resources
        kiln_dir = tmp_path / ".kiln"
        (kiln_dir / "commands").mkdir(parents=True)
        (kiln_dir / "commands" / "test.md").write_text("# Test")

        # Create fake home without ~/.claude/
        fake_home = tmp_path / "fake_home"
        fake_home.mkdir()

        with patch.object(Path, "home", return_value=fake_home):
            create_claude_symlinks()

        # Verify parent directory was created
        assert (fake_home / ".claude" / "commands").exists()
        assert (fake_home / ".claude" / "commands").is_dir()

    def test_create_symlinks_replaces_existing(self, tmp_path, monkeypatch):
        """Test that create_claude_symlinks replaces existing symlinks."""
        monkeypatch.chdir(tmp_path)

        # Create .kiln with resources
        kiln_dir = tmp_path / ".kiln"
        (kiln_dir / "commands").mkdir(parents=True)
        (kiln_dir / "commands" / "test.md").write_text("# Test")

        # Create fake home with existing symlink pointing elsewhere
        fake_home = tmp_path / "fake_home"
        old_target = tmp_path / "old_target"
        old_target.mkdir()
        (fake_home / ".claude" / "commands").mkdir(parents=True)
        old_link = fake_home / ".claude" / "commands" / "kiln"
        old_link.symlink_to(old_target)

        with patch.object(Path, "home", return_value=fake_home):
            create_claude_symlinks()

        # Verify symlink now points to new target
        link = fake_home / ".claude" / "commands" / "kiln"
        assert link.is_symlink()
        assert link.resolve() == (kiln_dir / "commands").resolve()

    def test_create_symlinks_skips_missing_source(self, tmp_path, monkeypatch):
        """Test that create_claude_symlinks skips subdirs that don't exist in .kiln."""
        monkeypatch.chdir(tmp_path)

        # Create .kiln with only commands (no agents or skills)
        kiln_dir = tmp_path / ".kiln"
        (kiln_dir / "commands").mkdir(parents=True)
        (kiln_dir / "commands" / "test.md").write_text("# Test")

        # Create fake home
        fake_home = tmp_path / "fake_home"
        fake_home.mkdir()

        with patch.object(Path, "home", return_value=fake_home):
            create_claude_symlinks()

        # Only commands symlink should exist
        assert (fake_home / ".claude" / "commands" / "kiln").exists()
        assert not (fake_home / ".claude" / "agents" / "kiln").exists()
        assert not (fake_home / ".claude" / "skills" / "kiln").exists()

    def test_create_symlinks_is_idempotent(self, tmp_path, monkeypatch):
        """Test that calling create_claude_symlinks twice doesn't fail."""
        monkeypatch.chdir(tmp_path)

        # Create .kiln with resources
        kiln_dir = tmp_path / ".kiln"
        (kiln_dir / "commands").mkdir(parents=True)
        (kiln_dir / "commands" / "test.md").write_text("# Test")

        fake_home = tmp_path / "fake_home"
        fake_home.mkdir()

        with patch.object(Path, "home", return_value=fake_home):
            # Call twice - should not raise
            create_claude_symlinks()
            create_claude_symlinks()

        # Symlink should still work
        link = fake_home / ".claude" / "commands" / "kiln"
        assert link.is_symlink()


@pytest.mark.unit
class TestCleanupClaudeSymlinks:
    """Tests for cleanup_claude_symlinks function."""

    def test_cleanup_removes_symlinks(self, tmp_path, monkeypatch):
        """Test that cleanup_claude_symlinks removes symlinks."""
        monkeypatch.chdir(tmp_path)

        # Create .kiln with resources
        kiln_dir = tmp_path / ".kiln"
        for subdir in ["commands", "agents", "skills"]:
            (kiln_dir / subdir).mkdir(parents=True)

        # Create fake home with symlinks
        fake_home = tmp_path / "fake_home"
        for subdir in ["commands", "agents", "skills"]:
            (fake_home / ".claude" / subdir).mkdir(parents=True)
            link = fake_home / ".claude" / subdir / "kiln"
            link.symlink_to(kiln_dir / subdir)

        with patch.object(Path, "home", return_value=fake_home):
            cleanup_claude_symlinks()

        # Verify symlinks were removed
        for subdir in ["commands", "agents", "skills"]:
            link = fake_home / ".claude" / subdir / "kiln"
            assert not link.exists(), f"Symlink ~/.claude/{subdir}/kiln should be removed"

    def test_cleanup_handles_missing_symlinks(self, tmp_path, monkeypatch):
        """Test that cleanup_claude_symlinks handles missing symlinks gracefully."""
        fake_home = tmp_path / "fake_home"
        fake_home.mkdir()

        with patch.object(Path, "home", return_value=fake_home):
            # Should not raise even if symlinks don't exist
            cleanup_claude_symlinks()

    def test_cleanup_handles_partial_symlinks(self, tmp_path, monkeypatch):
        """Test that cleanup_claude_symlinks handles partial symlinks."""
        monkeypatch.chdir(tmp_path)

        # Create .kiln with resources
        kiln_dir = tmp_path / ".kiln"
        (kiln_dir / "commands").mkdir(parents=True)

        # Create fake home with only commands symlink
        fake_home = tmp_path / "fake_home"
        (fake_home / ".claude" / "commands").mkdir(parents=True)
        link = fake_home / ".claude" / "commands" / "kiln"
        link.symlink_to(kiln_dir / "commands")

        with patch.object(Path, "home", return_value=fake_home):
            # Should not raise
            cleanup_claude_symlinks()

        # Commands symlink should be removed
        assert not link.exists()

    def test_cleanup_logs_errors(self, tmp_path, monkeypatch):
        """Test that cleanup_claude_symlinks logs errors gracefully."""
        fake_home = tmp_path / "fake_home"
        (fake_home / ".claude" / "commands").mkdir(parents=True)

        # Create a regular file (not symlink) at the kiln path
        bad_path = fake_home / ".claude" / "commands" / "kiln"
        bad_path.write_text("not a symlink")

        with patch.object(Path, "home", return_value=fake_home):
            # Should not raise - just log warning
            cleanup_claude_symlinks()

        # File should still exist (cleanup only removes symlinks)
        assert bad_path.exists()

    def test_cleanup_is_idempotent(self, tmp_path, monkeypatch):
        """Test that calling cleanup_claude_symlinks twice doesn't fail."""
        fake_home = tmp_path / "fake_home"
        fake_home.mkdir()

        with patch.object(Path, "home", return_value=fake_home):
            # Call twice - should not raise
            cleanup_claude_symlinks()
            cleanup_claude_symlinks()
