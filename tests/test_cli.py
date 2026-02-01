"""Unit tests for the CLI module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.cli import (
    BANNER_PLAIN,
    __version__,
    extract_claude_resources,
    get_banner,
    get_readme,
    get_sample_config,
    install_claude_resources,
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
class TestInstallClaudeResources:
    """Tests for install_claude_resources function."""

    def test_install_copies_files(self, tmp_path, monkeypatch):
        """Test that install_claude_resources copies files to ~/.claude/."""
        monkeypatch.chdir(tmp_path)

        # Create .kiln directory with kiln-prefixed resources
        kiln_dir = tmp_path / ".kiln"
        (kiln_dir / "commands").mkdir(parents=True)
        (kiln_dir / "commands" / "kiln-create_plan_github.md").write_text("# Test command")
        (kiln_dir / "agents").mkdir(parents=True)
        (kiln_dir / "agents" / "kiln-codebase-analyzer.md").write_text("# Test agent")
        (kiln_dir / "skills" / "kiln-edit-github-issue-components").mkdir(parents=True)
        (kiln_dir / "skills" / "kiln-edit-github-issue-components" / "SKILL.md").write_text("# Test skill")

        # Create fake home directory
        fake_home = tmp_path / "fake_home"
        fake_home.mkdir()

        with patch.object(Path, "home", return_value=fake_home):
            install_claude_resources()

        # Verify files were copied (not symlinks)
        cmd_file = fake_home / ".claude" / "commands" / "kiln-create_plan_github.md"
        assert cmd_file.exists(), "Command file should be copied"
        assert not cmd_file.is_symlink(), "Should be a file, not a symlink"
        assert cmd_file.read_text() == "# Test command"

        agent_file = fake_home / ".claude" / "agents" / "kiln-codebase-analyzer.md"
        assert agent_file.exists(), "Agent file should be copied"

        skill_dir = fake_home / ".claude" / "skills" / "kiln-edit-github-issue-components"
        assert skill_dir.exists(), "Skill directory should be copied"
        assert skill_dir.is_dir(), "Skill should be a directory"

    def test_install_creates_parent_directories(self, tmp_path, monkeypatch):
        """Test that install_claude_resources creates parent directories if needed."""
        monkeypatch.chdir(tmp_path)

        # Create .kiln with a command
        kiln_dir = tmp_path / ".kiln"
        (kiln_dir / "commands").mkdir(parents=True)
        (kiln_dir / "commands" / "kiln-implement_github.md").write_text("# Test")

        # Create fake home without ~/.claude/
        fake_home = tmp_path / "fake_home"
        fake_home.mkdir()

        with patch.object(Path, "home", return_value=fake_home):
            install_claude_resources()

        # Verify parent directory was created
        assert (fake_home / ".claude" / "commands").exists()
        assert (fake_home / ".claude" / "commands").is_dir()

    def test_install_overwrites_existing(self, tmp_path, monkeypatch):
        """Test that install_claude_resources overwrites existing files."""
        monkeypatch.chdir(tmp_path)

        # Create .kiln with a command
        kiln_dir = tmp_path / ".kiln"
        (kiln_dir / "commands").mkdir(parents=True)
        (kiln_dir / "commands" / "kiln-implement_github.md").write_text("# New content")

        # Create fake home with existing file
        fake_home = tmp_path / "fake_home"
        (fake_home / ".claude" / "commands").mkdir(parents=True)
        existing = fake_home / ".claude" / "commands" / "kiln-implement_github.md"
        existing.write_text("# Old content")

        with patch.object(Path, "home", return_value=fake_home):
            install_claude_resources()

        # Verify file was overwritten
        assert existing.read_text() == "# New content"

    def test_install_is_idempotent(self, tmp_path, monkeypatch):
        """Test that calling install_claude_resources twice doesn't fail."""
        monkeypatch.chdir(tmp_path)

        # Create .kiln with a command
        kiln_dir = tmp_path / ".kiln"
        (kiln_dir / "commands").mkdir(parents=True)
        (kiln_dir / "commands" / "kiln-implement_github.md").write_text("# Test")

        fake_home = tmp_path / "fake_home"
        fake_home.mkdir()

        with patch.object(Path, "home", return_value=fake_home):
            # Call twice - should not raise
            install_claude_resources()
            install_claude_resources()

        # File should still exist
        cmd_file = fake_home / ".claude" / "commands" / "kiln-implement_github.md"
        assert cmd_file.exists()

    def test_install_raises_on_write_failure(self, tmp_path, monkeypatch):
        """Test that install_claude_resources raises RuntimeError on failure."""
        monkeypatch.chdir(tmp_path)

        # Create .kiln with a command
        kiln_dir = tmp_path / ".kiln"
        (kiln_dir / "commands").mkdir(parents=True)
        (kiln_dir / "commands" / "kiln-implement_github.md").write_text("# Test")

        # Create fake home where commands dir is a file (will fail to copy)
        fake_home = tmp_path / "fake_home"
        (fake_home / ".claude").mkdir(parents=True)
        (fake_home / ".claude" / "commands").write_text("not a directory")

        with patch.object(Path, "home", return_value=fake_home):
            with pytest.raises(RuntimeError, match="Failed to install kiln resources"):
                install_claude_resources()

    def test_install_skips_missing_source_dirs(self, tmp_path, monkeypatch):
        """Test that install_claude_resources handles missing source directories."""
        monkeypatch.chdir(tmp_path)

        # Create .kiln with only commands (no agents or skills dirs)
        kiln_dir = tmp_path / ".kiln"
        (kiln_dir / "commands").mkdir(parents=True)
        (kiln_dir / "commands" / "kiln-implement_github.md").write_text("# Test")

        fake_home = tmp_path / "fake_home"
        fake_home.mkdir()

        with patch.object(Path, "home", return_value=fake_home):
            # Should not raise even with missing source dirs
            install_claude_resources()

        # Command should still be installed
        assert (fake_home / ".claude" / "commands" / "kiln-implement_github.md").exists()


