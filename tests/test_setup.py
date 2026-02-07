"""Unit tests for the setup validation module."""

import os
import subprocess
import time
import urllib.error
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from src.setup.checks import (
    CACHE_FILE_NAME,
    CACHE_MAX_AGE_SECONDS,
    ClaudeInfo,
    SetupError,
    ShellConfigVar,
    UpdateInfo,
    check_anthropic_env_vars,
    check_claude_installation,
    check_for_updates,
    check_required_tools,
    configure_git_credential_env,
    get_hostnames_from_project_urls,
    is_restricted_directory,
    scan_shell_configs_for_anthropic,
    validate_working_directory,
)
from src.setup.project import (
    GITHUB_DEFAULT_COLUMNS,
    REQUIRED_COLUMN_NAMES,
    ValidationResult,
    validate_project_columns,
)


@pytest.mark.unit
class TestIsRestrictedDirectory:
    """Tests for is_restricted_directory()."""

    def test_root_directory_is_restricted(self, tmp_path):
        """Test that root directory (/) is restricted."""
        from pathlib import Path

        assert is_restricted_directory(Path("/")) is True

    def test_users_directory_is_restricted(self):
        """Test that /Users/ is restricted."""
        from pathlib import Path

        assert is_restricted_directory(Path("/Users")) is True
        assert is_restricted_directory(Path("/Users/")) is True

    def test_home_directory_linux_is_restricted(self, tmp_path, monkeypatch):
        """Test that /home/<user> directory is restricted (Linux-style)."""
        from pathlib import Path

        # On macOS, /home resolves to /System/Volumes/Data/home which doesn't
        # match our pattern. We test the Linux-style home by mocking Path.home().
        # The key behavior is that the user's home directory is restricted,
        # regardless of whether it's /Users/<user> or /home/<user>.
        mock_home = tmp_path / "home" / "testuser"
        mock_home.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: mock_home)

        # User's home directory should be restricted
        assert is_restricted_directory(mock_home) is True

        # Subdirectory of home should be allowed
        subdir = mock_home / "projects"
        subdir.mkdir()
        assert is_restricted_directory(subdir) is False

    def test_user_home_directory_is_restricted(self, tmp_path, monkeypatch):
        """Test that user's home directory is restricted."""
        from pathlib import Path

        # Mock Path.home() to return a controlled path
        mock_home = tmp_path / "mockhome"
        mock_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: mock_home)

        assert is_restricted_directory(mock_home) is True

    def test_subdirectory_of_home_is_allowed(self, tmp_path, monkeypatch):
        """Test that subdirectories of home are allowed."""
        from pathlib import Path

        # Mock Path.home() to return a controlled path
        mock_home = tmp_path / "mockhome"
        mock_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: mock_home)

        subdir = mock_home / "projects"
        subdir.mkdir()

        assert is_restricted_directory(subdir) is False

    def test_deeply_nested_directory_is_allowed(self, tmp_path, monkeypatch):
        """Test that deeply nested directories are allowed."""
        from pathlib import Path

        mock_home = tmp_path / "mockhome"
        mock_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: mock_home)

        deep_dir = mock_home / "projects" / "kiln" / "workspace"
        deep_dir.mkdir(parents=True)

        assert is_restricted_directory(deep_dir) is False

    def test_uses_cwd_when_no_directory_provided(self, tmp_path, monkeypatch):
        """Test that current working directory is used when none provided."""
        monkeypatch.chdir(tmp_path)
        # tmp_path is not a restricted directory
        assert is_restricted_directory() is False

    def test_non_home_top_level_directory_is_allowed(self):
        """Test that non-restricted top-level directories are allowed."""
        from pathlib import Path

        # /tmp, /var, etc. should be allowed
        assert is_restricted_directory(Path("/tmp")) is False
        assert is_restricted_directory(Path("/var")) is False


@pytest.mark.unit
class TestValidateWorkingDirectory:
    """Tests for validate_working_directory()."""

    def test_raises_for_root_directory(self):
        """Test that SetupError is raised for root directory."""
        from pathlib import Path

        with pytest.raises(SetupError) as exc_info:
            validate_working_directory(Path("/"))

        error = str(exc_info.value)
        assert "Cannot run kiln" in error
        assert "not allowed" in error
        assert "mkdir" in error

    def test_raises_for_home_directory(self, tmp_path, monkeypatch):
        """Test that SetupError is raised for home directory."""
        from pathlib import Path

        mock_home = tmp_path / "mockhome"
        mock_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: mock_home)

        with pytest.raises(SetupError) as exc_info:
            validate_working_directory(mock_home)

        error = str(exc_info.value)
        assert "Cannot run kiln" in error
        assert str(mock_home) in error

    def test_no_error_for_valid_directory(self, tmp_path, monkeypatch):
        """Test that no error is raised for valid directory."""
        from pathlib import Path

        mock_home = tmp_path / "mockhome"
        mock_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: mock_home)

        valid_dir = mock_home / "projects"
        valid_dir.mkdir()

        # Should not raise
        validate_working_directory(valid_dir)

    def test_error_includes_recommendation(self):
        """Test that error message includes recommendation to create directory."""
        from pathlib import Path

        with pytest.raises(SetupError) as exc_info:
            validate_working_directory(Path("/"))

        error = str(exc_info.value)
        assert "mkdir" in error
        assert "kiln-workspace" in error


