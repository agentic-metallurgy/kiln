"""Unit tests for the MCP configuration module."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.azure_oauth import AzureOAuthClient, AzureTokenRequestError
from src.mcp_config import (
    MCP_CONFIG_PATH,
    TOKEN_PLACEHOLDER_PATTERN,
    WORKTREE_CONFIG_NAME,
    MCPConfig,
    MCPConfigError,
    MCPConfigLoadError,
    MCPConfigManager,
    MCPConfigWriteError,
)


@pytest.mark.unit
class TestMCPConfig:
    """Tests for MCPConfig dataclass."""

    def test_mcp_config_creation(self):
        """Test creating an MCPConfig instance."""
        mcp_servers = {"server1": {"command": "test"}}
        raw_config = {"mcpServers": mcp_servers}

        config = MCPConfig(mcp_servers=mcp_servers, raw_config=raw_config)

        assert config.mcp_servers == mcp_servers
        assert config.raw_config == raw_config


@pytest.mark.unit
class TestMCPConfigManager:
    """Tests for MCPConfigManager initialization."""

    def test_manager_initialization_defaults(self):
        """Test manager initialization with default values."""
        manager = MCPConfigManager()

        assert manager.azure_client is None
        assert manager.config_path == MCP_CONFIG_PATH

    def test_manager_initialization_with_azure_client(self):
        """Test manager initialization with Azure client."""
        mock_client = MagicMock(spec=AzureOAuthClient)
        manager = MCPConfigManager(azure_client=mock_client)

        assert manager.azure_client is mock_client

    def test_manager_initialization_with_custom_path(self):
        """Test manager initialization with custom config path."""
        manager = MCPConfigManager(config_path="/custom/path/mcp.json")

        assert manager.config_path == "/custom/path/mcp.json"


@pytest.mark.unit
class TestMCPConfigManagerLoadConfig:
    """Tests for MCPConfigManager.load_config()."""

    def test_load_config_file_not_found(self):
        """Test loading when config file doesn't exist."""
        manager = MCPConfigManager(config_path="/nonexistent/mcp.json")

        result = manager.load_config()

        assert result is None

    def test_load_config_success(self):
        """Test successfully loading a valid config file."""
        config_data = {
            "mcpServers": {
                "test-server": {
                    "command": "npx",
                    "args": ["-y", "@test/mcp-server"],
                    "env": {"API_KEY": "test-key"},
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name

        try:
            manager = MCPConfigManager(config_path=config_path)
            result = manager.load_config()

            assert result is not None
            assert "test-server" in result.mcp_servers
            assert result.mcp_servers["test-server"]["command"] == "npx"
            assert result.raw_config == config_data
        finally:
            Path(config_path).unlink()

    def test_load_config_invalid_json(self):
        """Test loading an invalid JSON file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not valid json {")
            config_path = f.name

        try:
            manager = MCPConfigManager(config_path=config_path)

            with pytest.raises(MCPConfigLoadError) as exc_info:
                manager.load_config()

            assert "Invalid JSON" in str(exc_info.value)
        finally:
            Path(config_path).unlink()

    def test_load_config_not_object(self):
        """Test loading a JSON file that's not an object."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(["not", "an", "object"], f)
            config_path = f.name

        try:
            manager = MCPConfigManager(config_path=config_path)

            with pytest.raises(MCPConfigLoadError) as exc_info:
                manager.load_config()

            assert "must be a JSON object" in str(exc_info.value)
        finally:
            Path(config_path).unlink()

    def test_load_config_mcp_servers_not_object(self):
        """Test loading a config where mcpServers is not an object."""
        config_data = {"mcpServers": ["not", "an", "object"]}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name

        try:
            manager = MCPConfigManager(config_path=config_path)

            with pytest.raises(MCPConfigLoadError) as exc_info:
                manager.load_config()

            assert "mcpServers must be an object" in str(exc_info.value)
        finally:
            Path(config_path).unlink()

    def test_load_config_empty_mcp_servers(self):
        """Test loading a config with empty mcpServers."""
        config_data = {"mcpServers": {}}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name

        try:
            manager = MCPConfigManager(config_path=config_path)
            result = manager.load_config()

            assert result is not None
            assert len(result.mcp_servers) == 0
        finally:
            Path(config_path).unlink()

    def test_load_config_missing_mcp_servers_key(self):
        """Test loading a config without mcpServers key."""
        config_data = {"otherKey": "value"}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name

        try:
            manager = MCPConfigManager(config_path=config_path)
            result = manager.load_config()

            assert result is not None
            assert len(result.mcp_servers) == 0
        finally:
            Path(config_path).unlink()


@pytest.mark.unit
class TestMCPConfigManagerHasConfig:
    """Tests for MCPConfigManager.has_config()."""

    def test_has_config_no_file(self):
        """Test has_config when file doesn't exist."""
        manager = MCPConfigManager(config_path="/nonexistent/mcp.json")

        assert manager.has_config() is False

    def test_has_config_empty_servers(self):
        """Test has_config with empty mcpServers."""
        config_data = {"mcpServers": {}}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name

        try:
            manager = MCPConfigManager(config_path=config_path)

            assert manager.has_config() is False
        finally:
            Path(config_path).unlink()

    def test_has_config_with_servers(self):
        """Test has_config with server definitions."""
        config_data = {
            "mcpServers": {
                "test-server": {"command": "test"}
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name

        try:
            manager = MCPConfigManager(config_path=config_path)

            assert manager.has_config() is True
        finally:
            Path(config_path).unlink()

    def test_has_config_invalid_file(self):
        """Test has_config with invalid JSON file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("invalid json")
            config_path = f.name

        try:
            manager = MCPConfigManager(config_path=config_path)

            assert manager.has_config() is False
        finally:
            Path(config_path).unlink()


@pytest.mark.unit
class TestMCPConfigManagerTokenSubstitution:
    """Tests for MCPConfigManager token substitution."""

    def test_substitute_tokens_no_azure_client(self):
        """Test substitution without Azure client returns config unchanged."""
        manager = MCPConfigManager(azure_client=None)
        config = {"env": {"TOKEN": "${AZURE_BEARER_TOKEN}"}}

        result = manager._substitute_tokens(config)

        assert result == config

    def test_substitute_tokens_simple_string(self):
        """Test substitution in a simple string value."""
        mock_client = MagicMock(spec=AzureOAuthClient)
        mock_client.get_token.return_value = "actual-token-123"

        manager = MCPConfigManager(azure_client=mock_client)
        config = {"env": {"TOKEN": "${AZURE_BEARER_TOKEN}"}}

        result = manager._substitute_tokens(config)

        assert result["env"]["TOKEN"] == "actual-token-123"
        mock_client.get_token.assert_called_once()

    def test_substitute_tokens_nested_config(self):
        """Test substitution in nested configuration."""
        mock_client = MagicMock(spec=AzureOAuthClient)
        mock_client.get_token.return_value = "nested-token"

        manager = MCPConfigManager(azure_client=mock_client)
        config = {
            "mcpServers": {
                "server1": {
                    "env": {
                        "AUTH": "Bearer ${AZURE_BEARER_TOKEN}",
                        "OTHER": "no-token-here",
                    }
                },
                "server2": {
                    "args": ["--token", "${AZURE_BEARER_TOKEN}"],
                }
            }
        }

        result = manager._substitute_tokens(config)

        assert result["mcpServers"]["server1"]["env"]["AUTH"] == "Bearer nested-token"
        assert result["mcpServers"]["server1"]["env"]["OTHER"] == "no-token-here"
        assert result["mcpServers"]["server2"]["args"][1] == "nested-token"

    def test_substitute_tokens_multiple_placeholders(self):
        """Test substitution of multiple placeholders in one string."""
        mock_client = MagicMock(spec=AzureOAuthClient)
        mock_client.get_token.return_value = "token123"

        manager = MCPConfigManager(azure_client=mock_client)
        config = {"header": "${AZURE_BEARER_TOKEN}:${AZURE_BEARER_TOKEN}"}

        result = manager._substitute_tokens(config)

        assert result["header"] == "token123:token123"

    def test_substitute_tokens_no_placeholders(self):
        """Test config without placeholders remains unchanged."""
        mock_client = MagicMock(spec=AzureOAuthClient)
        mock_client.get_token.return_value = "unused-token"

        manager = MCPConfigManager(azure_client=mock_client)
        config = {"env": {"KEY": "regular-value"}}

        result = manager._substitute_tokens(config)

        assert result == {"env": {"KEY": "regular-value"}}

    def test_substitute_tokens_azure_error(self):
        """Test substitution when Azure client fails returns original config."""
        mock_client = MagicMock(spec=AzureOAuthClient)
        mock_client.get_token.side_effect = AzureTokenRequestError("Auth failed")

        manager = MCPConfigManager(azure_client=mock_client)
        config = {"env": {"TOKEN": "${AZURE_BEARER_TOKEN}"}}

        result = manager._substitute_tokens(config)

        # Original config should be returned without substitution
        assert result == config

    def test_substitute_tokens_preserves_non_string_values(self):
        """Test that non-string values are preserved."""
        mock_client = MagicMock(spec=AzureOAuthClient)
        mock_client.get_token.return_value = "token"

        manager = MCPConfigManager(azure_client=mock_client)
        config = {
            "port": 8080,
            "enabled": True,
            "items": [1, 2, 3],
            "nested": None,
        }

        result = manager._substitute_tokens(config)

        assert result["port"] == 8080
        assert result["enabled"] is True
        assert result["items"] == [1, 2, 3]
        assert result["nested"] is None


@pytest.mark.unit
class TestMCPConfigManagerWriteToWorktree:
    """Tests for MCPConfigManager.write_to_worktree()."""

    def test_write_to_worktree_no_config(self):
        """Test write_to_worktree when no config exists."""
        manager = MCPConfigManager(config_path="/nonexistent/mcp.json")

        with tempfile.TemporaryDirectory() as worktree_path:
            result = manager.write_to_worktree(worktree_path)

            assert result is None
            assert not (Path(worktree_path) / WORKTREE_CONFIG_NAME).exists()

    def test_write_to_worktree_empty_servers(self):
        """Test write_to_worktree when mcpServers is empty."""
        config_data = {"mcpServers": {}}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name

        try:
            manager = MCPConfigManager(config_path=config_path)

            with tempfile.TemporaryDirectory() as worktree_path:
                result = manager.write_to_worktree(worktree_path)

                assert result is None
                assert not (Path(worktree_path) / WORKTREE_CONFIG_NAME).exists()
        finally:
            Path(config_path).unlink()

    def test_write_to_worktree_success(self):
        """Test successful write to worktree."""
        config_data = {
            "mcpServers": {
                "test-server": {"command": "test-cmd"}
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name

        try:
            manager = MCPConfigManager(config_path=config_path)

            with tempfile.TemporaryDirectory() as worktree_path:
                result = manager.write_to_worktree(worktree_path)

                assert result is not None
                assert Path(result).exists()
                assert Path(result).name == WORKTREE_CONFIG_NAME

                # Verify written content
                with open(result) as f:
                    written_config = json.load(f)
                assert written_config == config_data
        finally:
            Path(config_path).unlink()

    def test_write_to_worktree_with_token_substitution(self):
        """Test write to worktree with token substitution."""
        config_data = {
            "mcpServers": {
                "auth-server": {
                    "command": "server",
                    "env": {"TOKEN": "${AZURE_BEARER_TOKEN}"}
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name

        try:
            mock_client = MagicMock(spec=AzureOAuthClient)
            mock_client.get_token.return_value = "substituted-token"

            manager = MCPConfigManager(
                azure_client=mock_client,
                config_path=config_path,
            )

            with tempfile.TemporaryDirectory() as worktree_path:
                result = manager.write_to_worktree(worktree_path)

                assert result is not None

                with open(result) as f:
                    written_config = json.load(f)

                assert written_config["mcpServers"]["auth-server"]["env"]["TOKEN"] == "substituted-token"
        finally:
            Path(config_path).unlink()

    def test_write_to_worktree_returns_absolute_path(self):
        """Test that write_to_worktree returns absolute path."""
        config_data = {"mcpServers": {"s": {"command": "c"}}}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name

        try:
            manager = MCPConfigManager(config_path=config_path)

            with tempfile.TemporaryDirectory() as worktree_path:
                result = manager.write_to_worktree(worktree_path)

                assert Path(result).is_absolute()
        finally:
            Path(config_path).unlink()


@pytest.mark.unit
class TestMCPConfigManagerGetWorktreeConfigPath:
    """Tests for MCPConfigManager.get_worktree_config_path()."""

    def test_get_worktree_config_path(self):
        """Test getting the worktree config path."""
        manager = MCPConfigManager()

        result = manager.get_worktree_config_path("/path/to/worktree")

        assert WORKTREE_CONFIG_NAME in result
        assert Path(result).is_absolute()

    def test_get_worktree_config_path_relative_input(self):
        """Test with relative worktree path returns absolute."""
        manager = MCPConfigManager()

        result = manager.get_worktree_config_path("relative/worktree")

        assert Path(result).is_absolute()


@pytest.mark.unit
class TestMCPConfigManagerClearCache:
    """Tests for MCPConfigManager.clear_cache()."""

    def test_clear_cache(self):
        """Test that clear_cache resets the cached config."""
        config_data = {"mcpServers": {"s": {"command": "c"}}}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name

        try:
            manager = MCPConfigManager(config_path=config_path)

            # Load config (populates cache)
            manager.load_config()
            assert manager._cached_config is not None

            # Clear cache
            manager.clear_cache()
            assert manager._cached_config is None
        finally:
            Path(config_path).unlink()


@pytest.mark.unit
class TestMCPConfigManagerValidateConfig:
    """Tests for MCPConfigManager.validate_config()."""

    def test_validate_config_no_file(self):
        """Test validation when file doesn't exist."""
        manager = MCPConfigManager(config_path="/nonexistent/mcp.json")

        warnings = manager.validate_config()

        assert len(warnings) == 0

    def test_validate_config_invalid_file(self):
        """Test validation returns error for invalid file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("invalid json")
            config_path = f.name

        try:
            manager = MCPConfigManager(config_path=config_path)

            warnings = manager.validate_config()

            assert len(warnings) == 1
            assert "Invalid JSON" in warnings[0]
        finally:
            Path(config_path).unlink()

    def test_validate_config_placeholder_without_azure_client(self):
        """Test warning for placeholder without Azure client."""
        config_data = {
            "mcpServers": {
                "server": {
                    "command": "cmd",
                    "env": {"TOKEN": "${AZURE_BEARER_TOKEN}"}
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name

        try:
            manager = MCPConfigManager(config_path=config_path, azure_client=None)

            warnings = manager.validate_config()

            assert any("Azure OAuth client" in w for w in warnings)
        finally:
            Path(config_path).unlink()

    def test_validate_config_missing_command(self):
        """Test warning for local server missing command field."""
        config_data = {
            "mcpServers": {
                "no-command-server": {
                    "args": ["--test"]
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name

        try:
            manager = MCPConfigManager(config_path=config_path)

            warnings = manager.validate_config()

            assert any("missing 'command'" in w for w in warnings)
            assert any("local server" in w for w in warnings)
        finally:
            Path(config_path).unlink()

    def test_validate_config_server_not_object(self):
        """Test warning for server config that's not an object."""
        config_data = {
            "mcpServers": {
                "bad-server": "not an object"
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name

        try:
            manager = MCPConfigManager(config_path=config_path)

            warnings = manager.validate_config()

            assert any("not an object" in w for w in warnings)
        finally:
            Path(config_path).unlink()

    def test_validate_config_valid_config(self):
        """Test validation passes for valid config."""
        mock_client = MagicMock(spec=AzureOAuthClient)

        config_data = {
            "mcpServers": {
                "valid-server": {
                    "command": "test-command",
                    "args": ["--arg1"],
                    "env": {"TOKEN": "${AZURE_BEARER_TOKEN}"}
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name

        try:
            manager = MCPConfigManager(config_path=config_path, azure_client=mock_client)

            warnings = manager.validate_config()

            assert len(warnings) == 0
        finally:
            Path(config_path).unlink()


@pytest.mark.unit
class TestMCPConfigManagerIsRemoteServer:
    """Tests for MCPConfigManager.is_remote_server()."""

    def test_is_remote_server_with_url(self):
        """Test that server with url field is detected as remote."""
        manager = MCPConfigManager()
        server_config = {"url": "https://api.example.com/mcp"}

        assert manager.is_remote_server(server_config) is True

    def test_is_remote_server_with_url_and_other_fields(self):
        """Test remote server with additional config fields."""
        manager = MCPConfigManager()
        server_config = {
            "url": "https://api.example.com/mcp",
            "env": {"API_KEY": "test-key"},
            "transport": "streamable-http",
        }

        assert manager.is_remote_server(server_config) is True

    def test_is_remote_server_local_with_command(self):
        """Test that server with command (no url) is local."""
        manager = MCPConfigManager()
        server_config = {"command": "npx", "args": ["-y", "@test/mcp-server"]}

        assert manager.is_remote_server(server_config) is False

    def test_is_remote_server_empty_config(self):
        """Test that empty config is not detected as remote."""
        manager = MCPConfigManager()
        server_config = {}

        assert manager.is_remote_server(server_config) is False

    def test_is_remote_server_only_args(self):
        """Test server with only args (missing command and url) is not remote."""
        manager = MCPConfigManager()
        server_config = {"args": ["--test"]}

        assert manager.is_remote_server(server_config) is False


@pytest.mark.unit
class TestMCPConfigManagerValidateRemoteServers:
    """Tests for validate_config() handling of remote servers."""

    def test_validate_config_remote_server_no_command_warning(self):
        """Test that remote servers don't trigger 'missing command' warning."""
        config_data = {
            "mcpServers": {
                "remote-server": {
                    "url": "https://api.example.com/mcp",
                    "env": {"API_KEY": "test-key"},
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name

        try:
            manager = MCPConfigManager(config_path=config_path)

            warnings = manager.validate_config()

            # Should NOT have any warning about missing 'command' field
            assert not any("missing 'command'" in w for w in warnings)
        finally:
            Path(config_path).unlink()

    def test_validate_config_local_server_missing_command_warns(self):
        """Test that local servers without command still trigger warning."""
        config_data = {
            "mcpServers": {
                "local-server-without-command": {
                    "args": ["--test"]
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name

        try:
            manager = MCPConfigManager(config_path=config_path)

            warnings = manager.validate_config()

            # Should have warning about missing 'command' field for local server
            assert any("missing 'command'" in w for w in warnings)
            assert any("local server" in w for w in warnings)
        finally:
            Path(config_path).unlink()

    def test_validate_config_mixed_local_and_remote_servers(self):
        """Test validation with both local and remote servers."""
        config_data = {
            "mcpServers": {
                "remote-jenkins": {
                    "url": "https://jenkins.example.com/mcp",
                },
                "local-filesystem": {
                    "command": "npx",
                    "args": ["-y", "@test/fs-server"],
                },
                "local-missing-command": {
                    "args": ["--some-arg"]
                },
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name

        try:
            manager = MCPConfigManager(config_path=config_path)

            warnings = manager.validate_config()

            # Should only warn about the local server missing command
            assert len(warnings) == 1
            assert "local-missing-command" in warnings[0]
            assert "missing 'command'" in warnings[0]
            # Should NOT warn about remote-jenkins
            assert not any("remote-jenkins" in w for w in warnings)
        finally:
            Path(config_path).unlink()

    def test_validate_config_multiple_remote_servers(self):
        """Test validation with multiple remote servers (none should warn)."""
        config_data = {
            "mcpServers": {
                "remote-server-1": {
                    "url": "https://api1.example.com/mcp",
                },
                "remote-server-2": {
                    "url": "https://api2.example.com/mcp",
                    "transport": "sse",
                },
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name

        try:
            manager = MCPConfigManager(config_path=config_path)

            warnings = manager.validate_config()

            # No warnings should be produced
            assert len(warnings) == 0
        finally:
            Path(config_path).unlink()


@pytest.mark.unit
class TestMCPConfigExceptions:
    """Tests for MCP config exception classes."""

    def test_mcp_config_error_base(self):
        """Test MCPConfigError is base exception."""
        error = MCPConfigError("Test error")
        assert str(error) == "Test error"
        assert isinstance(error, Exception)

    def test_mcp_config_load_error(self):
        """Test MCPConfigLoadError."""
        error = MCPConfigLoadError("Load failed")
        assert str(error) == "Load failed"
        assert isinstance(error, MCPConfigError)

    def test_mcp_config_write_error(self):
        """Test MCPConfigWriteError."""
        error = MCPConfigWriteError("Write failed")
        assert str(error) == "Write failed"
        assert isinstance(error, MCPConfigError)


@pytest.mark.unit
class TestConstants:
    """Tests for module constants."""

    def test_mcp_config_path(self):
        """Test MCP_CONFIG_PATH constant."""
        assert MCP_CONFIG_PATH == ".kiln/mcp.json"

    def test_worktree_config_name(self):
        """Test WORKTREE_CONFIG_NAME constant."""
        assert WORKTREE_CONFIG_NAME == ".mcp.kiln.json"

    def test_token_placeholder_pattern(self):
        """Test TOKEN_PLACEHOLDER_PATTERN matches correctly."""
        assert TOKEN_PLACEHOLDER_PATTERN.search("${AZURE_BEARER_TOKEN}") is not None
        assert TOKEN_PLACEHOLDER_PATTERN.search("Bearer ${AZURE_BEARER_TOKEN}") is not None
        assert TOKEN_PLACEHOLDER_PATTERN.search("no token here") is None
        assert TOKEN_PLACEHOLDER_PATTERN.search("${OTHER_TOKEN}") is None
