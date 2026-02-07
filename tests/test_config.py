"""Unit tests for the config module."""

import pytest

from src.config import (
    Config,
    determine_workspace_dir,
    load_config,
    load_config_from_env,
    load_config_from_file,
    parse_config_file,
)


@pytest.mark.unit
class TestConfig:
    """Tests for Config dataclass."""

    def test_config_creation_with_defaults(self):
        """Test creating a Config instance with default values."""
        config = Config(
            github_token="test_token",
            project_urls=["https://github.com/orgs/chronoboost/projects/6/views/2"],
        )

        assert config.github_token == "test_token"
        assert config.project_urls == ["https://github.com/orgs/chronoboost/projects/6/views/2"]
        assert config.poll_interval == 30
        assert config.database_path == ".kiln/kiln.db"
        assert config.workspace_dir == "worktrees"
        assert config.watched_statuses == ["Research", "Plan", "Implement"]
        assert config.max_concurrent_workflows == 6
        assert config.log_file == ".kiln/logs/kiln.log"

    def test_config_creation_with_custom_values(self):
        """Test creating a Config instance with custom values."""
        config = Config(
            github_token="custom_token",
            project_urls=[
                "https://github.com/orgs/myorg/projects/1",
                "https://github.com/orgs/myorg/projects/2",
            ],
            poll_interval=60,
            database_path="custom.db",
            workspace_dir="custom_workspaces",
            watched_statuses=["Todo", "In Progress"],
        )

        assert config.github_token == "custom_token"
        assert config.project_urls == [
            "https://github.com/orgs/myorg/projects/1",
            "https://github.com/orgs/myorg/projects/2",
        ]
        assert config.poll_interval == 60
        assert config.database_path == "custom.db"
        assert config.workspace_dir == "custom_workspaces"
        assert config.watched_statuses == ["Todo", "In Progress"]

    def test_config_watched_statuses_is_mutable(self):
        """Test that watched_statuses list is independent for each instance."""
        config1 = Config(
            github_token="token1", project_urls=["https://github.com/orgs/test/projects/1"]
        )
        config2 = Config(
            github_token="token2", project_urls=["https://github.com/orgs/test/projects/2"]
        )

        config1.watched_statuses.append("NewStatus")

        assert "NewStatus" in config1.watched_statuses
        assert "NewStatus" not in config2.watched_statuses