@pytest.mark.unit
class TestScanShellConfigsForAnthropic:
    """Tests for scan_shell_configs_for_anthropic()."""

    def test_finds_anthropic_var_in_zshrc(self, tmp_path, monkeypatch):
        """Test detection of ANTHROPIC_* in .zshrc."""
        from pathlib import Path

        # Create mock home directory with .zshrc
        mock_home = tmp_path / "home"
        mock_home.mkdir()
        zshrc = mock_home / ".zshrc"
        zshrc.write_text("# Some config\nexport ANTHROPIC_API_KEY=sk-abc123\n")

        monkeypatch.setattr(Path, "home", lambda: mock_home)

        result = scan_shell_configs_for_anthropic()

        assert len(result) == 1
        assert result[0].var == "ANTHROPIC_API_KEY"
        assert result[0].file == "~/.zshrc"
        assert result[0].line == 2

    def test_finds_anthropic_var_in_bashrc(self, tmp_path, monkeypatch):
        """Test detection of ANTHROPIC_* in .bashrc."""
        from pathlib import Path

        mock_home = tmp_path / "home"
        mock_home.mkdir()
        bashrc = mock_home / ".bashrc"
        bashrc.write_text("export ANTHROPIC_MODEL=claude-3\n")

        monkeypatch.setattr(Path, "home", lambda: mock_home)

        result = scan_shell_configs_for_anthropic()

        assert len(result) == 1
        assert result[0].var == "ANTHROPIC_MODEL"
        assert result[0].file == "~/.bashrc"
        assert result[0].line == 1

    def test_finds_multiple_vars_across_files(self, tmp_path, monkeypatch):
        """Test detection across multiple config files."""
        from pathlib import Path

        mock_home = tmp_path / "home"
        mock_home.mkdir()

        zshrc = mock_home / ".zshrc"
        zshrc.write_text("export ANTHROPIC_API_KEY=key1\n")

        bashrc = mock_home / ".bashrc"
        bashrc.write_text("export ANTHROPIC_BASE_URL=https://api.anthropic.com\n")

        monkeypatch.setattr(Path, "home", lambda: mock_home)

        result = scan_shell_configs_for_anthropic()

        assert len(result) == 2
        vars_found = {r.var for r in result}
        assert vars_found == {"ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL"}

    def test_no_false_positives(self, tmp_path, monkeypatch):
        """Test that non-ANTHROPIC_* vars are not detected."""
        from pathlib import Path

        mock_home = tmp_path / "home"
        mock_home.mkdir()
        zshrc = mock_home / ".zshrc"
        zshrc.write_text(
            "export PATH=/usr/bin\n"
            "export OPENAI_API_KEY=sk-openai\n"
            "# export ANTHROPIC_API_KEY=commented\n"  # Commented line
            "export GITHUB_TOKEN=ghp_xxx\n"
        )

        monkeypatch.setattr(Path, "home", lambda: mock_home)

        result = scan_shell_configs_for_anthropic()

        # Commented line should not be detected (pattern expects start of line)
        assert len(result) == 0

    def test_handles_missing_files_gracefully(self, tmp_path, monkeypatch):
        """Test that missing config files don't cause errors."""
        from pathlib import Path

        mock_home = tmp_path / "home"
        mock_home.mkdir()
        # Don't create any config files

        monkeypatch.setattr(Path, "home", lambda: mock_home)

        result = scan_shell_configs_for_anthropic()

        assert result == []

    def test_handles_unreadable_files_gracefully(self, tmp_path, monkeypatch):
        """Test that unreadable files are skipped."""
        from pathlib import Path

        mock_home = tmp_path / "home"
        mock_home.mkdir()
        zshrc = mock_home / ".zshrc"
        zshrc.write_text("export ANTHROPIC_API_KEY=key\n")
        zshrc.chmod(0o000)  # Make unreadable

        monkeypatch.setattr(Path, "home", lambda: mock_home)

        try:
            result = scan_shell_configs_for_anthropic()
            # Should not raise, should return empty or skip the file
            assert isinstance(result, list)
        finally:
            # Restore permissions for cleanup
            zshrc.chmod(0o644)

    def test_detects_var_with_leading_whitespace(self, tmp_path, monkeypatch):
        """Test detection of export with leading whitespace."""
        from pathlib import Path

        mock_home = tmp_path / "home"
        mock_home.mkdir()
        zshrc = mock_home / ".zshrc"
        zshrc.write_text("  export ANTHROPIC_API_KEY=key\n")

        monkeypatch.setattr(Path, "home", lambda: mock_home)

        result = scan_shell_configs_for_anthropic()

        assert len(result) == 1
        assert result[0].var == "ANTHROPIC_API_KEY"

    def test_shell_config_var_dataclass(self):
        """Test ShellConfigVar dataclass."""
        var = ShellConfigVar(var="ANTHROPIC_API_KEY", file="~/.zshrc", line=42)
        assert var.var == "ANTHROPIC_API_KEY"
        assert var.file == "~/.zshrc"
        assert var.line == 42


