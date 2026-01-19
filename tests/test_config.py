"""Unit tests for the config module."""

import pytest

from src.config import (
    Config,
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
        assert config.workspace_dir == "workspaces"
        assert config.watched_statuses == ["Research", "Plan", "Implement"]
        assert config.max_concurrent_workflows == 3
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
        monkeypatch.setenv("WORKSPACE_DIR", "env_workspaces")
        monkeypatch.setenv("WATCHED_STATUSES", "Status1, Status2, Status3")
        monkeypatch.setenv("ALLOWED_USERNAME", "user1")

        config = load_config_from_env()

        assert config.github_token == "env_token"
        assert config.project_urls == [
            "https://github.com/orgs/test/projects/1",
            "https://github.com/orgs/test/projects/2",
        ]
        assert config.poll_interval == 120
        assert config.database_path == "env.db"
        assert config.workspace_dir == "env_workspaces"
        assert config.watched_statuses == ["Status1", "Status2", "Status3"]
        assert config.allowed_username == "user1"

    def test_load_config_with_minimal_env_vars(self, monkeypatch):
        """Test load_config applies defaults when only required vars are set."""
        # Clear any existing environment variables
        for key in [
            "PROJECT_URLS",
            "POLL_INTERVAL",
            "DATABASE_PATH",
            "WORKSPACE_DIR",
            "WATCHED_STATUSES",
            "MAX_CONCURRENT_WORKFLOWS",
        ]:
            monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("GITHUB_TOKEN", "minimal_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/chronoboost/projects/6/views/2")
        monkeypatch.setenv("ALLOWED_USERNAME", "testuser")

        config = load_config_from_env()

        assert config.github_token == "minimal_token"
        assert config.project_urls == ["https://github.com/orgs/chronoboost/projects/6/views/2"]
        assert config.poll_interval == 30
        assert config.database_path == ".kiln/kiln.db"
        assert config.workspace_dir == "workspaces"
        assert config.watched_statuses == ["Research", "Plan", "Implement"]
        assert config.max_concurrent_workflows == 3
        assert config.allowed_username == "testuser"

    def test_load_config_missing_github_token(self, monkeypatch):
        """Test load_config accepts missing GITHUB_TOKEN."""
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("ALLOWED_USERNAME", "testuser")

        config = load_config_from_env()

        assert config.github_token is None

    def test_load_config_empty_github_token(self, monkeypatch):
        """Test load_config normalizes empty GITHUB_TOKEN to None."""
        monkeypatch.setenv("GITHUB_TOKEN", "")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("ALLOWED_USERNAME", "testuser")

        config = load_config_from_env()

        assert config.github_token is None

    def test_load_config_watched_statuses_with_spaces(self, monkeypatch):
        """Test watched_statuses parsing handles spaces correctly."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("WATCHED_STATUSES", "  Status 1  ,  Status 2  ,  Status 3  ")
        monkeypatch.setenv("ALLOWED_USERNAME", "testuser")

        config = load_config_from_env()

        assert config.watched_statuses == ["Status 1", "Status 2", "Status 3"]

    def test_load_config_poll_interval_conversion(self, monkeypatch):
        """Test poll_interval is correctly converted to int."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("POLL_INTERVAL", "300")
        monkeypatch.setenv("ALLOWED_USERNAME", "testuser")

        config = load_config_from_env()

        assert config.poll_interval == 300
        assert isinstance(config.poll_interval, int)

    def test_load_config_single_watched_status(self, monkeypatch):
        """Test watched_statuses with a single status."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("WATCHED_STATUSES", "OnlyOne")
        monkeypatch.setenv("ALLOWED_USERNAME", "testuser")

        config = load_config_from_env()

        assert config.watched_statuses == ["OnlyOne"]

    def test_load_config_preserves_env_values_between_calls(self, monkeypatch):
        """Test that load_config reads fresh values from environment each time."""
        monkeypatch.setenv("GITHUB_TOKEN", "token1")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("POLL_INTERVAL", "30")
        monkeypatch.setenv("ALLOWED_USERNAME", "testuser")

        config1 = load_config_from_env()
        assert config1.poll_interval == 30

        monkeypatch.setenv("POLL_INTERVAL", "60")
        config2 = load_config_from_env()
        assert config2.poll_interval == 60

    def test_load_config_missing_project_urls(self, monkeypatch):
        """Test load_config raises ValueError when PROJECT_URLS is missing."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.delenv("PROJECT_URLS", raising=False)

        with pytest.raises(ValueError, match="PROJECT_URLS environment variable is required"):
            load_config_from_env()

    def test_load_config_project_urls_comma_separated(self, monkeypatch):
        """Test PROJECT_URLS with comma-separated URLs."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv(
            "PROJECT_URLS",
            "https://github.com/orgs/test/projects/1, https://github.com/orgs/test/projects/2",
        )
        monkeypatch.setenv("ALLOWED_USERNAME", "testuser")

        config = load_config_from_env()

        assert config.project_urls == [
            "https://github.com/orgs/test/projects/1",
            "https://github.com/orgs/test/projects/2",
        ]

    def test_load_config_single_project_url(self, monkeypatch):
        """Test PROJECT_URLS with a single URL."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("ALLOWED_USERNAME", "testuser")

        config = load_config_from_env()

        assert config.project_urls == ["https://github.com/orgs/test/projects/1"]

    def test_load_config_default_stage_models(self, monkeypatch):
        """Test load_config applies default stage models."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("ALLOWED_USERNAME", "testuser")
        monkeypatch.delenv("STAGE_MODELS", raising=False)

        config = load_config_from_env()

        assert config.stage_models == {
            "Prepare": "haiku",
            "Research": "opus",
            "Plan": "opus",
            "Implement": "opus",
            "process_comments": "sonnet",
        }

    def test_load_config_custom_stage_models(self, monkeypatch):
        """Test load_config parses STAGE_MODELS JSON correctly."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("ALLOWED_USERNAME", "testuser")
        monkeypatch.setenv("STAGE_MODELS", '{"Prepare": "haiku", "Plan": "opus"}')

        config = load_config_from_env()

        assert config.stage_models == {"Prepare": "haiku", "Plan": "opus"}

    def test_load_config_invalid_stage_models_json(self, monkeypatch):
        """Test load_config raises ValueError for invalid STAGE_MODELS JSON."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("ALLOWED_USERNAME", "testuser")
        monkeypatch.setenv("STAGE_MODELS", "not valid json")

        with pytest.raises(ValueError, match="STAGE_MODELS must be valid JSON"):
            load_config_from_env()

    def test_load_config_claude_code_enable_telemetry_default(self, monkeypatch):
        """Test claude_code_enable_telemetry defaults to False."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("ALLOWED_USERNAME", "testuser")
        monkeypatch.delenv("CLAUDE_CODE_ENABLE_TELEMETRY", raising=False)

        config = load_config_from_env()

        assert config.claude_code_enable_telemetry is False

    def test_load_config_claude_code_enable_telemetry_enabled(self, monkeypatch):
        """Test claude_code_enable_telemetry parses '1' as True."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("ALLOWED_USERNAME", "testuser")
        monkeypatch.setenv("CLAUDE_CODE_ENABLE_TELEMETRY", "1")

        config = load_config_from_env()

        assert config.claude_code_enable_telemetry is True

    def test_load_config_claude_code_enable_telemetry_disabled_explicit(self, monkeypatch):
        """Test claude_code_enable_telemetry parses '0' as False."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("ALLOWED_USERNAME", "testuser")
        monkeypatch.setenv("CLAUDE_CODE_ENABLE_TELEMETRY", "0")

        config = load_config_from_env()

        assert config.claude_code_enable_telemetry is False

    # Tests for ALLOWED_USERNAME

    def test_load_config_missing_allowed_username(self, monkeypatch):
        """Test load_config raises ValueError when ALLOWED_USERNAME is missing."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.delenv("ALLOWED_USERNAME", raising=False)

        with pytest.raises(ValueError, match="ALLOWED_USERNAME environment variable is required"):
            load_config_from_env()

    def test_load_config_empty_allowed_username(self, monkeypatch):
        """Test load_config raises ValueError when ALLOWED_USERNAME is empty."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("ALLOWED_USERNAME", "")

        with pytest.raises(ValueError, match="ALLOWED_USERNAME environment variable is required"):
            load_config_from_env()

    def test_load_config_allowed_username_whitespace_only(self, monkeypatch):
        """Test load_config raises ValueError when ALLOWED_USERNAME contains only whitespace."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("ALLOWED_USERNAME", "   ")

        with pytest.raises(ValueError, match="ALLOWED_USERNAME environment variable is required"):
            load_config_from_env()

    def test_load_config_allowed_username(self, monkeypatch):
        """Test ALLOWED_USERNAME with a single username."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("ALLOWED_USERNAME", "solo-user")

        config = load_config_from_env()

        assert config.allowed_username == "solo-user"

    def test_load_config_allowed_username_with_spaces(self, monkeypatch):
        """Test ALLOWED_USERNAME parsing trims whitespace."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("ALLOWED_USERNAME", "  user1  ")

        config = load_config_from_env()

        assert config.allowed_username == "user1"


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
        content = f"GITHUB_TOKEN=ghp_test\nPROJECT_URLS=https://github.com/orgs/test/projects/1\nALLOWED_USERNAME=testuser\n{extra_lines}"
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
            "ALLOWED_USERNAME=testuser"
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
        config_file.write_text("GITHUB_TOKEN=ghp_test\nALLOWED_USERNAME=testuser")

        with pytest.raises(ValueError, match="PROJECT_URLS is required"):
            load_config_from_file(config_file)

    def test_load_config_from_file_parses_allowed_username(self, tmp_path, monkeypatch):
        """Test ALLOWED_USERNAME parsing."""
        config_file = tmp_path / "config"
        config_file.write_text(
            "GITHUB_TOKEN=ghp_test\n"
            "PROJECT_URLS=https://github.com/orgs/test/projects/1\n"
            "ALLOWED_USERNAME=myuser"
        )
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        config = load_config_from_file(config_file)

        assert config.allowed_username == "myuser"

    def test_load_config_from_file_raises_on_missing_allowed_username(self, tmp_path):
        """Test ValueError when ALLOWED_USERNAME missing."""
        config_file = tmp_path / "config"
        config_file.write_text(
            "GITHUB_TOKEN=ghp_test\nPROJECT_URLS=https://github.com/orgs/test/projects/1"
        )

        with pytest.raises(ValueError, match="ALLOWED_USERNAME is required"):
            load_config_from_file(config_file)

    def test_load_config_from_file_parses_poll_interval(self, tmp_path, monkeypatch):
        """Test POLL_INTERVAL integer parsing."""
        config_file = tmp_path / "config"
        config_file.write_text(
            "GITHUB_TOKEN=ghp_test\n"
            "PROJECT_URLS=https://github.com/orgs/test/projects/1\n"
            "ALLOWED_USERNAME=testuser\n"
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
            "ALLOWED_USERNAME=testuser\n"
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
            "ALLOWED_USERNAME=testuser"
        )
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        config = load_config_from_file(config_file)

        assert config.poll_interval == 30
        assert config.watched_statuses == ["Research", "Plan", "Implement"]
        assert config.max_concurrent_workflows == 3

    def test_load_config_from_file_parses_stage_models_json(self, tmp_path, monkeypatch):
        """Test STAGE_MODELS JSON parsing."""
        config_file = tmp_path / "config"
        config_file.write_text(
            "GITHUB_TOKEN=ghp_test\n"
            "PROJECT_URLS=https://github.com/orgs/test/projects/1\n"
            "ALLOWED_USERNAME=testuser\n"
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
            "ALLOWED_USERNAME=testuser\n"
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
            "ALLOWED_USERNAME=testuser"
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
            "ALLOWED_USERNAME=testuser\n"
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
            "ALLOWED_USERNAME=testuser\n"
            "MAX_CONCURRENT_WORKFLOWS=5"
        )
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        config = load_config_from_file(config_file)

        assert config.max_concurrent_workflows == 5


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
            "ALLOWED_USERNAME=testuser"
        )

        # Set env vars (should be ignored when file exists)
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_from_env")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/other/projects/2")
        monkeypatch.setenv("ALLOWED_USERNAME", "envuser")

        # Change cwd to temp directory
        monkeypatch.chdir(tmp_path)

        config = load_config()

        assert config.github_token == "ghp_from_file"
        assert config.project_urls == ["https://github.com/orgs/test/projects/1"]
        assert config.allowed_username == "testuser"

    def test_load_config_falls_back_to_env(self, tmp_path, monkeypatch):
        """Test load_config uses env vars when no config file."""
        # Ensure no .kiln/config exists
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_from_env")
        monkeypatch.setenv("PROJECT_URLS", "https://github.com/orgs/test/projects/1")
        monkeypatch.setenv("ALLOWED_USERNAME", "envuser")

        config = load_config()

        assert config.github_token == "ghp_from_env"
        assert config.project_urls == ["https://github.com/orgs/test/projects/1"]
        assert config.allowed_username == "envuser"

    def test_load_config_file_path_is_cwd_relative(self, tmp_path, monkeypatch):
        """Test config file path is .kiln/config relative to cwd."""
        # Create .kiln/config in temp directory
        kiln_dir = tmp_path / ".kiln"
        kiln_dir.mkdir()
        config_file = kiln_dir / "config"
        config_file.write_text(
            "GITHUB_TOKEN=ghp_cwd_test\n"
            "PROJECT_URLS=https://github.com/orgs/test/projects/1\n"
            "ALLOWED_USERNAME=testuser"
        )

        # Change to temp directory
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        config = load_config()

        assert config.github_token == "ghp_cwd_test"