@pytest.mark.unit
class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_config_with_all_env_vars(self, monkeypatch):
        """Test load_config reads all environment variables correctly."""
        monkeypatch.setenv("GITHUB_TOKEN", "env_token")
        monkeypatch.setenv(
            "PROJECT_URLS",
            "https://github.com/orgs/test/projects/1,https://github.com/orgs/test/projects/2",
        )
        monkeypatch.setenv("POLL_INTERVAL", "120")
        monkeypatch.setenv("DATABASE_PATH", "env.db")
        monkeypatch.setenv("WATCHED_STATUSES", "Status1, Status2, Status3")
        monkeypatch.setenv("USERNAME_SELF", "user1")

        config = load_config_from_env()

        assert config.github_token == "env_token"
        assert config.project_urls == [
            "https://github.com/orgs/test/projects/1",
            "https://github.com/orgs/test/projects/2",
        ]
        assert config.poll_interval == 120
        assert config.database_path == "env.db"
        assert config.watched_statuses == ["Status1", "Status2", "Status3"]
        assert config.username_self == "user1"

    def test_load_config_with_minimal_env_vars(self, tmp_path, monkeypatch):
        """Test load_config applies defaults when only required vars are set."""
        # Use clean directory so determine_workspace_dir() returns "worktrees"
        monkeypatch.chdir(tmp_path)
        # Clear any existing environment variables
        for key in [
            "PROJECT_URLS",
            "POLL_INTERVAL",
            "DATABASE_PATH",
            "WATCHED_STATUSES",
            "MAX_CONCURRENT_WORKFLOWS",
        ]:
            monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("GITHUB_TOKEN", "minimal_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/chronoboost/projects/6/views/2")
        monkeypatch.setenv("USERNAME_SELF", "testuser")

        config = load_config_from_env()

        assert config.github_token == "minimal_token"
        assert config.project_urls == ["https://github.com/orgs/chronoboost/projects/6/views/2"]
        assert config.poll_interval == 30
        assert config.database_path == ".kiln/kiln.db"
        assert config.workspace_dir == "worktrees"
        assert config.watched_statuses == ["Research", "Plan", "Implement"]
        assert config.max_concurrent_workflows == 6
        assert config.username_self == "testuser"

    def test_load_config_missing_github_token(self, monkeypatch):
        """Test load_config requires GITHUB_TOKEN when no GHES config."""
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_ENTERPRISE_HOST", raising=False)
        monkeypatch.delenv("GITHUB_ENTERPRISE_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_ENTERPRISE_VERSION", raising=False)
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("USERNAME_SELF", "testuser")

        with pytest.raises(ValueError, match="Missing required environment variables: GITHUB_TOKEN"):
            load_config_from_env()

    def test_load_config_empty_github_token(self, monkeypatch):
        """Test load_config treats empty GITHUB_TOKEN as missing."""
        monkeypatch.setenv("GITHUB_TOKEN", "")
        monkeypatch.delenv("GITHUB_ENTERPRISE_HOST", raising=False)
        monkeypatch.delenv("GITHUB_ENTERPRISE_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_ENTERPRISE_VERSION", raising=False)
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("USERNAME_SELF", "testuser")

        with pytest.raises(ValueError, match="Missing required environment variables: GITHUB_TOKEN"):
            load_config_from_env()

    def test_load_config_watched_statuses_with_spaces(self, monkeypatch):
        """Test watched_statuses parsing handles spaces correctly."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("WATCHED_STATUSES", "  Status 1  ,  Status 2  ,  Status 3  ")
        monkeypatch.setenv("USERNAME_SELF", "testuser")

        config = load_config_from_env()

        assert config.watched_statuses == ["Status 1", "Status 2", "Status 3"]

    def test_load_config_poll_interval_conversion(self, monkeypatch):
        """Test poll_interval is correctly converted to int."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("POLL_INTERVAL", "300")
        monkeypatch.setenv("USERNAME_SELF", "testuser")

        config = load_config_from_env()

        assert config.poll_interval == 300
        assert isinstance(config.poll_interval, int)

    def test_load_config_single_watched_status(self, monkeypatch):
        """Test watched_statuses with a single status."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("WATCHED_STATUSES", "OnlyOne")
        monkeypatch.setenv("USERNAME_SELF", "testuser")

        config = load_config_from_env()

        assert config.watched_statuses == ["OnlyOne"]

    def test_load_config_preserves_env_values_between_calls(self, monkeypatch):
        """Test that load_config reads fresh values from environment each time."""
        monkeypatch.setenv("GITHUB_TOKEN", "token1")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("POLL_INTERVAL", "30")
        monkeypatch.setenv("USERNAME_SELF", "testuser")

        config1 = load_config_from_env()
        assert config1.poll_interval == 30

        monkeypatch.setenv("POLL_INTERVAL", "60")
        config2 = load_config_from_env()
        assert config2.poll_interval == 60

    def test_load_config_missing_project_urls(self, monkeypatch):
        """Test load_config raises ValueError when PROJECT_URLS is missing."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("USERNAME_SELF", "testuser")
        monkeypatch.delenv("PROJECT_URLS", raising=False)

        with pytest.raises(ValueError, match="Missing required environment variables: PROJECT_URLS"):
            load_config_from_env()

    def test_load_config_missing_multiple_required_vars(self, monkeypatch):
        """Test load_config lists all missing required vars in a single error."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.delenv("PROJECT_URLS", raising=False)
        monkeypatch.delenv("USERNAME_SELF", raising=False)

        with pytest.raises(
            ValueError, match="Missing required environment variables: PROJECT_URLS, USERNAME_SELF"
        ):
            load_config_from_env()

    def test_load_config_missing_github_token_no_auth(self, monkeypatch):
        """Test load_config raises ValueError when no GitHub auth is configured."""
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_ENTERPRISE_HOST", raising=False)
        monkeypatch.delenv("GITHUB_ENTERPRISE_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_ENTERPRISE_VERSION", raising=False)
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("USERNAME_SELF", "testuser")

        with pytest.raises(
            ValueError, match="Missing required environment variables: GITHUB_TOKEN"
        ):
            load_config_from_env()

    def test_load_config_missing_all_required_vars(self, monkeypatch):
        """Test load_config lists all missing vars including GITHUB_TOKEN."""
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_ENTERPRISE_HOST", raising=False)
        monkeypatch.delenv("GITHUB_ENTERPRISE_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_ENTERPRISE_VERSION", raising=False)
        monkeypatch.delenv("PROJECT_URLS", raising=False)
        monkeypatch.delenv("USERNAME_SELF", raising=False)

        with pytest.raises(
            ValueError,
            match="Missing required environment variables: GITHUB_TOKEN, PROJECT_URLS, USERNAME_SELF",
        ):
            load_config_from_env()

    def test_load_config_project_urls_comma_separated(self, monkeypatch):
        """Test PROJECT_URLS with comma-separated URLs."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv(
            "PROJECT_URLS",
            "https://github.com/orgs/test/projects/1, https://github.com/orgs/test/projects/2",
        )
        monkeypatch.setenv("USERNAME_SELF", "testuser")

        config = load_config_from_env()

        assert config.project_urls == [
            "https://github.com/orgs/test/projects/1",
            "https://github.com/orgs/test/projects/2",
        ]

    def test_load_config_single_project_url(self, monkeypatch):
        """Test PROJECT_URLS with a single URL."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("USERNAME_SELF", "testuser")

        config = load_config_from_env()

        assert config.project_urls == ["https://github.com/orgs/test/projects/1"]

    def test_load_config_default_stage_models(self, monkeypatch):
        """Test load_config applies default stage models."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("USERNAME_SELF", "testuser")
        monkeypatch.delenv("STAGE_MODELS", raising=False)

        config = load_config_from_env()

        assert config.stage_models == {
            "Prepare": "claude-haiku-4-5-20251001",
            "Research": "claude-opus-4-5-20251101",
            "Plan": "claude-opus-4-5-20251101",
            "Implement": "claude-opus-4-5-20251101",
            "process_comments": "claude-sonnet-4-5-20250929",
        }

    def test_load_config_custom_stage_models(self, monkeypatch):
        """Test load_config parses STAGE_MODELS JSON correctly."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("USERNAME_SELF", "testuser")
        monkeypatch.setenv("STAGE_MODELS", '{"Prepare": "haiku", "Plan": "opus"}')

        config = load_config_from_env()

        assert config.stage_models == {"Prepare": "haiku", "Plan": "opus"}

    def test_load_config_invalid_stage_models_json(self, monkeypatch):
        """Test load_config raises ValueError for invalid STAGE_MODELS JSON."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("USERNAME_SELF", "testuser")
        monkeypatch.setenv("STAGE_MODELS", "not valid json")

        with pytest.raises(ValueError, match="STAGE_MODELS must be valid JSON"):
            load_config_from_env()

    def test_load_config_claude_code_enable_telemetry_default(self, monkeypatch):
        """Test claude_code_enable_telemetry defaults to False."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("USERNAME_SELF", "testuser")
        monkeypatch.delenv("CLAUDE_CODE_ENABLE_TELEMETRY", raising=False)

        config = load_config_from_env()

        assert config.claude_code_enable_telemetry is False

    def test_load_config_claude_code_enable_telemetry_enabled(self, monkeypatch):
        """Test claude_code_enable_telemetry parses '1' as True."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("USERNAME_SELF", "testuser")
        monkeypatch.setenv("CLAUDE_CODE_ENABLE_TELEMETRY", "1")

        config = load_config_from_env()

        assert config.claude_code_enable_telemetry is True

    def test_load_config_claude_code_enable_telemetry_disabled_explicit(self, monkeypatch):
        """Test claude_code_enable_telemetry parses '0' as False."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("USERNAME_SELF", "testuser")
        monkeypatch.setenv("CLAUDE_CODE_ENABLE_TELEMETRY", "0")

        config = load_config_from_env()

        assert config.claude_code_enable_telemetry is False

    # Tests for GHES_LOGS_MASK

    def test_load_config_ghes_logs_mask_default(self, monkeypatch):
        """Test ghes_logs_mask defaults to True when not specified."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("USERNAME_SELF", "testuser")
        monkeypatch.delenv("GHES_LOGS_MASK", raising=False)

        config = load_config_from_env()

        assert config.ghes_logs_mask is True

    def test_load_config_ghes_logs_mask_explicit_true(self, monkeypatch):
        """Test ghes_logs_mask parses 'true' as True."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("USERNAME_SELF", "testuser")
        monkeypatch.setenv("GHES_LOGS_MASK", "true")

        config = load_config_from_env()

        assert config.ghes_logs_mask is True

    def test_load_config_ghes_logs_mask_explicit_false(self, monkeypatch):
        """Test ghes_logs_mask parses 'false' as False."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("USERNAME_SELF", "testuser")
        monkeypatch.setenv("GHES_LOGS_MASK", "false")

        config = load_config_from_env()

        assert config.ghes_logs_mask is False

    def test_load_config_ghes_logs_mask_case_insensitive(self, monkeypatch):
        """Test ghes_logs_mask parsing is case-insensitive."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("USERNAME_SELF", "testuser")

        # Test uppercase TRUE
        monkeypatch.setenv("GHES_LOGS_MASK", "TRUE")
        config = load_config_from_env()
        assert config.ghes_logs_mask is True

        # Test mixed case False
        monkeypatch.setenv("GHES_LOGS_MASK", "False")
        config = load_config_from_env()
        assert config.ghes_logs_mask is False

        # Test mixed case True
        monkeypatch.setenv("GHES_LOGS_MASK", "True")
        config = load_config_from_env()
        assert config.ghes_logs_mask is True

    # Tests for SLACK_DM_ON_COMMENT

    def test_load_config_slack_dm_on_comment_default(self, monkeypatch):
        """Test slack_dm_on_comment defaults to True when not specified."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("USERNAME_SELF", "testuser")
        monkeypatch.delenv("SLACK_DM_ON_COMMENT", raising=False)

        config = load_config_from_env()

        assert config.slack_dm_on_comment is True

    def test_load_config_slack_dm_on_comment_enabled(self, monkeypatch):
        """Test slack_dm_on_comment parses '1' as True."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("USERNAME_SELF", "testuser")
        monkeypatch.setenv("SLACK_DM_ON_COMMENT", "1")

        config = load_config_from_env()

        assert config.slack_dm_on_comment is True

    def test_load_config_slack_dm_on_comment_disabled(self, monkeypatch):
        """Test slack_dm_on_comment parses '0' as False."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("USERNAME_SELF", "testuser")
        monkeypatch.setenv("SLACK_DM_ON_COMMENT", "0")

        config = load_config_from_env()

        assert config.slack_dm_on_comment is False

    # Tests for USERNAME_SELF

    def test_load_config_missing_username_self(self, monkeypatch):
        """Test load_config raises ValueError when USERNAME_SELF is missing."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.delenv("USERNAME_SELF", raising=False)

        with pytest.raises(ValueError, match="Missing required environment variables: USERNAME_SELF"):
            load_config_from_env()

    def test_load_config_empty_username_self(self, monkeypatch):
        """Test load_config raises ValueError when USERNAME_SELF is empty."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("USERNAME_SELF", "")

        with pytest.raises(ValueError, match="Missing required environment variables: USERNAME_SELF"):
            load_config_from_env()

    def test_load_config_username_self_whitespace_only(self, monkeypatch):
        """Test load_config raises ValueError when USERNAME_SELF contains only whitespace."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("USERNAME_SELF", "   ")

        with pytest.raises(ValueError, match="Missing required environment variables: USERNAME_SELF"):
            load_config_from_env()

    def test_load_config_username_self(self, monkeypatch):
        """Test USERNAME_SELF with a single username."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("USERNAME_SELF", "solo-user")

        config = load_config_from_env()

        assert config.username_self == "solo-user"

    def test_load_config_username_self_with_spaces(self, monkeypatch):
        """Test USERNAME_SELF parsing trims whitespace."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("USERNAME_SELF", "  user1  ")

        config = load_config_from_env()

        assert config.username_self == "user1"


@pytest.mark.unit
class TestParseConfigFile:
    """Tests for parse_config_file function."""

    def test_parse_config_file_reads_key_value_pairs(self, tmp_path):
        """Test parsing simple KEY=value pairs."""
        config_file = tmp_path / "config"
        config_file.write_text("KEY1=value1\nKEY2=value2")

        result = parse_config_file(config_file)

        assert result == {"KEY1": "value1", "KEY2": "value2"}

    def test_parse_config_file_ignores_comments(self, tmp_path):
        """Test that lines starting with # are ignored."""
        config_file = tmp_path / "config"
        config_file.write_text("# This is a comment\nKEY=value\n# Another comment")

        result = parse_config_file(config_file)

        assert result == {"KEY": "value"}

    def test_parse_config_file_ignores_empty_lines(self, tmp_path):
        """Test that empty lines are ignored."""
        config_file = tmp_path / "config"
        config_file.write_text("\nKEY1=value1\n\n\nKEY2=value2\n")

        result = parse_config_file(config_file)

        assert result == {"KEY1": "value1", "KEY2": "value2"}

    def test_parse_config_file_strips_whitespace(self, tmp_path):
        """Test that whitespace around keys/values is stripped."""
        config_file = tmp_path / "config"
        config_file.write_text("  KEY1  =  value1  \nKEY2 = value2")

        result = parse_config_file(config_file)

        assert result == {"KEY1": "value1", "KEY2": "value2"}

    def test_parse_config_file_handles_quoted_values(self, tmp_path):
        """Test that surrounding quotes are removed from values."""
        config_file = tmp_path / "config"
        config_file.write_text('KEY1="quoted value"\nKEY2=unquoted')

        result = parse_config_file(config_file)

        assert result == {"KEY1": "quoted value", "KEY2": "unquoted"}

    def test_parse_config_file_handles_single_quotes(self, tmp_path):
        """Test single-quoted values."""
        config_file = tmp_path / "config"
        config_file.write_text("KEY='single quoted'")

        result = parse_config_file(config_file)

        assert result == {"KEY": "single quoted"}

    def test_parse_config_file_handles_equals_in_value(self, tmp_path):
        """Test values containing = character."""
        config_file = tmp_path / "config"
        config_file.write_text("KEY=value=with=equals")

        result = parse_config_file(config_file)

        assert result == {"KEY": "value=with=equals"}

    def test_parse_config_file_handles_empty_value(self, tmp_path):
        """Test KEY= with empty value."""
        config_file = tmp_path / "config"
        config_file.write_text("KEY=")

        result = parse_config_file(config_file)

        assert result == {"KEY": ""}

    def test_parse_config_file_raises_on_missing_file(self, tmp_path):
        """Test FileNotFoundError for nonexistent file."""
        config_file = tmp_path / "nonexistent"

        with pytest.raises(FileNotFoundError):
            parse_config_file(config_file)