@pytest.mark.unit
class TestCheckAnthropicEnvVars:
    """Tests for check_anthropic_env_vars()."""

    def test_no_anthropic_vars(self, tmp_path, monkeypatch):
        """Test no error when no ANTHROPIC_* vars are set."""
        from pathlib import Path

        # Remove any existing ANTHROPIC_* vars
        for key in list(os.environ.keys()):
            if key.startswith("ANTHROPIC_"):
                monkeypatch.delenv(key, raising=False)

        # Mock home with no config files
        mock_home = tmp_path / "home"
        mock_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: mock_home)

        # Should not raise
        check_anthropic_env_vars()

    def test_single_anthropic_var_raises(self, tmp_path, monkeypatch):
        """Test error when a single ANTHROPIC_* var is set."""
        from pathlib import Path

        for key in list(os.environ.keys()):
            if key.startswith("ANTHROPIC_"):
                monkeypatch.delenv(key, raising=False)

        mock_home = tmp_path / "home"
        mock_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: mock_home)

        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        with pytest.raises(SetupError) as exc_info:
            check_anthropic_env_vars()

        error = str(exc_info.value)
        assert "ANTHROPIC_API_KEY" in error
        assert "set in current environment" in error
        assert "unset ANTHROPIC_API_KEY" in error

    def test_multiple_anthropic_vars_raises(self, tmp_path, monkeypatch):
        """Test error lists all ANTHROPIC_* vars."""
        from pathlib import Path

        for key in list(os.environ.keys()):
            if key.startswith("ANTHROPIC_"):
                monkeypatch.delenv(key, raising=False)

        mock_home = tmp_path / "home"
        mock_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: mock_home)

        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://example.com")

        with pytest.raises(SetupError) as exc_info:
            check_anthropic_env_vars()

        error = str(exc_info.value)
        assert "ANTHROPIC_API_KEY" in error
        assert "ANTHROPIC_BASE_URL" in error
        assert "unset ANTHROPIC_API_KEY" in error
        assert "unset ANTHROPIC_BASE_URL" in error

    def test_shell_config_var_detected(self, tmp_path, monkeypatch):
        """Test error when ANTHROPIC_* var is in shell config."""
        from pathlib import Path

        for key in list(os.environ.keys()):
            if key.startswith("ANTHROPIC_"):
                monkeypatch.delenv(key, raising=False)

        mock_home = tmp_path / "home"
        mock_home.mkdir()
        zshrc = mock_home / ".zshrc"
        zshrc.write_text("export ANTHROPIC_API_KEY=sk-xxx\n")
        monkeypatch.setattr(Path, "home", lambda: mock_home)

        with pytest.raises(SetupError) as exc_info:
            check_anthropic_env_vars()

        error = str(exc_info.value)
        assert "ANTHROPIC_API_KEY" in error
        assert "~/.zshrc line 1" in error
        assert "unset ANTHROPIC_API_KEY" in error

    def test_both_env_and_config_detected(self, tmp_path, monkeypatch):
        """Test error when ANTHROPIC_* var is in both env and config."""
        from pathlib import Path

        for key in list(os.environ.keys()):
            if key.startswith("ANTHROPIC_"):
                monkeypatch.delenv(key, raising=False)

        mock_home = tmp_path / "home"
        mock_home.mkdir()
        zshrc = mock_home / ".zshrc"
        zshrc.write_text("export ANTHROPIC_MODEL=claude-3\n")
        monkeypatch.setattr(Path, "home", lambda: mock_home)

        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        with pytest.raises(SetupError) as exc_info:
            check_anthropic_env_vars()

        error = str(exc_info.value)
        assert "ANTHROPIC_API_KEY" in error
        assert "set in current environment" in error
        assert "ANTHROPIC_MODEL" in error
        assert "~/.zshrc line 1" in error
        assert "conflict with Kiln's Claude integration" in error


@pytest.mark.unit
class TestCheckClaudeInstallation:
    """Tests for check_claude_installation()."""

    def test_claude_not_found(self):
        """Test error when claude is not in PATH."""
        with patch("shutil.which", return_value=None):
            with pytest.raises(SetupError) as exc_info:
                check_claude_installation()

            assert "claude CLI not found" in str(exc_info.value)
            assert "anthropic.com" in str(exc_info.value)

    def test_native_installation_returns_info(self):
        """Test native installation returns ClaudeInfo."""
        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0, stdout="claude v1.0.45 (build 12345)\n"
                )
                result = check_claude_installation()

        assert isinstance(result, ClaudeInfo)
        assert result.path == "/usr/local/bin/claude"
        assert result.version == "1.0.45"
        assert result.install_method == "native"

    def test_npm_installation_returns_info(self):
        """Test npm installation returns ClaudeInfo."""
        with patch("shutil.which", return_value="/usr/local/lib/node_modules/@anthropic-ai/claude-code/bin/claude"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0, stdout="claude v1.0.45\n"
                )
                result = check_claude_installation()

        assert isinstance(result, ClaudeInfo)
        assert result.path == "/usr/local/lib/node_modules/@anthropic-ai/claude-code/bin/claude"
        assert result.version == "1.0.45"
        assert result.install_method == "npm"

    def test_npm_path_detection(self):
        """Test npm path detection via /npm/ in path."""
        with patch("shutil.which", return_value="/home/user/.npm/bin/claude"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0, stdout="claude v1.0.45\n"
                )
                result = check_claude_installation()

        assert isinstance(result, ClaudeInfo)
        assert result.install_method == "npm"

    def test_brew_installation_returns_info(self):
        """Test Homebrew installation returns ClaudeInfo."""
        with patch("shutil.which", return_value="/opt/homebrew/Cellar/claude/1.0.45/bin/claude"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0, stdout="claude v1.0.45\n"
                )
                result = check_claude_installation()

        assert isinstance(result, ClaudeInfo)
        assert result.path == "/opt/homebrew/Cellar/claude/1.0.45/bin/claude"
        assert result.version == "1.0.45"
        assert result.install_method == "brew"

    def test_brew_path_detection_homebrew(self):
        """Test brew path detection via /homebrew/ in path."""
        with patch("shutil.which", return_value="/usr/local/homebrew/bin/claude"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0, stdout="claude v1.0.45\n"
                )
                result = check_claude_installation()

        assert isinstance(result, ClaudeInfo)
        assert result.install_method == "brew"

    def test_version_parsing_without_v_prefix(self):
        """Test version parsing when version doesn't have v prefix."""
        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0, stdout="claude 2.1.0\n"
                )
                result = check_claude_installation()

        assert result.version == "2.1.0"

    def test_version_command_error(self):
        """Test error when claude --version fails."""
        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = subprocess.CalledProcessError(
                    1, "claude", stderr="error message"
                )
                with pytest.raises(SetupError) as exc_info:
                    check_claude_installation()

        assert "claude CLI error" in str(exc_info.value)