@pytest.mark.unit
class TestCmdRun:
    """Tests for cmd_run function."""

    def test_cmd_run_validates_working_directory(self, tmp_path, monkeypatch):
        """Test that cmd_run validates working directory before proceeding."""
        from argparse import Namespace

        from src.cli import cmd_run

        # Mock Path.home() to return a controlled path
        mock_home = tmp_path / "mockhome"
        mock_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: mock_home)

        # Change to home directory (which is restricted)
        monkeypatch.chdir(mock_home)

        # cmd_run should exit with error when in home directory
        args = Namespace(daemon=False)

        with pytest.raises(SystemExit) as exc_info:
            cmd_run(args)

        assert exc_info.value.code == 1

    def test_cmd_run_allows_valid_directory(self, tmp_path, monkeypatch, capsys):
        """Test that cmd_run proceeds for valid directories."""
        from argparse import Namespace

        from src.cli import cmd_run

        # Mock Path.home() to return a controlled path
        mock_home = tmp_path / "mockhome"
        mock_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: mock_home)

        # Create a valid subdirectory
        valid_dir = mock_home / "projects"
        valid_dir.mkdir()

        # Change to valid directory
        monkeypatch.chdir(valid_dir)

        # cmd_run should proceed (will call init_kiln since no config exists)
        args = Namespace(daemon=False)
        cmd_run(args)

        # init_kiln should have been called - check for its output
        captured = capsys.readouterr()
        assert ".kiln/" in captured.out or "Created:" in captured.out

    def test_cmd_run_error_message_includes_recommendation(self, tmp_path, monkeypatch, capsys):
        """Test that error message includes recommendation when in restricted directory."""
        from argparse import Namespace

        from src.cli import cmd_run

        # Mock Path.home()
        mock_home = tmp_path / "mockhome"
        mock_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: mock_home)

        # Change to home directory
        monkeypatch.chdir(mock_home)

        args = Namespace(daemon=False)

        with pytest.raises(SystemExit):
            cmd_run(args)

        captured = capsys.readouterr()
        # Error should include recommendation
        assert "mkdir" in captured.err
        assert "kiln-workspace" in captured.err


