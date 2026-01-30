"""MCP client module for testing server connectivity at startup.

This module provides functionality to test MCP server connections and list
available tools at daemon startup. It supports both local (stdio) and remote
(HTTP/SSE) MCP transports.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

logger = logging.getLogger(__name__)


@dataclass
class MCPTestResult:
    """Result from testing an MCP server connection.

    Attributes:
        server_name: Name/identifier of the MCP server.
        success: Whether the connection and tool listing succeeded.
        tools: List of tool names available on the server (if successful).
        error: Error message if connection failed.
    """

    server_name: str
    success: bool
    tools: list[str] = field(default_factory=list)
    error: str | None = None


def _is_remote_server(server_config: dict[str, Any]) -> bool:
    """Check if server config is for a remote MCP (has url field).

    Args:
        server_config: Server configuration dictionary.

    Returns:
        True if the server uses HTTP/SSE transport (has url field).
    """
    return "url" in server_config


async def _test_stdio_server(
    server_name: str,
    server_config: dict[str, Any],
    timeout: float,
) -> MCPTestResult:
    """Test connectivity to a local stdio MCP server.

    Args:
        server_name: Name/identifier of the server.
        server_config: Server configuration with command, args, env fields.
        timeout: Connection timeout in seconds.

    Returns:
        MCPTestResult with success status and tool list or error.
    """
    command = server_config.get("command")
    if not command:
        return MCPTestResult(
            server_name=server_name,
            success=False,
            error="missing 'command' field",
        )

    args = server_config.get("args", [])
    env = server_config.get("env")

    server_params = StdioServerParameters(
        command=command,
        args=args,
        env=env,
    )

    try:
        async with asyncio.timeout(timeout):
            async with stdio_client(server_params) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    tools_result = await session.list_tools()
                    tool_names = sorted([tool.name for tool in tools_result.tools])

                    return MCPTestResult(
                        server_name=server_name,
                        success=True,
                        tools=tool_names,
                    )

    except TimeoutError:
        return MCPTestResult(
            server_name=server_name,
            success=False,
            error=f"timeout after {timeout}s",
        )
    except Exception as e:
        error_msg = str(e) if str(e) else type(e).__name__
        return MCPTestResult(
            server_name=server_name,
            success=False,
            error=f"connection failed ({error_msg})",
        )


async def _test_http_server(
    server_name: str,
    server_config: dict[str, Any],
    timeout: float,
) -> MCPTestResult:
    """Test connectivity to a remote HTTP/SSE MCP server.

    Args:
        server_name: Name/identifier of the server.
        server_config: Server configuration with url and optional headers/env.
        timeout: Connection timeout in seconds.

    Returns:
        MCPTestResult with success status and tool list or error.
    """
    url = server_config.get("url")
    if not url:
        return MCPTestResult(
            server_name=server_name,
            success=False,
            error="missing 'url' field",
        )

    # Build headers from env if present (common pattern for auth tokens)
    headers: dict[str, str] = {}
    if "env" in server_config and isinstance(server_config["env"], dict):
        # Look for common auth header patterns
        env = server_config["env"]
        if "AUTHORIZATION" in env:
            headers["Authorization"] = env["AUTHORIZATION"]
        elif "API_KEY" in env:
            headers["X-API-Key"] = env["API_KEY"]

    try:
        async with asyncio.timeout(timeout):
            async with streamablehttp_client(
                url=url,
                headers=headers if headers else None,
                timeout=timeout,
            ) as (read_stream, write_stream, _):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    tools_result = await session.list_tools()
                    tool_names = sorted([tool.name for tool in tools_result.tools])

                    return MCPTestResult(
                        server_name=server_name,
                        success=True,
                        tools=tool_names,
                    )

    except TimeoutError:
        return MCPTestResult(
            server_name=server_name,
            success=False,
            error=f"timeout after {timeout}s",
        )
    except Exception as e:
        error_msg = str(e) if str(e) else type(e).__name__
        return MCPTestResult(
            server_name=server_name,
            success=False,
            error=f"connection failed ({error_msg})",
        )


async def check_mcp_server(
    server_name: str,
    server_config: dict[str, Any],
    timeout: float = 30.0,
) -> MCPTestResult:
    """Test connectivity to a single MCP server and list its tools.

    Automatically detects the transport type (stdio vs HTTP) based on the
    server configuration and tests connectivity accordingly.

    Args:
        server_name: Name/identifier of the server (used for logging).
        server_config: Server configuration dictionary. Should contain either:
            - Local servers: 'command' (required), 'args' (optional), 'env' (optional)
            - Remote servers: 'url' (required), 'env' (optional for auth)
        timeout: Maximum time to wait for connection in seconds. Default: 30.0

    Returns:
        MCPTestResult containing:
            - server_name: The name passed in
            - success: True if connection succeeded and tools were listed
            - tools: List of tool names (empty list if failed)
            - error: Error message if failed, None if successful
    """
    if _is_remote_server(server_config):
        return await _test_http_server(server_name, server_config, timeout)
    else:
        return await _test_stdio_server(server_name, server_config, timeout)


async def check_all_mcp_servers(
    mcp_servers: dict[str, dict[str, Any]],
    timeout: float = 30.0,
) -> list[MCPTestResult]:
    """Test all configured MCP servers in parallel.

    Connects to each server, initializes the session, and lists available tools.
    All servers are tested concurrently for efficiency.

    Args:
        mcp_servers: Dictionary mapping server names to their configurations.
            Each configuration should have either 'command' (for local stdio servers)
            or 'url' (for remote HTTP/SSE servers).
        timeout: Maximum time to wait for each server connection in seconds.
            Default: 30.0

    Returns:
        List of MCPTestResult objects, one per server. Results are returned in
        no guaranteed order (since tests run concurrently).

    Example:
        >>> servers = {
        ...     "jenkins": {"url": "https://jenkins.example.com/mcp"},
        ...     "filesystem": {"command": "npx", "args": ["-y", "@test/fs-server"]},
        ... }
        >>> results = await check_all_mcp_servers(servers)
        >>> for r in results:
        ...     print(f"{r.server_name}: {r.success}")
    """
    if not mcp_servers:
        return []

    tasks = [
        check_mcp_server(server_name, server_config, timeout)
        for server_name, server_config in mcp_servers.items()
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Convert any exceptions to MCPTestResult
    final_results: list[MCPTestResult] = []
    for result, (server_name, _) in zip(results, mcp_servers.items(), strict=True):
        if isinstance(result, BaseException):
            final_results.append(
                MCPTestResult(
                    server_name=server_name,
                    success=False,
                    error=f"unexpected error: {result}",
                )
            )
        else:
            # result is MCPTestResult after BaseException check
            final_results.append(result)

    return final_results