@pytest.mark.unit
class TestCheckRequiredTools:
    """Tests for check_required_tools()."""

    def test_all_tools_present(self, monkeypatch):
        """Test that ClaudeInfo is returned when all tools are present."""
        # Clear ANTHROPIC_* vars
        for key in list(os.environ.keys()):
            if key.startswith("ANTHROPIC_"):
                monkeypatch.delenv(key, raising=False)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="claude v1.0.45\n")
            with patch("shutil.which", return_value="/usr/local/bin/claude"):
                result = check_required_tools()

        assert isinstance(result, ClaudeInfo)
        assert result.path == "/usr/local/bin/claude"

    def test_gh_cli_missing(self, monkeypatch):
        """Test error when gh CLI is missing."""
        for key in list(os.environ.keys()):
            if key.startswith("ANTHROPIC_"):
                monkeypatch.delenv(key, raising=False)

        def side_effect(args, **kwargs):
            if args[0] == "gh":
                raise FileNotFoundError()
            return MagicMock(returncode=0, stdout="claude v1.0.45\n")

        with patch("subprocess.run", side_effect=side_effect):
            with pytest.raises(SetupError) as exc_info:
                check_required_tools()

            assert "gh CLI not found" in str(exc_info.value)
            assert "https://cli.github.com/" in str(exc_info.value)

    def test_claude_cli_missing(self, monkeypatch):
        """Test error when claude CLI is missing."""
        for key in list(os.environ.keys()):
            if key.startswith("ANTHROPIC_"):
                monkeypatch.delenv(key, raising=False)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            with patch("shutil.which", return_value=None):
                with pytest.raises(SetupError) as exc_info:
                    check_required_tools()

        assert "claude CLI not found" in str(exc_info.value)
        assert "anthropic.com" in str(exc_info.value)

    def test_anthropic_env_vars_checked_first(self, tmp_path, monkeypatch):
        """Test that ANTHROPIC_* env vars are checked before tools."""
        from pathlib import Path

        for key in list(os.environ.keys()):
            if key.startswith("ANTHROPIC_"):
                monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        # Mock home with no config files
        mock_home = tmp_path / "home"
        mock_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: mock_home)

        # Even if tools would fail, env var check should happen first
        with pytest.raises(SetupError) as exc_info:
            check_required_tools()

        assert "ANTHROPIC_API_KEY" in str(exc_info.value)
        assert "conflict with Kiln's Claude integration" in str(exc_info.value)

    def test_gh_cli_error(self, monkeypatch):
        """Test error when gh CLI returns an error."""
        for key in list(os.environ.keys()):
            if key.startswith("ANTHROPIC_"):
                monkeypatch.delenv(key, raising=False)

        def side_effect(args, **kwargs):
            if args[0] == "gh":
                raise subprocess.CalledProcessError(1, "gh", stderr=b"gh: command failed")
            return MagicMock(returncode=0, stdout="claude v1.0.45\n")

        with patch("subprocess.run", side_effect=side_effect):
            with pytest.raises(SetupError) as exc_info:
                check_required_tools()

            assert "gh CLI error" in str(exc_info.value)


@pytest.mark.unit
class TestConfigureGitCredentialEnv:
    """Tests for configure_git_credential_env()."""

    def test_single_hostname(self, monkeypatch):
        """Test environment variables set for single hostname."""
        # Clear any existing GIT_CONFIG_* vars
        for key in list(os.environ.keys()):
            if key.startswith("GIT_CONFIG_"):
                monkeypatch.delenv(key, raising=False)

        configure_git_credential_env({"github.com"})

        assert os.environ["GIT_CONFIG_COUNT"] == "1"
        assert os.environ["GIT_CONFIG_KEY_0"] == "credential.https://github.com.helper"
        assert os.environ["GIT_CONFIG_VALUE_0"] == "!gh auth git-credential"

    def test_multiple_hostnames_sorted(self, monkeypatch):
        """Test multiple hostnames are sorted and zero-indexed."""
        for key in list(os.environ.keys()):
            if key.startswith("GIT_CONFIG_"):
                monkeypatch.delenv(key, raising=False)

        configure_git_credential_env({"zebra.example.com", "alpha.example.com", "github.com"})

        assert os.environ["GIT_CONFIG_COUNT"] == "3"
        # Sorted order: alpha, github, zebra
        assert os.environ["GIT_CONFIG_KEY_0"] == "credential.https://alpha.example.com.helper"
        assert os.environ["GIT_CONFIG_VALUE_0"] == "!gh auth git-credential"
        assert os.environ["GIT_CONFIG_KEY_1"] == "credential.https://github.com.helper"
        assert os.environ["GIT_CONFIG_VALUE_1"] == "!gh auth git-credential"
        assert os.environ["GIT_CONFIG_KEY_2"] == "credential.https://zebra.example.com.helper"
        assert os.environ["GIT_CONFIG_VALUE_2"] == "!gh auth git-credential"

    def test_empty_hostname_set(self, monkeypatch):
        """Test empty hostname set sets count to zero."""
        for key in list(os.environ.keys()):
            if key.startswith("GIT_CONFIG_"):
                monkeypatch.delenv(key, raising=False)

        configure_git_credential_env(set())

        assert os.environ["GIT_CONFIG_COUNT"] == "0"

    def test_logs_configured_hostnames(self, monkeypatch):
        """Test that configured hostnames are logged at DEBUG level."""
        for key in list(os.environ.keys()):
            if key.startswith("GIT_CONFIG_"):
                monkeypatch.delenv(key, raising=False)

        with patch("src.setup.checks.logger") as mock_logger:
            configure_git_credential_env({"github.com", "ghes.company.com"})
            mock_logger.debug.assert_called_once()
            log_message = mock_logger.debug.call_args[0][0]
            assert "ghes.company.com" in log_message
            assert "github.com" in log_message

    def test_no_log_for_empty_set(self, monkeypatch):
        """Test that no log is produced for empty hostname set."""
        for key in list(os.environ.keys()):
            if key.startswith("GIT_CONFIG_"):
                monkeypatch.delenv(key, raising=False)

        with patch("src.setup.checks.logger") as mock_logger:
            configure_git_credential_env(set())
            mock_logger.debug.assert_not_called()