@pytest.mark.unit
class TestLoadConfigFromFile:
    """Tests for load_config_from_file function."""

    def _write_minimal_config(self, tmp_path, extra_lines=""):
        """Helper to write a minimal valid config file."""
        config_file = tmp_path / "config"
        content = f"GITHUB_TOKEN=ghp_test\nPROJECT_URLS=https://github.com/orgs/test/projects/1\nUSERNAME_SELF=testuser\n{extra_lines}"
        config_file.write_text(content)
        return config_file

    def test_load_config_from_file_parses_github_token(self, tmp_path, monkeypatch):
        """Test GITHUB_TOKEN parsing from config file."""
        config_file = self._write_minimal_config(tmp_path)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        config = load_config_from_file(config_file)

        assert config.github_token == "ghp_test"

    def test_load_config_from_file_parses_project_urls(self, tmp_path, monkeypatch):
        """Test PROJECT_URLS comma-separated parsing."""
        config_file = tmp_path / "config"
        config_file.write_text(
            "GITHUB_TOKEN=ghp_test\n"
            "PROJECT_URLS=https://github.com/orgs/test/projects/1, https://github.com/orgs/test/projects/2\n"
            "USERNAME_SELF=testuser"
        )
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        config = load_config_from_file(config_file)

        assert config.project_urls == [
            "https://github.com/orgs/test/projects/1",
            "https://github.com/orgs/test/projects/2",
        ]

    def test_load_config_from_file_raises_on_missing_project_urls(self, tmp_path):
        """Test ValueError when PROJECT_URLS missing."""
        config_file = tmp_path / "config"
        config_file.write_text("GITHUB_TOKEN=ghp_test\nUSERNAME_SELF=testuser")

        with pytest.raises(ValueError, match="Missing required configuration in .kiln/config: PROJECT_URLS"):
            load_config_from_file(config_file)

    def test_load_config_from_file_parses_username_self(self, tmp_path, monkeypatch):
        """Test USERNAME_SELF parsing."""
        config_file = tmp_path / "config"
        config_file.write_text(
            "GITHUB_TOKEN=ghp_test\n"
            "PROJECT_URLS=https://github.com/orgs/test/projects/1\n"
            "USERNAME_SELF=myuser"
        )
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        config = load_config_from_file(config_file)

        assert config.username_self == "myuser"

    def test_load_config_from_file_raises_on_missing_username_self(self, tmp_path):
        """Test ValueError when USERNAME_SELF missing."""
        config_file = tmp_path / "config"
        config_file.write_text(
            "GITHUB_TOKEN=ghp_test\nPROJECT_URLS=https://github.com/orgs/test/projects/1"
        )

        with pytest.raises(ValueError, match="Missing required configuration in .kiln/config: USERNAME_SELF"):
            load_config_from_file(config_file)

    def test_load_config_from_file_raises_on_missing_multiple_vars(self, tmp_path):
        """Test ValueError lists all missing required vars in config file."""
        config_file = tmp_path / "config"
        config_file.write_text("GITHUB_TOKEN=ghp_test")

        with pytest.raises(
            ValueError, match="Missing required configuration in .kiln/config: PROJECT_URLS, USERNAME_SELF"
        ):
            load_config_from_file(config_file)

    def test_load_config_from_file_raises_on_missing_github_token(self, tmp_path):
        """Test ValueError when no GitHub auth is configured in file."""
        config_file = tmp_path / "config"
        config_file.write_text(
            "PROJECT_URLS=https://github.com/orgs/test/projects/1\n"
            "USERNAME_SELF=testuser"
        )

        with pytest.raises(
            ValueError, match="Missing required configuration in .kiln/config: GITHUB_TOKEN"
        ):
            load_config_from_file(config_file)

    def test_load_config_from_file_raises_on_missing_all_vars(self, tmp_path):
        """Test ValueError lists all missing vars including GITHUB_TOKEN in file."""
        config_file = tmp_path / "config"
        config_file.write_text("# empty config")

        with pytest.raises(
            ValueError,
            match="Missing required configuration in .kiln/config: GITHUB_TOKEN, PROJECT_URLS, USERNAME_SELF",
        ):
            load_config_from_file(config_file)

    def test_load_config_from_file_parses_poll_interval(self, tmp_path, monkeypatch):
        """Test POLL_INTERVAL integer parsing."""
        config_file = tmp_path / "config"
        config_file.write_text(
            "GITHUB_TOKEN=ghp_test\n"
            "PROJECT_URLS=https://github.com/orgs/test/projects/1\n"
            "USERNAME_SELF=testuser\n"
            "POLL_INTERVAL=120"
        )
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        config = load_config_from_file(config_file)

        assert config.poll_interval == 120

    def test_load_config_from_file_parses_watched_statuses(self, tmp_path, monkeypatch):
        """Test WATCHED_STATUSES comma-separated parsing."""
        config_file = tmp_path / "config"
        config_file.write_text(
            "GITHUB_TOKEN=ghp_test\n"
            "PROJECT_URLS=https://github.com/orgs/test/projects/1\n"
            "USERNAME_SELF=testuser\n"
            "WATCHED_STATUSES=Todo, In Progress, Done"
        )
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        config = load_config_from_file(config_file)

        assert config.watched_statuses == ["Todo", "In Progress", "Done"]

    def test_load_config_from_file_applies_defaults(self, tmp_path, monkeypatch):
        """Test default values applied for optional fields."""
        config_file = tmp_path / "config"
        config_file.write_text(
            "GITHUB_TOKEN=ghp_test\n"
            "PROJECT_URLS=https://github.com/orgs/test/projects/1\n"
            "USERNAME_SELF=testuser"
        )
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        config = load_config_from_file(config_file)

        assert config.poll_interval == 30
        assert config.watched_statuses == ["Research", "Plan", "Implement"]
        assert config.max_concurrent_workflows == 6

    def test_load_config_from_file_parses_stage_models_json(self, tmp_path, monkeypatch):
        """Test STAGE_MODELS JSON parsing."""
        config_file = tmp_path / "config"
        config_file.write_text(
            "GITHUB_TOKEN=ghp_test\n"
            "PROJECT_URLS=https://github.com/orgs/test/projects/1\n"
            "USERNAME_SELF=testuser\n"
            'STAGE_MODELS={"Prepare": "haiku", "Plan": "sonnet"}'
        )
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        config = load_config_from_file(config_file)

        assert config.stage_models == {"Prepare": "haiku", "Plan": "sonnet"}

    def test_load_config_from_file_raises_on_invalid_stage_models_json(self, tmp_path):
        """Test ValueError for malformed STAGE_MODELS JSON."""
        config_file = tmp_path / "config"
        config_file.write_text(
            "GITHUB_TOKEN=ghp_test\n"
            "PROJECT_URLS=https://github.com/orgs/test/projects/1\n"
            "USERNAME_SELF=testuser\n"
            "STAGE_MODELS=not valid json"
        )

        with pytest.raises(ValueError, match="STAGE_MODELS must be valid JSON"):
            load_config_from_file(config_file)

    def test_load_config_from_file_sets_env_vars(self, tmp_path, monkeypatch):
        """Test that tokens are set in environment for subprocess access."""
        import os

        config_file = tmp_path / "config"
        config_file.write_text(
            "GITHUB_TOKEN=ghp_env_test\n"
            "PROJECT_URLS=https://github.com/orgs/test/projects/1\n"
            "USERNAME_SELF=testuser"
        )
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        load_config_from_file(config_file)

        assert os.environ.get("GITHUB_TOKEN") == "ghp_env_test"

    def test_load_config_from_file_parses_telemetry_settings(self, tmp_path, monkeypatch):
        """Test OTEL and telemetry settings parsing."""
        config_file = tmp_path / "config"
        config_file.write_text(
            "GITHUB_TOKEN=ghp_test\n"
            "PROJECT_URLS=https://github.com/orgs/test/projects/1\n"
            "USERNAME_SELF=testuser\n"
            "OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317\n"
            "OTEL_SERVICE_NAME=kiln-test\n"
            "CLAUDE_CODE_ENABLE_TELEMETRY=1"
        )
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        config = load_config_from_file(config_file)

        assert config.otel_endpoint == "http://localhost:4317"
        assert config.otel_service_name == "kiln-test"
        assert config.claude_code_enable_telemetry is True

    def test_load_config_from_file_max_concurrent_workflows(self, tmp_path, monkeypatch):
        """Test MAX_CONCURRENT_WORKFLOWS parsing."""
        config_file = tmp_path / "config"
        config_file.write_text(
            "GITHUB_TOKEN=ghp_test\n"
            "PROJECT_URLS=https://github.com/orgs/test/projects/1\n"
            "USERNAME_SELF=testuser\n"
            "MAX_CONCURRENT_WORKFLOWS=5"
        )
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        config = load_config_from_file(config_file)

        assert config.max_concurrent_workflows == 5

    def test_load_config_from_file_ghes_logs_mask_default(self, tmp_path, monkeypatch):
        """Test ghes_logs_mask defaults to True when not specified in file."""
        config_file = self._write_minimal_config(tmp_path)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        config = load_config_from_file(config_file)

        assert config.ghes_logs_mask is True

    def test_load_config_from_file_ghes_logs_mask_true(self, tmp_path, monkeypatch):
        """Test GHES_LOGS_MASK=true parsing from config file."""
        config_file = self._write_minimal_config(tmp_path, "GHES_LOGS_MASK=true")
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        config = load_config_from_file(config_file)

        assert config.ghes_logs_mask is True

    def test_load_config_from_file_ghes_logs_mask_false(self, tmp_path, monkeypatch):
        """Test GHES_LOGS_MASK=false parsing from config file."""
        config_file = self._write_minimal_config(tmp_path, "GHES_LOGS_MASK=false")
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        config = load_config_from_file(config_file)

        assert config.ghes_logs_mask is False

    def test_load_config_from_file_ghes_logs_mask_case_insensitive(self, tmp_path, monkeypatch):
        """Test GHES_LOGS_MASK parsing is case-insensitive in file."""
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        # Test uppercase TRUE
        config_file = self._write_minimal_config(tmp_path, "GHES_LOGS_MASK=TRUE")
        config = load_config_from_file(config_file)
        assert config.ghes_logs_mask is True

        # Test mixed case False
        config_file = self._write_minimal_config(tmp_path, "GHES_LOGS_MASK=False")
        config = load_config_from_file(config_file)
        assert config.ghes_logs_mask is False

    def test_load_config_from_file_slack_dm_on_comment_default(self, tmp_path, monkeypatch):
        """Test slack_dm_on_comment defaults to True when not specified in file."""
        config_file = self._write_minimal_config(tmp_path)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        config = load_config_from_file(config_file)

        assert config.slack_dm_on_comment is True

    def test_load_config_from_file_slack_dm_on_comment_enabled(self, tmp_path, monkeypatch):
        """Test SLACK_DM_ON_COMMENT=1 parsing from config file."""
        config_file = self._write_minimal_config(tmp_path, "SLACK_DM_ON_COMMENT=1")
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        config = load_config_from_file(config_file)

        assert config.slack_dm_on_comment is True

    def test_load_config_from_file_slack_dm_on_comment_disabled(self, tmp_path, monkeypatch):
        """Test SLACK_DM_ON_COMMENT=0 parsing from config file."""
        config_file = self._write_minimal_config(tmp_path, "SLACK_DM_ON_COMMENT=0")
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        config = load_config_from_file(config_file)

        assert config.slack_dm_on_comment is False