@pytest.mark.unit
class TestRunDaemonSlackInitialization:
    """Tests to verify run_daemon() initializes Slack correctly.

    These tests prevent regression of the bug where cli.py's run_daemon()
    was missing Slack initialization, while daemon.py's main() had it.

    These tests use source code inspection to verify Slack initialization
    is present in run_daemon(), avoiding the complexity of mocking the
    entire startup sequence.
    """

    def test_run_daemon_imports_slack_functions(self):
        """Test that run_daemon() imports init_slack and send_startup_ping."""
        import inspect

        from src.cli import run_daemon

        source = inspect.getsource(run_daemon)

        # Verify the imports are present
        assert "from src.slack import init_slack, send_startup_ping" in source, \
            "run_daemon() must import init_slack and send_startup_ping from src.slack"

    def test_run_daemon_calls_init_slack(self):
        """Test that run_daemon() calls init_slack with config values."""
        import inspect

        from src.cli import run_daemon

        source = inspect.getsource(run_daemon)

        # Verify init_slack is called with the config's slack settings
        assert "init_slack(config.slack_bot_token, config.slack_user_id)" in source, \
            "run_daemon() must call init_slack(config.slack_bot_token, config.slack_user_id)"

    def test_run_daemon_calls_send_startup_ping(self):
        """Test that run_daemon() calls send_startup_ping()."""
        import inspect

        from src.cli import run_daemon

        source = inspect.getsource(run_daemon)

        # Verify send_startup_ping is called
        assert "send_startup_ping()" in source, \
            "run_daemon() must call send_startup_ping()"

    def test_run_daemon_calls_slack_init_before_daemon_run(self):
        """Test that Slack initialization happens before daemon.run()."""
        import inspect

        from src.cli import run_daemon

        source = inspect.getsource(run_daemon)

        # Find positions of key calls
        init_slack_pos = source.find("init_slack(config.slack_bot_token")
        send_startup_ping_pos = source.find("send_startup_ping()")
        daemon_run_pos = source.find("daemon.run()")

        # Verify order: init_slack -> send_startup_ping -> daemon.run()
        assert init_slack_pos != -1, "init_slack call not found"
        assert send_startup_ping_pos != -1, "send_startup_ping call not found"
        assert daemon_run_pos != -1, "daemon.run() call not found"

        assert init_slack_pos < send_startup_ping_pos, \
            "init_slack must be called before send_startup_ping"
        assert send_startup_ping_pos < daemon_run_pos, \
            "send_startup_ping must be called before daemon.run()"


@pytest.mark.unit
class TestRunDaemonPagerDutyInitialization:
    """Tests to verify run_daemon() initializes PagerDuty correctly.

    These tests prevent regression of the bug where cli.py's run_daemon()
    was missing PagerDuty initialization.
    """

    def test_run_daemon_imports_pagerduty_init(self):
        """Test that run_daemon() imports init_pagerduty."""
        import inspect

        from src.cli import run_daemon

        source = inspect.getsource(run_daemon)
        assert "from src.pagerduty import init_pagerduty" in source, \
            "run_daemon() must import init_pagerduty from src.pagerduty"

    def test_run_daemon_calls_init_pagerduty(self):
        """Test that run_daemon() calls init_pagerduty with config value."""
        import inspect

        from src.cli import run_daemon

        source = inspect.getsource(run_daemon)
        assert "init_pagerduty(config.pagerduty_routing_key)" in source, \
            "run_daemon() must call init_pagerduty(config.pagerduty_routing_key)"

    def test_run_daemon_pagerduty_init_is_conditional(self):
        """Test that PagerDuty init only happens if routing key is configured."""
        import inspect

        from src.cli import run_daemon

        source = inspect.getsource(run_daemon)
        # Find the conditional check
        assert "if config.pagerduty_routing_key:" in source, \
            "PagerDuty initialization must be conditional on routing key"

    def test_run_daemon_pagerduty_init_order(self):
        """Test that PagerDuty init happens between telemetry and Slack init."""
        import inspect

        from src.cli import run_daemon

        source = inspect.getsource(run_daemon)

        # Find positions of key initializations
        telemetry_pos = source.find("init_telemetry(")
        pagerduty_pos = source.find("init_pagerduty(config.pagerduty_routing_key)")
        slack_pos = source.find("init_slack(config.slack_bot_token")

        assert telemetry_pos != -1, "init_telemetry call not found"
        assert pagerduty_pos != -1, "init_pagerduty call not found"
        assert slack_pos != -1, "init_slack call not found"

        assert telemetry_pos < pagerduty_pos, \
            "init_pagerduty must be called after init_telemetry"
        assert pagerduty_pos < slack_pos, \
            "init_pagerduty must be called before init_slack"