@pytest.mark.unit
class TestGetHostnamesFromProjectUrls:
    """Tests for get_hostnames_from_project_urls()."""

    def test_extracts_github_com(self):
        """Test extracting github.com from standard URL."""
        urls = ["https://github.com/orgs/test/projects/1"]
        result = get_hostnames_from_project_urls(urls)
        assert result == {"github.com"}

    def test_extracts_ghes_hostname(self):
        """Test extracting GHES hostname."""
        urls = ["https://ghes.company.com/orgs/test/projects/1"]
        result = get_hostnames_from_project_urls(urls)
        assert result == {"ghes.company.com"}

    def test_extracts_multiple_unique_hostnames(self):
        """Test extracting multiple unique hostnames."""
        urls = [
            "https://github.com/orgs/test/projects/1",
            "https://ghes.company.com/orgs/test/projects/2",
            "https://github.example.org/orgs/test/projects/3",
        ]
        result = get_hostnames_from_project_urls(urls)
        assert result == {"github.com", "ghes.company.com", "github.example.org"}

    def test_deduplicates_hostnames(self):
        """Test that duplicate hostnames are deduplicated."""
        urls = [
            "https://github.com/orgs/test/projects/1",
            "https://github.com/orgs/other/projects/2",
            "https://github.com/orgs/third/projects/3",
        ]
        result = get_hostnames_from_project_urls(urls)
        assert result == {"github.com"}

    def test_empty_list_returns_github_com(self):
        """Test that empty list defaults to github.com."""
        result = get_hostnames_from_project_urls([])
        assert result == {"github.com"}

    def test_malformed_url_defaults_to_github_com(self):
        """Test that malformed URLs default to github.com."""
        urls = ["not-a-url", "just-some-text"]
        result = get_hostnames_from_project_urls(urls)
        assert result == {"github.com"}

    def test_mixed_valid_and_invalid_urls(self):
        """Test mixed valid and invalid URLs."""
        urls = [
            "https://ghes.company.com/orgs/test/projects/1",
            "not-a-url",
            "https://github.com/orgs/test/projects/2",
        ]
        result = get_hostnames_from_project_urls(urls)
        assert result == {"ghes.company.com", "github.com"}

    def test_http_url_also_works(self):
        """Test that http (non-https) URLs are also parsed."""
        urls = ["http://github.internal.com/orgs/test/projects/1"]
        result = get_hostnames_from_project_urls(urls)
        assert result == {"github.internal.com"}

    def test_url_with_port(self):
        """Test URL with port number."""
        urls = ["https://github.local:8443/orgs/test/projects/1"]
        result = get_hostnames_from_project_urls(urls)
        assert result == {"github.local:8443"}


