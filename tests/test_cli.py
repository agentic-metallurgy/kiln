"""Unit tests for the CLI module."""

import pytest

from src.cli import get_readme, get_sample_config


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