@pytest.mark.unit
class TestLoadConfigEntryPoint:
    """Tests for load_config entry point."""

    def test_load_config_uses_file_when_exists(self, tmp_path, monkeypatch):
        """Test load_config prefers file when .kiln/config exists."""
        # Create .kiln/config in a temp directory
        kiln_dir = tmp_path / ".kiln"
        kiln_dir.mkdir()
        config_file = kiln_dir / "config"
        config_file.write_text(
            "GITHUB_TOKEN=ghp_from_file\n"
            "PROJECT_URLS=https://github.com/orgs/test/projects/1\n"
            "USERNAME_SELF=testuser"
        )

        # Set env vars (should be ignored when file exists)
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_from_env")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/other/projects/2")
        monkeypatch.setenv("USERNAME_SELF", "envuser")

        # Change cwd to temp directory
        monkeypatch.chdir(tmp_path)

        config = load_config()

        assert config.github_token == "ghp_from_file"
        assert config.project_urls == ["https://github.com/orgs/test/projects/1"]
        assert config.username_self == "testuser"

    def test_load_config_falls_back_to_env(self, tmp_path, monkeypatch):
        """Test load_config uses env vars when no config file."""
        # Ensure no .kiln/config exists
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_from_env")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("USERNAME_SELF", "envuser")

        config = load_config()

        assert config.github_token == "ghp_from_env"
        assert config.project_urls == ["https://github.com/orgs/test/projects/1"]
        assert config.username_self == "envuser"

    def test_load_config_file_path_is_cwd_relative(self, tmp_path, monkeypatch):
        """Test config file path is .kiln/config relative to cwd."""
        # Create .kiln/config in temp directory
        kiln_dir = tmp_path / ".kiln"
        kiln_dir.mkdir()
        config_file = kiln_dir / "config"
        config_file.write_text(
            "GITHUB_TOKEN=ghp_cwd_test\n"
            "PROJECT_URLS=https://github.com/orgs/test/projects/1\n"
            "USERNAME_SELF=testuser"
        )

        # Change to temp directory
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        config = load_config()

        assert config.github_token == "ghp_cwd_test"