@pytest.mark.unit
class TestCheckForUpdates:
    """Tests for check_for_updates()."""

    FORMULA_CONTENT = b'class Kiln < Formula\n  version "2.0.0"\n  url "https://example.com"\nend'

    def _mock_urlopen(self, content: bytes) -> MagicMock:
        """Create a mock urlopen context manager that returns content."""
        mock_response = MagicMock()
        mock_response.read.return_value = content
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        return mock_response

    def test_returns_update_info_when_newer_version_available(self, tmp_path) -> None:
        """Test: returns UpdateInfo when newer version is available."""
        kiln_dir = tmp_path / ".kiln"

        with patch("src.setup.checks.urllib.request.urlopen", return_value=self._mock_urlopen(self.FORMULA_CONTENT)):
            with patch("src.cli.__version__", "1.0.0"):
                result = check_for_updates(kiln_dir=kiln_dir)

        assert result is not None
        assert isinstance(result, UpdateInfo)
        assert result.latest_version == "2.0.0"
        assert result.current_version == "1.0.0"

    def test_returns_none_when_version_matches(self, tmp_path) -> None:
        """Test: returns None when version matches (up-to-date)."""
        kiln_dir = tmp_path / ".kiln"
        formula = b'class Kiln < Formula\n  version "1.1.0"\nend'

        with patch("src.setup.checks.urllib.request.urlopen", return_value=self._mock_urlopen(formula)):
            with patch("src.cli.__version__", "1.1.0"):
                result = check_for_updates(kiln_dir=kiln_dir)

        assert result is None

    def test_returns_none_on_network_timeout(self, tmp_path) -> None:
        """Test: returns None on network timeout."""
        kiln_dir = tmp_path / ".kiln"

        with patch("src.setup.checks.urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")):
            result = check_for_updates(kiln_dir=kiln_dir)

        assert result is None

    def test_returns_none_on_http_error(self, tmp_path) -> None:
        """Test: returns None on HTTP error (404, 500)."""
        kiln_dir = tmp_path / ".kiln"

        with patch(
            "src.setup.checks.urllib.request.urlopen",
            side_effect=urllib.error.HTTPError(
                url="https://example.com", code=404, msg="Not Found", hdrs=MagicMock(), fp=BytesIO(b"")
            ),
        ):
            result = check_for_updates(kiln_dir=kiln_dir)

        assert result is None

    def test_returns_none_on_malformed_formula_content(self, tmp_path) -> None:
        """Test: returns None on malformed formula content (no version string)."""
        kiln_dir = tmp_path / ".kiln"
        malformed = b"class Kiln < Formula\n  url 'https://example.com'\nend"

        with patch("src.setup.checks.urllib.request.urlopen", return_value=self._mock_urlopen(malformed)):
            with patch("src.cli.__version__", "1.0.0"):
                result = check_for_updates(kiln_dir=kiln_dir)

        assert result is None

    def test_cache_prevents_repeat_checks_within_24_hours(self, tmp_path) -> None:
        """Test: cache file prevents repeat checks within 24 hours."""
        kiln_dir = tmp_path / ".kiln"
        kiln_dir.mkdir()
        cache_file = kiln_dir / CACHE_FILE_NAME
        cache_file.touch()  # Fresh cache file (mtime = now)

        with patch("src.setup.checks.urllib.request.urlopen") as mock_urlopen:
            result = check_for_updates(kiln_dir=kiln_dir)

        assert result is None
        mock_urlopen.assert_not_called()

    def test_cache_older_than_24_hours_triggers_new_check(self, tmp_path) -> None:
        """Test: cache file older than 24 hours triggers new check."""
        kiln_dir = tmp_path / ".kiln"
        kiln_dir.mkdir()
        cache_file = kiln_dir / CACHE_FILE_NAME
        cache_file.touch()

        # Set mtime to 25 hours ago
        old_time = time.time() - (CACHE_MAX_AGE_SECONDS + 3600)
        os.utime(cache_file, (old_time, old_time))

        with patch("src.setup.checks.urllib.request.urlopen", return_value=self._mock_urlopen(self.FORMULA_CONTENT)):
            with patch("src.cli.__version__", "1.0.0"):
                result = check_for_updates(kiln_dir=kiln_dir)

        assert result is not None
        assert result.latest_version == "2.0.0"

    def test_cache_file_created_after_successful_check(self, tmp_path) -> None:
        """Test: cache file is created/updated after successful check."""
        kiln_dir = tmp_path / ".kiln"

        with patch("src.setup.checks.urllib.request.urlopen", return_value=self._mock_urlopen(self.FORMULA_CONTENT)):
            with patch("src.cli.__version__", "1.0.0"):
                check_for_updates(kiln_dir=kiln_dir)

        cache_file = kiln_dir / CACHE_FILE_NAME
        assert cache_file.exists()

    def test_cache_file_created_when_up_to_date(self, tmp_path) -> None:
        """Test: cache file is created/updated after check when already up-to-date."""
        kiln_dir = tmp_path / ".kiln"
        formula = b'class Kiln < Formula\n  version "1.1.0"\nend'

        with patch("src.setup.checks.urllib.request.urlopen", return_value=self._mock_urlopen(formula)):
            with patch("src.cli.__version__", "1.1.0"):
                result = check_for_updates(kiln_dir=kiln_dir)

        assert result is None
        cache_file = kiln_dir / CACHE_FILE_NAME
        assert cache_file.exists()

    def test_works_when_kiln_directory_does_not_exist(self, tmp_path) -> None:
        """Test: works when .kiln/ directory doesn't exist yet (creates it)."""
        kiln_dir = tmp_path / ".kiln"
        assert not kiln_dir.exists()

        with patch("src.setup.checks.urllib.request.urlopen", return_value=self._mock_urlopen(self.FORMULA_CONTENT)):
            with patch("src.cli.__version__", "1.0.0"):
                result = check_for_updates(kiln_dir=kiln_dir)

        assert result is not None
        assert kiln_dir.exists()
        assert (kiln_dir / CACHE_FILE_NAME).exists()

    def test_fails_silently_when_cache_directory_cannot_be_created(self, tmp_path) -> None:
        """Test: fails silently when cache directory can't be created."""
        # Use a path that can't be created (file exists where directory is expected)
        blocker = tmp_path / ".kiln"
        blocker.write_text("not a directory")  # File blocking directory creation

        with patch("src.setup.checks.urllib.request.urlopen", return_value=self._mock_urlopen(self.FORMULA_CONTENT)):
            with patch("src.cli.__version__", "1.0.0"):
                result = check_for_updates(kiln_dir=blocker)

        # Should fail silently and return None
        assert result is None


