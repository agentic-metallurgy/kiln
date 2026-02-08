"""MCP Configuration module for kiln.

This module provides management of MCP (Model Context Protocol) server
configurations, including loading from .kiln/mcp.json, token placeholder
substitution, and writing resolved configurations to worktrees.
"""

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from src.integrations.azure_oauth import AzureOAuthClient, AzureOAuthError

logger = logging.getLogger(__name__)

# Default paths
MCP_CONFIG_PATH = ".kiln/mcp.json"
WORKTREE_CONFIG_NAME = ".mcp.kiln.json"

# Token placeholder pattern: ${AZURE_BEARER_TOKEN}
TOKEN_PLACEHOLDER_PATTERN = re.compile(r"\$\{AZURE_BEARER_TOKEN\}")


class MCPConfigError(Exception):
    """Base exception for MCP configuration errors."""

    pass


class MCPConfigLoadError(MCPConfigError):
    """Error loading MCP configuration file."""

    pass


class MCPConfigWriteError(MCPConfigError):
    """Error writing MCP configuration to worktree."""

    pass


@dataclass
class MCPConfig:
    """Represents a loaded MCP configuration."""

    mcp_servers: dict[str, Any]
    raw_config: dict[str, Any]


class MCPConfigManager:
    """Manager for MCP (Model Context Protocol) server configurations.

    This class handles:
    - Loading MCP server definitions from .kiln/mcp.json
    - Substituting token placeholders (${AZURE_BEARER_TOKEN}) with actual tokens
    - Writing resolved configurations to worktree directories

    Attributes:
        azure_client: Optional Azure OAuth client for token retrieval
        config_path: Path to the MCP configuration file
    """

    def __init__(
        self,
        azure_client: AzureOAuthClient | None = None,
        config_path: str | None = None,
    ):
        """Initialize the MCP configuration manager.

        Args:
            azure_client: Optional Azure OAuth client for token substitution.
                If provided, ${AZURE_BEARER_TOKEN} placeholders will be replaced.
            config_path: Optional path to MCP config file.
                Defaults to .kiln/mcp.json if not specified.
        """
        self.azure_client = azure_client
        self.config_path = config_path or MCP_CONFIG_PATH
        self._cached_config: MCPConfig | None = None

    def load_config(self) -> MCPConfig | None:
        """Load MCP configuration from the config file.

        Returns:
            MCPConfig if the file exists and is valid, None otherwise.

        Raises:
            MCPConfigLoadError: If the file exists but cannot be parsed.
        """
        config_path = Path(self.config_path)

        if not config_path.exists():
            logger.debug(f"MCP config file not found at {self.config_path}")
            return None

        try:
            with open(config_path, encoding="utf-8") as f:
                raw_config = json.load(f)
        except json.JSONDecodeError as e:
            raise MCPConfigLoadError(
                f"Invalid JSON in MCP config file {self.config_path}: {e}"
            ) from e
        except OSError as e:
            raise MCPConfigLoadError(
                f"Failed to read MCP config file {self.config_path}: {e}"
            ) from e

        # Validate structure
        if not isinstance(raw_config, dict):
            raise MCPConfigLoadError(
                f"MCP config must be a JSON object, got {type(raw_config).__name__}"
            )

        mcp_servers = raw_config.get("mcpServers", {})
        if not isinstance(mcp_servers, dict):
            raise MCPConfigLoadError(
                f"mcpServers must be an object, got {type(mcp_servers).__name__}"
            )

        self._cached_config = MCPConfig(
            mcp_servers=mcp_servers,
            raw_config=raw_config,
        )

        logger.info(f"Loaded MCP config with {len(mcp_servers)} server(s)")
        return self._cached_config

    def has_config(self) -> bool:
        """Check if MCP config exists and has server definitions.

        Returns:
            True if MCP config file exists and contains at least one server.
        """
        try:
            config = self.load_config()
            return config is not None and len(config.mcp_servers) > 0
        except MCPConfigError:
            return False

    def _substitute_tokens(self, config: dict[str, Any]) -> dict[str, Any]:
        """Substitute token placeholders in the configuration.

        Recursively traverses the configuration and replaces ${AZURE_BEARER_TOKEN}
        placeholders with actual tokens from the Azure OAuth client.

        Args:
            config: Configuration dictionary to process.

        Returns:
            New configuration dictionary with tokens substituted.
        """
        if self.azure_client is None:
            return config

        try:
            token = self.azure_client.get_token()
        except AzureOAuthError as e:
            logger.warning(f"Failed to get Azure OAuth token for MCP config: {e}")
            # Return config without substitution - let MCP server handle auth failure
            return config

        def substitute_recursive(obj: Any) -> Any:
            """Recursively substitute tokens in nested structures."""
            if isinstance(obj, str):
                return TOKEN_PLACEHOLDER_PATTERN.sub(token, obj)
            elif isinstance(obj, dict):
                return {k: substitute_recursive(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [substitute_recursive(item) for item in obj]
            else:
                return obj

        return cast(dict[str, Any], substitute_recursive(config))

    def write_to_worktree(self, worktree_path: str) -> str | None:
        """Write resolved MCP configuration to a worktree directory.

        Loads the MCP config, substitutes tokens, and writes the resolved
        configuration to .mcp.kiln.json in the specified worktree.

        Args:
            worktree_path: Path to the worktree directory.

        Returns:
            Absolute path to the written config file, or None if no config exists.

        Raises:
            MCPConfigWriteError: If writing the configuration fails.
        """
        config = self.load_config()
        if config is None or len(config.mcp_servers) == 0:
            logger.debug("No MCP config to write to worktree")
            return None

        # Substitute tokens in the raw config
        resolved_config = self._substitute_tokens(config.raw_config)

        # Determine output path
        output_path = Path(worktree_path) / WORKTREE_CONFIG_NAME

        try:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(resolved_config, f, indent=2)
        except OSError as e:
            raise MCPConfigWriteError(f"Failed to write MCP config to {output_path}: {e}") from e

        logger.info(f"Wrote MCP config to {output_path}")
        return str(output_path.absolute())

    def get_worktree_config_path(self, worktree_path: str) -> str:
        """Get the path where MCP config would be written in a worktree.

        Args:
            worktree_path: Path to the worktree directory.

        Returns:
            Absolute path to the config file location.
        """
        return str((Path(worktree_path) / WORKTREE_CONFIG_NAME).absolute())

    def clear_cache(self) -> None:
        """Clear the cached configuration.

        Forces the next load_config() call to re-read from disk.
        """
        self._cached_config = None
        logger.debug("MCP config cache cleared")

    def is_remote_server(self, server_config: dict[str, Any]) -> bool:
        """Check if server config is for a remote MCP (has url field).

        Remote MCPs use HTTP/SSE transport via a URL instead of launching
        a local subprocess via command.

        Args:
            server_config: Server configuration dictionary.

        Returns:
            True if the server is configured for remote transport (has url field).
        """
        return "url" in server_config

    def validate_config(self) -> list[str]:
        """Validate the MCP configuration and return any warnings.

        Returns:
            List of warning messages for potential issues.
        """
        warnings = []

        try:
            config = self.load_config()
        except MCPConfigError as e:
            return [str(e)]

        if config is None:
            return []

        # Check for token placeholders without Azure client
        config_str = json.dumps(config.raw_config)
        has_placeholder = TOKEN_PLACEHOLDER_PATTERN.search(config_str) is not None

        if has_placeholder and self.azure_client is None:
            warnings.append(
                "MCP config contains ${AZURE_BEARER_TOKEN} placeholder but "
                "no Azure OAuth client is configured. Tokens will not be substituted."
            )

        # Validate each server has required fields
        for server_name, server_config in config.mcp_servers.items():
            if not isinstance(server_config, dict):
                warnings.append(f"MCP server '{server_name}' config is not an object")
                continue

            # Only warn about missing command for local (non-remote) servers
            if "command" not in server_config and not self.is_remote_server(server_config):
                warnings.append(
                    f"MCP server '{server_name}' is missing 'command' field (local server)"
                )

        return warnings