@pytest.mark.unit
class TestGHESConfiguration:
    """Tests for GitHub Enterprise Server configuration."""

    def _write_config(self, tmp_path, content):
        """Helper to write a config file."""
        config_file = tmp_path / "config"
        config_file.write_text(content)
        return config_file

    def test_ghes_config_parsed_from_file(self, tmp_path, monkeypatch):
        """Test GHES host and token are parsed from config file."""
        config_file = self._write_config(
            tmp_path,
            "GITHUB_ENTERPRISE_HOST=github.mycompany.com\n"
            "GITHUB_ENTERPRISE_TOKEN=ghp_enterprise_test\n"
            "GITHUB_ENTERPRISE_VERSION=3.14\n"
            "PROJECT_URLS=https://github.mycompany.com/orgs/test/projects/1\n"
            "USERNAME_SELF=testuser",
        )
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        config = load_config_from_file(config_file)

        assert config.github_enterprise_host == "github.mycompany.com"
        assert config.github_enterprise_token == "ghp_enterprise_test"
        assert config.github_enterprise_version == "3.14"
        assert config.github_token is None

    def test_ghes_config_parsed_from_env(self, monkeypatch):
        """Test GHES host and token are parsed from environment."""
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.setenv("GITHUB_ENTERPRISE_HOST", "github.enterprise.io")
        monkeypatch.setenv("GITHUB_ENTERPRISE_TOKEN", "ghp_ent_token")
        monkeypatch.setenv("GITHUB_ENTERPRISE_VERSION", "3.14")
        monkeypatch.setenv("PROJECT_URLS", "https://github.enterprise.io/orgs/test/projects/1")
        monkeypatch.setenv("USERNAME_SELF", "testuser")

        config = load_config_from_env()

        assert config.github_enterprise_host == "github.enterprise.io"
        assert config.github_enterprise_token == "ghp_ent_token"
        assert config.github_enterprise_version == "3.14"
        assert config.github_token is None

    def test_mutual_exclusivity_raises_error_file(self, tmp_path):
        """Test error when both GITHUB_TOKEN and GITHUB_ENTERPRISE_TOKEN set in file."""
        config_file = self._write_config(
            tmp_path,
            "GITHUB_TOKEN=ghp_regular\n"
            "GITHUB_ENTERPRISE_HOST=github.mycompany.com\n"
            "GITHUB_ENTERPRISE_TOKEN=ghp_enterprise\n"
            "PROJECT_URLS=https://github.com/orgs/test/projects/1\n"
            "USERNAME_SELF=testuser",
        )

        with pytest.raises(
            ValueError,
            match="Cannot configure both GITHUB_TOKEN and GITHUB_ENTERPRISE_TOKEN",
        ):
            load_config_from_file(config_file)

    def test_mutual_exclusivity_raises_error_env(self, monkeypatch):
        """Test error when both GITHUB_TOKEN and GITHUB_ENTERPRISE_TOKEN set in env."""
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_regular")
        monkeypatch.setenv("GITHUB_ENTERPRISE_HOST", "github.mycompany.com")
        monkeypatch.setenv("GITHUB_ENTERPRISE_TOKEN", "ghp_enterprise")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("USERNAME_SELF", "testuser")

        with pytest.raises(
            ValueError,
            match="Cannot configure both GITHUB_TOKEN and GITHUB_ENTERPRISE_TOKEN",
        ):
            load_config_from_env()

    def test_ghes_token_without_host_raises_error_file(self, tmp_path):
        """Test error when GITHUB_ENTERPRISE_TOKEN set without GITHUB_ENTERPRISE_HOST in file."""
        config_file = self._write_config(
            tmp_path,
            "GITHUB_ENTERPRISE_TOKEN=ghp_enterprise\n"
            "PROJECT_URLS=https://github.com/orgs/test/projects/1\n"
            "USERNAME_SELF=testuser",
        )

        # Version is now optional (auto-detected), only host is required
        with pytest.raises(
            ValueError,
            match="Missing required configuration in .kiln/config: GITHUB_ENTERPRISE_HOST",
        ):
            load_config_from_file(config_file)

    def test_ghes_token_without_host_raises_error_env(self, monkeypatch):
        """Test error when GITHUB_ENTERPRISE_TOKEN set without GITHUB_ENTERPRISE_HOST in env."""
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_ENTERPRISE_HOST", raising=False)
        monkeypatch.setenv("GITHUB_ENTERPRISE_TOKEN", "ghp_enterprise")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("USERNAME_SELF", "testuser")

        # Version is now optional (auto-detected), only host is required
        with pytest.raises(
            ValueError,
            match="Missing required environment variables: GITHUB_ENTERPRISE_HOST",
        ):
            load_config_from_env()

    def test_project_urls_host_mismatch_raises_error_ghes_file(self, tmp_path):
        """Test error when PROJECT_URLS hostname doesn't match GHES config in file."""
        config_file = self._write_config(
            tmp_path,
            "GITHUB_ENTERPRISE_HOST=github.mycompany.com\n"
            "GITHUB_ENTERPRISE_TOKEN=ghp_enterprise\n"
            "GITHUB_ENTERPRISE_VERSION=3.14\n"
            "PROJECT_URLS=https://github.com/orgs/test/projects/1\n"
            "USERNAME_SELF=testuser",
        )

        with pytest.raises(
            ValueError,
            match="PROJECT_URLS contains 'github.com' but configured for 'github.mycompany.com'",
        ):
            load_config_from_file(config_file)

    def test_project_urls_host_mismatch_raises_error_ghes_env(self, monkeypatch):
        """Test error when PROJECT_URLS hostname doesn't match GHES config in env."""
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.setenv("GITHUB_ENTERPRISE_HOST", "github.mycompany.com")
        monkeypatch.setenv("GITHUB_ENTERPRISE_TOKEN", "ghp_enterprise")
        monkeypatch.setenv("GITHUB_ENTERPRISE_VERSION", "3.14")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("USERNAME_SELF", "testuser")

        with pytest.raises(
            ValueError,
            match="PROJECT_URLS contains 'github.com' but configured for 'github.mycompany.com'",
        ):
            load_config_from_env()

    def test_project_urls_host_mismatch_raises_error_github_com(self, tmp_path, monkeypatch):
        """Test error when PROJECT_URLS uses GHES hostname but configured for github.com."""
        config_file = self._write_config(
            tmp_path,
            "GITHUB_TOKEN=ghp_regular\n"
            "PROJECT_URLS=https://github.mycompany.com/orgs/test/projects/1\n"
            "USERNAME_SELF=testuser",
        )
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        with pytest.raises(
            ValueError,
            match="PROJECT_URLS contains 'github.mycompany.com' but configured for 'github.com'",
        ):
            load_config_from_file(config_file)

    def test_ghes_only_config_works_file(self, tmp_path, monkeypatch):
        """Test GHES-only configuration without github.com token in file."""
        config_file = self._write_config(
            tmp_path,
            "GITHUB_ENTERPRISE_HOST=github.enterprise.io\n"
            "GITHUB_ENTERPRISE_TOKEN=ghp_ent_only\n"
            "GITHUB_ENTERPRISE_VERSION=3.14\n"
            "PROJECT_URLS=https://github.enterprise.io/orgs/myorg/projects/5\n"
            "USERNAME_SELF=enterpriseuser",
        )
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        config = load_config_from_file(config_file)

        assert config.github_token is None
        assert config.github_enterprise_host == "github.enterprise.io"
        assert config.github_enterprise_token == "ghp_ent_only"
        assert config.github_enterprise_version == "3.14"
        assert config.project_urls == ["https://github.enterprise.io/orgs/myorg/projects/5"]
        assert config.username_self == "enterpriseuser"

    def test_ghes_only_config_works_env(self, monkeypatch):
        """Test GHES-only configuration without github.com token in env."""
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.setenv("GITHUB_ENTERPRISE_HOST", "git.corp.com")
        monkeypatch.setenv("GITHUB_ENTERPRISE_TOKEN", "ghp_corp_token")
        monkeypatch.setenv("GITHUB_ENTERPRISE_VERSION", "3.14")
        monkeypatch.setenv("PROJECT_URLS", "https://git.corp.com/orgs/team/projects/3")
        monkeypatch.setenv("USERNAME_SELF", "corpuser")

        config = load_config_from_env()

        assert config.github_token is None
        assert config.github_enterprise_host == "git.corp.com"
        assert config.github_enterprise_token == "ghp_corp_token"
        assert config.github_enterprise_version == "3.14"
        assert config.project_urls == ["https://git.corp.com/orgs/team/projects/3"]

    def test_empty_ghes_values_normalized_to_none_file(self, tmp_path, monkeypatch):
        """Test empty GHES values become None in file config."""
        config_file = self._write_config(
            tmp_path,
            "GITHUB_TOKEN=ghp_test\n"
            "GITHUB_ENTERPRISE_HOST=\n"
            "GITHUB_ENTERPRISE_TOKEN=\n"
            "PROJECT_URLS=https://github.com/orgs/test/projects/1\n"
            "USERNAME_SELF=testuser",
        )
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        config = load_config_from_file(config_file)

        assert config.github_enterprise_host is None
        assert config.github_enterprise_token is None
        assert config.github_token == "ghp_test"

    def test_empty_ghes_values_normalized_to_none_env(self, monkeypatch):
        """Test empty GHES values become None in env config."""
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
        monkeypatch.setenv("GITHUB_ENTERPRISE_HOST", "")
        monkeypatch.setenv("GITHUB_ENTERPRISE_TOKEN", "")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("USERNAME_SELF", "testuser")

        config = load_config_from_env()

        assert config.github_enterprise_host is None
        assert config.github_enterprise_token is None
        assert config.github_token == "ghp_test"

    def test_ghes_token_sets_env_var(self, tmp_path, monkeypatch):
        """Test GHES token is set in environment for subprocess access."""
        import os

        config_file = self._write_config(
            tmp_path,
            "GITHUB_ENTERPRISE_HOST=github.mycompany.com\n"
            "GITHUB_ENTERPRISE_TOKEN=ghp_ent_env_test\n"
            "GITHUB_ENTERPRISE_VERSION=3.14\n"
            "PROJECT_URLS=https://github.mycompany.com/orgs/test/projects/1\n"
            "USERNAME_SELF=testuser",
        )
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        load_config_from_file(config_file)

        # GHES token should be set as GITHUB_TOKEN for gh CLI subprocess use
        assert os.environ.get("GITHUB_TOKEN") == "ghp_ent_env_test"

    def test_project_urls_multiple_matching_ghes_hosts(self, tmp_path, monkeypatch):
        """Test multiple PROJECT_URLS all matching GHES host succeeds."""
        config_file = self._write_config(
            tmp_path,
            "GITHUB_ENTERPRISE_HOST=github.mycompany.com\n"
            "GITHUB_ENTERPRISE_TOKEN=ghp_enterprise\n"
            "GITHUB_ENTERPRISE_VERSION=3.14\n"
            "PROJECT_URLS=https://github.mycompany.com/orgs/team1/projects/1,"
            "https://github.mycompany.com/orgs/team2/projects/2\n"
            "USERNAME_SELF=testuser",
        )
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        config = load_config_from_file(config_file)

        assert config.project_urls == [
            "https://github.mycompany.com/orgs/team1/projects/1",
            "https://github.mycompany.com/orgs/team2/projects/2",
        ]

    def test_project_urls_one_mismatched_host_raises_error(self, tmp_path, monkeypatch):
        """Test error when one PROJECT_URL doesn't match configured host."""
        config_file = self._write_config(
            tmp_path,
            "GITHUB_ENTERPRISE_HOST=github.mycompany.com\n"
            "GITHUB_ENTERPRISE_TOKEN=ghp_enterprise\n"
            "GITHUB_ENTERPRISE_VERSION=3.14\n"
            "PROJECT_URLS=https://github.mycompany.com/orgs/team1/projects/1,"
            "https://github.com/orgs/team2/projects/2\n"
            "USERNAME_SELF=testuser",
        )
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        with pytest.raises(
            ValueError,
            match="PROJECT_URLS contains 'github.com' but configured for 'github.mycompany.com'",
        ):
            load_config_from_file(config_file)

    def test_ghes_host_only_without_token_ignored(self, tmp_path, monkeypatch):
        """Test GHES host without token doesn't affect github.com config."""
        config_file = self._write_config(
            tmp_path,
            "GITHUB_TOKEN=ghp_regular\n"
            "GITHUB_ENTERPRISE_HOST=github.mycompany.com\n"
            "PROJECT_URLS=https://github.com/orgs/test/projects/1\n"
            "USERNAME_SELF=testuser",
        )
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        config = load_config_from_file(config_file)

        # Should work as github.com config since GHES token is not set
        assert config.github_token == "ghp_regular"
        assert config.github_enterprise_host == "github.mycompany.com"
        assert config.github_enterprise_token is None

    def test_ghes_version_318_parsed_from_file(self, tmp_path, monkeypatch):
        """Test GHES version 3.18 is parsed from config file."""
        config_file = self._write_config(
            tmp_path,
            "GITHUB_ENTERPRISE_HOST=github.mycompany.com\n"
            "GITHUB_ENTERPRISE_TOKEN=ghp_enterprise\n"
            "GITHUB_ENTERPRISE_VERSION=3.18\n"
            "PROJECT_URLS=https://github.mycompany.com/orgs/test/projects/1\n"
            "USERNAME_SELF=testuser",
        )
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        config = load_config_from_file(config_file)

        assert config.github_enterprise_version == "3.18"
        assert config.github_enterprise_host == "github.mycompany.com"
        assert config.github_enterprise_token == "ghp_enterprise"

    def test_ghes_version_318_parsed_from_env(self, monkeypatch):
        """Test GHES version 3.18 is parsed from environment."""
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.setenv("GITHUB_ENTERPRISE_HOST", "github.mycompany.com")
        monkeypatch.setenv("GITHUB_ENTERPRISE_TOKEN", "ghp_enterprise")
        monkeypatch.setenv("GITHUB_ENTERPRISE_VERSION", "3.18")
        monkeypatch.setenv("PROJECT_URLS", "https://github.mycompany.com/orgs/test/projects/1")
        monkeypatch.setenv("USERNAME_SELF", "testuser")

        config = load_config_from_env()

        assert config.github_enterprise_version == "3.18"
        assert config.github_enterprise_host == "github.mycompany.com"
        assert config.github_enterprise_token == "ghp_enterprise"