@pytest.mark.unit
class TestValidateProjectColumns:
    """Tests for validate_project_columns()."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock GitHubTicketClient."""
        client = MagicMock()
        return client

    def test_only_backlog_creates_columns(self, mock_client):
        """Test that columns are created when only Backlog exists."""
        mock_client.get_board_metadata.return_value = {
            "status_field_id": "field_123",
            "status_options": {"Backlog": "opt_backlog"},
        }

        result = validate_project_columns(mock_client, "https://github.com/orgs/test/projects/1")

        assert result.action == "created"
        assert "Research" in result.message
        mock_client.update_status_field_options.assert_called_once()

        # Verify the options passed
        call_args = mock_client.update_status_field_options.call_args
        options = call_args[0][1]
        option_names = [opt["name"] for opt in options]
        assert option_names == REQUIRED_COLUMN_NAMES

    def test_all_columns_correct_order(self, mock_client):
        """Test no action when all columns present in correct order."""
        # The status_options dict preserves insertion order in Python 3.7+
        # We need to simulate the order matching REQUIRED_COLUMN_NAMES
        ordered_options = {}
        for name in REQUIRED_COLUMN_NAMES:
            ordered_options[name] = f"opt_{name}"

        mock_client.get_board_metadata.return_value = {
            "status_field_id": "field_123",
            "status_options": ordered_options,
        }

        result = validate_project_columns(mock_client, "https://github.com/orgs/test/projects/1")

        assert result.action == "ok"
        mock_client.update_status_field_options.assert_not_called()

    def test_all_columns_wrong_order_reorders(self, mock_client):
        """Test reordering when all columns present but wrong order."""
        # Reverse order
        reversed_options = {}
        for name in reversed(REQUIRED_COLUMN_NAMES):
            reversed_options[name] = f"opt_{name}"

        mock_client.get_board_metadata.return_value = {
            "status_field_id": "field_123",
            "status_options": reversed_options,
        }

        result = validate_project_columns(mock_client, "https://github.com/orgs/test/projects/1")

        assert result.action == "reordered"
        assert "reordered" in result.message.lower()
        mock_client.update_status_field_options.assert_called_once()

        # Verify the options are in correct order with IDs
        call_args = mock_client.update_status_field_options.call_args
        options = call_args[0][1]
        option_names = [opt["name"] for opt in options]
        assert option_names == REQUIRED_COLUMN_NAMES
        # Each should have an ID
        for opt in options:
            assert "id" in opt

    def test_extra_columns_raises_error(self, mock_client):
        """Test error when extra columns exist."""
        options = {name: f"opt_{name}" for name in REQUIRED_COLUMN_NAMES}
        options["CustomColumn"] = "opt_custom"

        mock_client.get_board_metadata.return_value = {
            "status_field_id": "field_123",
            "status_options": options,
        }

        with pytest.raises(SetupError) as exc_info:
            validate_project_columns(mock_client, "https://github.com/orgs/test/projects/1")

        error = str(exc_info.value)
        assert "not compatible" in error
        assert "CustomColumn" in error

    def test_missing_columns_with_extras_raises_error(self, mock_client):
        """Test error when missing required columns but has extras."""
        mock_client.get_board_metadata.return_value = {
            "status_field_id": "field_123",
            "status_options": {
                "Backlog": "opt_backlog",
                "Prepare": "opt_prepare",  # Deprecated
            },
        }

        with pytest.raises(SetupError) as exc_info:
            validate_project_columns(mock_client, "https://github.com/orgs/test/projects/1")

        error = str(exc_info.value)
        assert "not compatible" in error
        # Should mention the extra column
        assert "Prepare" in error or "Extra columns" in error

    def test_missing_status_field_raises_error(self, mock_client):
        """Test error when Status field not found."""
        mock_client.get_board_metadata.return_value = {
            "status_field_id": None,
            "status_options": {},
        }

        with pytest.raises(SetupError) as exc_info:
            validate_project_columns(mock_client, "https://github.com/orgs/test/projects/1")

        assert "Could not find Status field" in str(exc_info.value)

    def test_error_message_includes_instructions(self, mock_client):
        """Test that error message includes instructions for fixing."""
        mock_client.get_board_metadata.return_value = {
            "status_field_id": "field_123",
            "status_options": {"Backlog": "opt_backlog", "Custom": "opt_custom"},
        }

        with pytest.raises(SetupError) as exc_info:
            validate_project_columns(mock_client, "https://github.com/orgs/test/projects/1")

        error = str(exc_info.value)
        # Should include the project URL
        assert "https://github.com/orgs/test/projects/1" in error
        # Should include instruction options
        assert "Option 1" in error
        assert "Option 2" in error
        # Should list required columns
        assert "Backlog" in error
        assert "Research" in error
        assert "Done" in error

    def test_validation_result_dataclass(self):
        """Test ValidationResult dataclass."""
        result = ValidationResult(
            project_url="https://github.com/orgs/test/projects/1",
            action="ok",
            message="Test message",
        )
        assert result.project_url == "https://github.com/orgs/test/projects/1"
        assert result.action == "ok"
        assert result.message == "Test message"

    def test_github_defaults_replaces_columns(self, mock_client):
        """Test that GitHub default columns are replaced with Kiln columns."""
        # Simulate GitHub defaults - order preserved by dict in Python 3.7+
        mock_client.get_board_metadata.return_value = {
            "status_field_id": "field_123",
            "status_options": {
                "Backlog": "opt_1",
                "Ready": "opt_2",
                "In progress": "opt_3",
                "In review": "opt_4",
                "Done": "opt_5",
            },
        }
        mock_client.get_board_items.return_value = []  # No items to migrate

        result = validate_project_columns(
            mock_client, "https://github.com/orgs/test/projects/1"
        )

        assert result.action == "replaced"
        assert "Replaced GitHub default columns" in result.message
        mock_client.update_status_field_options.assert_called_once()

        # Verify the options passed include all 6 Kiln columns
        call_args = mock_client.update_status_field_options.call_args
        options = call_args[0][1]
        option_names = [opt["name"] for opt in options]
        assert option_names == REQUIRED_COLUMN_NAMES

    def test_github_defaults_migrates_items_to_backlog(self, mock_client):
        """Test that items in deprecated statuses are migrated to Backlog."""
        mock_client.get_board_metadata.return_value = {
            "status_field_id": "field_123",
            "status_options": {
                "Backlog": "opt_1",
                "Ready": "opt_2",
                "In progress": "opt_3",
                "In review": "opt_4",
                "Done": "opt_5",
            },
        }

        # Mock items in deprecated statuses
        from src.interfaces import TicketItem

        mock_items = [
            TicketItem(
                item_id="item1",
                board_url="https://github.com/orgs/test/projects/1",
                ticket_id=1,
                repo="github.com/test/repo",
                status="Ready",
                title="Test 1",
                labels=set(),
                state="OPEN",
            ),
            TicketItem(
                item_id="item2",
                board_url="https://github.com/orgs/test/projects/1",
                ticket_id=2,
                repo="github.com/test/repo",
                status="In progress",
                title="Test 2",
                labels=set(),
                state="OPEN",
            ),
            TicketItem(
                item_id="item3",
                board_url="https://github.com/orgs/test/projects/1",
                ticket_id=3,
                repo="github.com/test/repo",
                status="Backlog",
                title="Test 3",
                labels=set(),
                state="OPEN",
            ),
        ]
        mock_client.get_board_items.return_value = mock_items

        result = validate_project_columns(
            mock_client, "https://github.com/orgs/test/projects/1"
        )

        assert result.action == "replaced"
        assert "2 item(s) moved to Backlog" in result.message
        # Verify update_item_status called for items in deprecated statuses
        assert mock_client.update_item_status.call_count == 2

    def test_partial_github_defaults_raises_error(self, mock_client):
        """Test that partial GitHub defaults (e.g., missing one column) still errors."""
        # Only 4 of the 5 GitHub defaults - missing "In Review"
        mock_client.get_board_metadata.return_value = {
            "status_field_id": "field_123",
            "status_options": {
                "Backlog": "opt_1",
                "Ready": "opt_2",
                "In progress": "opt_3",
                "Done": "opt_5",
            },
        }

        with pytest.raises(SetupError):
            validate_project_columns(
                mock_client, "https://github.com/orgs/test/projects/1"
            )

    def test_github_defaults_empty_project_no_items(self, mock_client):
        """Test GitHub defaults with no items to migrate (fresh project)."""
        mock_client.get_board_metadata.return_value = {
            "status_field_id": "field_123",
            "status_options": {
                "Backlog": "opt_1",
                "Ready": "opt_2",
                "In progress": "opt_3",
                "In review": "opt_4",
                "Done": "opt_5",
            },
        }
        mock_client.get_board_items.return_value = []  # Empty project

        result = validate_project_columns(
            mock_client, "https://github.com/orgs/test/projects/1"
        )

        assert result.action == "replaced"
        # Message should NOT contain migration count if no items migrated
        assert "item(s) moved to Backlog" not in result.message
        # update_item_status should not have been called
        mock_client.update_item_status.assert_not_called()

    def test_github_default_columns_constant(self):
        """Test that GITHUB_DEFAULT_COLUMNS has the correct values."""
        expected = frozenset(
            {"Backlog", "Ready", "In progress", "In review", "Done"}
        )
        assert expected == GITHUB_DEFAULT_COLUMNS
        assert isinstance(GITHUB_DEFAULT_COLUMNS, frozenset)


@pytest.mark.unit
class TestUpdateStatusFieldOptions:
    """Tests for GitHubTicketClient.update_status_field_options()."""

    def test_update_status_field_options_calls_graphql(self):
        """Test that update_status_field_options executes GraphQL mutation."""
        from src.ticket_clients.github import GitHubTicketClient

        client = GitHubTicketClient(tokens={"github.com": "test-token"})

        with patch.object(client, "_execute_graphql_query") as mock_query:
            options = [
                {"name": "Backlog", "color": "GRAY", "description": "Test"},
                {"name": "Done", "color": "GREEN", "description": "Complete"},
            ]
            client.update_status_field_options("field_123", options)

            mock_query.assert_called_once()
            call_args = mock_query.call_args
            # Check mutation was called with correct field ID
            assert call_args[0][1]["fieldId"] == "field_123"
            # Check options were passed correctly
            passed_options = call_args[0][1]["options"]
            assert len(passed_options) == 2
            # ProjectV2SingleSelectFieldOptionInput only accepts name, color, description
            assert "id" not in passed_options[0]
            assert "id" not in passed_options[1]
            assert passed_options[1]["name"] == "Done"

    def test_update_status_field_options_with_hostname(self):
        """Test that hostname is passed correctly."""
        from src.ticket_clients.github import GitHubTicketClient

        client = GitHubTicketClient(tokens={"github.mycompany.com": "test-token"})

        with patch.object(client, "_execute_graphql_query") as mock_query:
            options = [{"name": "Test", "color": "GRAY", "description": ""}]
            client.update_status_field_options(
                "field_123", options, hostname="github.mycompany.com"
            )

            mock_query.assert_called_once()
            call_args = mock_query.call_args
            assert call_args[1]["hostname"] == "github.mycompany.com"