@pytest.mark.unit
class TestTeamUsernamesConfiguration:
    """Tests for team usernames configuration (USERNAMES_TEAM)."""

    def test_team_usernames_empty_by_default_env(self, monkeypatch):
        """Test team_usernames defaults to empty list when USERNAMES_TEAM not set."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("USERNAME_SELF", "testuser")
        monkeypatch.delenv("USERNAMES_TEAM", raising=False)

        config = load_config_from_env()

        assert config.team_usernames == []

    def test_team_usernames_single_member_env(self, monkeypatch):
        """Test USERNAMES_TEAM parsing with single team member."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("USERNAME_SELF", "testuser")
        monkeypatch.setenv("USERNAMES_TEAM", "teammate1")

        config = load_config_from_env()

        assert config.team_usernames == ["teammate1"]

    def test_team_usernames_multiple_members_env(self, monkeypatch):
        """Test USERNAMES_TEAM parsing with multiple team members."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("USERNAME_SELF", "testuser")
        monkeypatch.setenv("USERNAMES_TEAM", "alice,bob,charlie")

        config = load_config_from_env()

        assert config.team_usernames == ["alice", "bob", "charlie"]

    def test_team_usernames_strips_whitespace_env(self, monkeypatch):
        """Test USERNAMES_TEAM parsing strips whitespace around usernames."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("USERNAME_SELF", "testuser")
        monkeypatch.setenv("USERNAMES_TEAM", "  alice  ,  bob  ,  charlie  ")

        config = load_config_from_env()

        assert config.team_usernames == ["alice", "bob", "charlie"]

    def test_team_usernames_ignores_empty_entries_env(self, monkeypatch):
        """Test USERNAMES_TEAM parsing ignores empty entries (e.g., from trailing comma)."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("USERNAME_SELF", "testuser")
        monkeypatch.setenv("USERNAMES_TEAM", "alice,,bob,")

        config = load_config_from_env()

        assert config.team_usernames == ["alice", "bob"]

    def _write_config(self, tmp_path, content):
        """Helper to write a config file."""
        config_file = tmp_path / "config"
        config_file.write_text(content)
        return config_file

    def test_team_usernames_from_file(self, tmp_path, monkeypatch):
        """Test USERNAMES_TEAM parsing from config file."""
        config_file = self._write_config(
            tmp_path,
            "GITHUB_TOKEN=ghp_test\n"
            "PROJECT_URLS=https://github.com/orgs/test/projects/1\n"
            "USERNAME_SELF=testuser\n"
            "USERNAMES_TEAM=teammate1,teammate2,teammate3",
        )
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        config = load_config_from_file(config_file)

        assert config.team_usernames == ["teammate1", "teammate2", "teammate3"]

    def test_team_usernames_empty_by_default_file(self, tmp_path, monkeypatch):
        """Test team_usernames defaults to empty list when USERNAMES_TEAM not in file."""
        config_file = self._write_config(
            tmp_path,
            "GITHUB_TOKEN=ghp_test\n"
            "PROJECT_URLS=https://github.com/orgs/test/projects/1\n"
            "USERNAME_SELF=testuser",
        )
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        config = load_config_from_file(config_file)

        assert config.team_usernames == []

    def test_team_usernames_strips_whitespace_file(self, tmp_path, monkeypatch):
        """Test USERNAMES_TEAM parsing strips whitespace from file."""
        config_file = self._write_config(
            tmp_path,
            "GITHUB_TOKEN=ghp_test\n"
            "PROJECT_URLS=https://github.com/orgs/test/projects/1\n"
            "USERNAME_SELF=testuser\n"
            "USERNAMES_TEAM=  alice  ,  bob  ",
        )
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        config = load_config_from_file(config_file)

        assert config.team_usernames == ["alice", "bob"]


@pytest.mark.unit
class TestBackwardIncompatibility:
    """Tests ensuring ALLOWED_USERNAME is no longer supported (clean break)."""

    def test_allowed_username_not_accepted_env(self, monkeypatch):
        """Test that ALLOWED_USERNAME alone does not configure the username.

        The config module no longer supports ALLOWED_USERNAME. Only USERNAME_SELF
        is accepted. Using ALLOWED_USERNAME should result in a missing USERNAME_SELF error.
        """
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("ALLOWED_USERNAME", "olduser")  # Old config option
        monkeypatch.delenv("USERNAME_SELF", raising=False)

        with pytest.raises(ValueError, match="Missing required environment variables: USERNAME_SELF"):
            load_config_from_env()

    def test_allowed_username_not_accepted_file(self, tmp_path, monkeypatch):
        """Test that ALLOWED_USERNAME in config file does not configure the username.

        The config module no longer supports ALLOWED_USERNAME. Only USERNAME_SELF
        is accepted. Using ALLOWED_USERNAME should result in a missing USERNAME_SELF error.
        """
        config_file = tmp_path / "config"
        config_file.write_text(
            "GITHUB_TOKEN=ghp_test\n"
            "PROJECT_URLS=https://github.com/orgs/test/projects/1\n"
            "ALLOWED_USERNAME=olduser"  # Old config option
        )
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        with pytest.raises(ValueError, match="Missing required configuration in .kiln/config: USERNAME_SELF"):
            load_config_from_file(config_file)

    def test_allowed_username_ignored_when_username_self_present(self, monkeypatch):
        """Test that ALLOWED_USERNAME is ignored when USERNAME_SELF is also set.

        Even if ALLOWED_USERNAME is present, it has no effect - only USERNAME_SELF
        is used for the username configuration.
        """
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("USERNAME_SELF", "newuser")
        monkeypatch.setenv("ALLOWED_USERNAME", "olduser")  # Should be ignored

        config = load_config_from_env()

        assert config.username_self == "newuser"
        assert not hasattr(config, "allowed_username")


@pytest.mark.unit
class TestAzureOAuthConfiguration:
    """Tests for Azure OAuth configuration fields."""

    def _write_config(self, tmp_path, content):
        """Helper to write a config file."""
        config_file = tmp_path / "config"
        config_file.write_text(content)
        return config_file

    def test_azure_oauth_defaults_to_none_env(self, monkeypatch):
        """Test Azure OAuth fields default to None when not set."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("USERNAME_SELF", "testuser")
        monkeypatch.delenv("AZURE_TENANT_ID", raising=False)
        monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)
        monkeypatch.delenv("AZURE_USERNAME", raising=False)
        monkeypatch.delenv("AZURE_PASSWORD", raising=False)
        monkeypatch.delenv("AZURE_SCOPE", raising=False)

        config = load_config_from_env()

        assert config.azure_tenant_id is None
        assert config.azure_client_id is None
        assert config.azure_username is None
        assert config.azure_password is None
        assert config.azure_scope is None

    def test_azure_oauth_all_fields_set_env(self, monkeypatch):
        """Test Azure OAuth fields are parsed correctly when all set."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("USERNAME_SELF", "testuser")
        monkeypatch.setenv("AZURE_TENANT_ID", "tenant-123")
        monkeypatch.setenv("AZURE_CLIENT_ID", "client-456")
        monkeypatch.setenv("AZURE_USERNAME", "service@example.com")
        monkeypatch.setenv("AZURE_PASSWORD", "secret-password")
        monkeypatch.setenv("AZURE_SCOPE", "https://api.example.com/.default")

        config = load_config_from_env()

        assert config.azure_tenant_id == "tenant-123"
        assert config.azure_client_id == "client-456"
        assert config.azure_username == "service@example.com"
        assert config.azure_password == "secret-password"
        assert config.azure_scope == "https://api.example.com/.default"

    def test_azure_oauth_scope_optional_env(self, monkeypatch):
        """Test Azure OAuth works when scope is not set (optional)."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("USERNAME_SELF", "testuser")
        monkeypatch.setenv("AZURE_TENANT_ID", "tenant-123")
        monkeypatch.setenv("AZURE_CLIENT_ID", "client-456")
        monkeypatch.setenv("AZURE_USERNAME", "service@example.com")
        monkeypatch.setenv("AZURE_PASSWORD", "secret-password")
        monkeypatch.delenv("AZURE_SCOPE", raising=False)

        config = load_config_from_env()

        assert config.azure_tenant_id == "tenant-123"
        assert config.azure_client_id == "client-456"
        assert config.azure_username == "service@example.com"
        assert config.azure_password == "secret-password"
        assert config.azure_scope is None

    def test_azure_oauth_partial_config_raises_error_env(self, monkeypatch):
        """Test partial Azure OAuth config raises validation error."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("USERNAME_SELF", "testuser")
        monkeypatch.setenv("AZURE_TENANT_ID", "tenant-123")
        monkeypatch.setenv("AZURE_CLIENT_ID", "client-456")
        # Missing AZURE_USERNAME and AZURE_PASSWORD
        monkeypatch.delenv("AZURE_USERNAME", raising=False)
        monkeypatch.delenv("AZURE_PASSWORD", raising=False)

        with pytest.raises(
            ValueError,
            match="Azure OAuth configuration is incomplete.*Missing: AZURE_USERNAME, AZURE_PASSWORD",
        ):
            load_config_from_env()

    def test_azure_oauth_missing_password_only_env(self, monkeypatch):
        """Test missing password only raises validation error with correct message."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("USERNAME_SELF", "testuser")
        monkeypatch.setenv("AZURE_TENANT_ID", "tenant-123")
        monkeypatch.setenv("AZURE_CLIENT_ID", "client-456")
        monkeypatch.setenv("AZURE_USERNAME", "service@example.com")
        monkeypatch.delenv("AZURE_PASSWORD", raising=False)

        with pytest.raises(
            ValueError,
            match="Azure OAuth configuration is incomplete.*Missing: AZURE_PASSWORD",
        ):
            load_config_from_env()

    def test_azure_oauth_empty_values_normalized_to_none_env(self, monkeypatch):
        """Test empty Azure OAuth values become None."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("USERNAME_SELF", "testuser")
        monkeypatch.setenv("AZURE_TENANT_ID", "")
        monkeypatch.setenv("AZURE_CLIENT_ID", "")
        monkeypatch.setenv("AZURE_USERNAME", "")
        monkeypatch.setenv("AZURE_PASSWORD", "")
        monkeypatch.setenv("AZURE_SCOPE", "")

        config = load_config_from_env()

        assert config.azure_tenant_id is None
        assert config.azure_client_id is None
        assert config.azure_username is None
        assert config.azure_password is None
        assert config.azure_scope is None

    def test_azure_oauth_defaults_to_none_file(self, tmp_path, monkeypatch):
        """Test Azure OAuth fields default to None when not in file."""
        config_file = self._write_config(
            tmp_path,
            "GITHUB_TOKEN=ghp_test\n"
            "PROJECT_URLS=https://github.com/orgs/test/projects/1\n"
            "USERNAME_SELF=testuser",
        )
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        config = load_config_from_file(config_file)

        assert config.azure_tenant_id is None
        assert config.azure_client_id is None
        assert config.azure_username is None
        assert config.azure_password is None
        assert config.azure_scope is None

    def test_azure_oauth_all_fields_set_file(self, tmp_path, monkeypatch):
        """Test Azure OAuth fields are parsed correctly from file."""
        config_file = self._write_config(
            tmp_path,
            "GITHUB_TOKEN=ghp_test\n"
            "PROJECT_URLS=https://github.com/orgs/test/projects/1\n"
            "USERNAME_SELF=testuser\n"
            "AZURE_TENANT_ID=tenant-123\n"
            "AZURE_CLIENT_ID=client-456\n"
            "AZURE_USERNAME=service@example.com\n"
            "AZURE_PASSWORD=secret-password\n"
            "AZURE_SCOPE=https://api.example.com/.default",
        )
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        config = load_config_from_file(config_file)

        assert config.azure_tenant_id == "tenant-123"
        assert config.azure_client_id == "client-456"
        assert config.azure_username == "service@example.com"
        assert config.azure_password == "secret-password"
        assert config.azure_scope == "https://api.example.com/.default"

    def test_azure_oauth_scope_optional_file(self, tmp_path, monkeypatch):
        """Test Azure OAuth works when scope is not set in file."""
        config_file = self._write_config(
            tmp_path,
            "GITHUB_TOKEN=ghp_test\n"
            "PROJECT_URLS=https://github.com/orgs/test/projects/1\n"
            "USERNAME_SELF=testuser\n"
            "AZURE_TENANT_ID=tenant-123\n"
            "AZURE_CLIENT_ID=client-456\n"
            "AZURE_USERNAME=service@example.com\n"
            "AZURE_PASSWORD=secret-password",
        )
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        config = load_config_from_file(config_file)

        assert config.azure_tenant_id == "tenant-123"
        assert config.azure_client_id == "client-456"
        assert config.azure_username == "service@example.com"
        assert config.azure_password == "secret-password"
        assert config.azure_scope is None

    def test_azure_oauth_partial_config_raises_error_file(self, tmp_path, monkeypatch):
        """Test partial Azure OAuth config in file raises validation error."""
        config_file = self._write_config(
            tmp_path,
            "GITHUB_TOKEN=ghp_test\n"
            "PROJECT_URLS=https://github.com/orgs/test/projects/1\n"
            "USERNAME_SELF=testuser\n"
            "AZURE_TENANT_ID=tenant-123\n"
            "AZURE_CLIENT_ID=client-456",
            # Missing AZURE_USERNAME and AZURE_PASSWORD
        )
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        with pytest.raises(
            ValueError,
            match="Azure OAuth configuration is incomplete.*Missing: AZURE_USERNAME, AZURE_PASSWORD",
        ):
            load_config_from_file(config_file)

    def test_azure_oauth_empty_values_normalized_to_none_file(self, tmp_path, monkeypatch):
        """Test empty Azure OAuth values in file become None."""
        config_file = self._write_config(
            tmp_path,
            "GITHUB_TOKEN=ghp_test\n"
            "PROJECT_URLS=https://github.com/orgs/test/projects/1\n"
            "USERNAME_SELF=testuser\n"
            "AZURE_TENANT_ID=\n"
            "AZURE_CLIENT_ID=\n"
            "AZURE_USERNAME=\n"
            "AZURE_PASSWORD=\n"
            "AZURE_SCOPE=",
        )
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        config = load_config_from_file(config_file)

        assert config.azure_tenant_id is None
        assert config.azure_client_id is None
        assert config.azure_username is None
        assert config.azure_password is None
        assert config.azure_scope is None

    def test_azure_oauth_quoted_password_file(self, tmp_path, monkeypatch):
        """Test Azure OAuth password with special characters in quotes."""
        config_file = self._write_config(
            tmp_path,
            "GITHUB_TOKEN=ghp_test\n"
            "PROJECT_URLS=https://github.com/orgs/test/projects/1\n"
            "USERNAME_SELF=testuser\n"
            "AZURE_TENANT_ID=tenant-123\n"
            "AZURE_CLIENT_ID=client-456\n"
            "AZURE_USERNAME=service@example.com\n"
            'AZURE_PASSWORD="pass=word!@#$%"',
        )
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        config = load_config_from_file(config_file)

        assert config.azure_password == "pass=word!@#$%"


@pytest.mark.unit
class TestDetermineWorkspaceDir:
    """Tests for determine_workspace_dir() auto-detection logic."""

    def test_fresh_install_uses_worktrees(self, tmp_path, monkeypatch):
        """Test that fresh install (no existing directories) defaults to worktrees."""
        monkeypatch.chdir(tmp_path)

        assert determine_workspace_dir() == "worktrees"

    def test_existing_workspaces_with_content_uses_workspaces(self, tmp_path, monkeypatch):
        """Test that existing workspaces/ with content is preserved."""
        monkeypatch.chdir(tmp_path)
        workspaces = tmp_path / "workspaces"
        workspaces.mkdir()
        (workspaces / "test-worktree").mkdir()

        assert determine_workspace_dir() == "workspaces"

    def test_empty_workspaces_uses_worktrees(self, tmp_path, monkeypatch):
        """Test that empty workspaces/ directory is ignored."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "workspaces").mkdir()

        assert determine_workspace_dir() == "worktrees"

    def test_workspaces_with_only_gitkeep_uses_worktrees(self, tmp_path, monkeypatch):
        """Test that workspaces/ with only .gitkeep is ignored."""
        monkeypatch.chdir(tmp_path)
        workspaces = tmp_path / "workspaces"
        workspaces.mkdir()
        (workspaces / ".gitkeep").touch()

        assert determine_workspace_dir() == "worktrees"
