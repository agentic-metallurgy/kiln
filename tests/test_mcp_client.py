"""Unit tests for the MCP client module."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.mcp_client import (
    MCPTestResult,
    _is_remote_server,
    _test_http_server,
    _test_stdio_server,
    check_all_mcp_servers,
    check_mcp_server,
)


@pytest.mark.unit
class TestMCPTestResult:
    """Tests for MCPTestResult dataclass."""

    def test_result_success(self):
        """Test creating a successful result."""
        result = MCPTestResult(
            server_name="test-server",
            success=True,
            tools=["tool1", "tool2"],
        )

        assert result.server_name == "test-server"
        assert result.success is True
        assert result.tools == ["tool1", "tool2"]
        assert result.error is None

    def test_result_failure(self):
        """Test creating a failure result."""
        result = MCPTestResult(
            server_name="failed-server",
            success=False,
            error="connection refused",
        )

        assert result.server_name == "failed-server"
        assert result.success is False
        assert result.tools == []
        assert result.error == "connection refused"

    def test_result_defaults(self):
        """Test default values for result fields."""
        result = MCPTestResult(server_name="server", success=True)

        assert result.tools == []
        assert result.error is None


@pytest.mark.unit
class TestIsRemoteServer:
    """Tests for _is_remote_server helper function."""

    def test_remote_server_with_url(self):
        """Test server with url field is detected as remote."""
        config = {"url": "https://api.example.com/mcp"}

        assert _is_remote_server(config) is True

    def test_remote_server_with_url_and_extras(self):
        """Test remote server with additional config fields."""
        config = {
            "url": "https://api.example.com/mcp",
            "env": {"API_KEY": "secret"},
            "transport": "streamable-http",
        }

        assert _is_remote_server(config) is True

    def test_local_server_with_command(self):
        """Test server with command (no url) is local."""
        config = {"command": "npx", "args": ["-y", "@test/mcp-server"]}

        assert _is_remote_server(config) is False

    def test_empty_config_is_local(self):
        """Test empty config is not detected as remote."""
        config = {}

        assert _is_remote_server(config) is False


@pytest.mark.unit
class TestTestStdioServer:
    """Tests for _test_stdio_server function."""

    @pytest.mark.asyncio
    async def test_missing_command_returns_error(self):
        """Test that missing command field returns error result."""
        config = {"args": ["--test"]}

        result = await _test_stdio_server("server", config, timeout=5.0)

        assert result.success is False
        assert "missing 'command'" in result.error

    @pytest.mark.asyncio
    async def test_successful_connection(self):
        """Test successful stdio server connection."""
        config = {"command": "test-cmd", "args": ["--arg"]}

        # Create mock tools
        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_tools_result = MagicMock()
        mock_tools_result.tools = [mock_tool]

        # Mock the session
        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()
        mock_session.list_tools = AsyncMock(return_value=mock_tools_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        # Mock the client context manager
        mock_client_cm = AsyncMock()
        mock_client_cm.__aenter__ = AsyncMock(return_value=(MagicMock(), MagicMock()))
        mock_client_cm.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.mcp_client.stdio_client", return_value=mock_client_cm),
            patch("src.mcp_client.ClientSession", return_value=mock_session),
        ):
            result = await _test_stdio_server("test-server", config, timeout=5.0)

        assert result.success is True
        assert result.server_name == "test-server"
        assert "test_tool" in result.tools

    @pytest.mark.asyncio
    async def test_connection_timeout(self):
        """Test timeout handling for slow servers."""
        config = {"command": "slow-cmd"}

        async def slow_connect(*args):
            await asyncio.sleep(10)

        mock_client_cm = AsyncMock()
        mock_client_cm.__aenter__ = slow_connect
        mock_client_cm.__aexit__ = AsyncMock(return_value=None)

        with patch("src.mcp_client.stdio_client", return_value=mock_client_cm):
            result = await _test_stdio_server("slow-server", config, timeout=0.1)

        assert result.success is False
        assert "timeout" in result.error.lower()

    @pytest.mark.asyncio
    async def test_connection_error(self):
        """Test handling of connection errors."""
        config = {"command": "bad-cmd"}

        mock_client_cm = AsyncMock()
        mock_client_cm.__aenter__ = AsyncMock(side_effect=ConnectionError("refused"))
        mock_client_cm.__aexit__ = AsyncMock(return_value=None)

        with patch("src.mcp_client.stdio_client", return_value=mock_client_cm):
            result = await _test_stdio_server("bad-server", config, timeout=5.0)

        assert result.success is False
        assert "connection failed" in result.error.lower()


@pytest.mark.unit
class TestTestHttpServer:
    """Tests for _test_http_server function."""

    @pytest.mark.asyncio
    async def test_missing_url_returns_error(self):
        """Test that missing url field returns error result."""
        config = {"env": {"API_KEY": "test"}}

        result = await _test_http_server("server", config, timeout=5.0)

        assert result.success is False
        assert "missing 'url'" in result.error

    @pytest.mark.asyncio
    async def test_successful_connection(self):
        """Test successful HTTP server connection."""
        config = {"url": "https://api.example.com/mcp"}

        # Create mock tools
        mock_tool1 = MagicMock()
        mock_tool1.name = "tool_b"
        mock_tool2 = MagicMock()
        mock_tool2.name = "tool_a"
        mock_tools_result = MagicMock()
        mock_tools_result.tools = [mock_tool1, mock_tool2]

        # Mock the session
        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()
        mock_session.list_tools = AsyncMock(return_value=mock_tools_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        # Mock the client context manager
        mock_client_cm = AsyncMock()
        mock_client_cm.__aenter__ = AsyncMock(return_value=(MagicMock(), MagicMock(), MagicMock()))
        mock_client_cm.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.mcp_client.streamablehttp_client", return_value=mock_client_cm),
            patch("src.mcp_client.ClientSession", return_value=mock_session),
        ):
            result = await _test_http_server("http-server", config, timeout=5.0)

        assert result.success is True
        assert result.server_name == "http-server"
        # Tools should be sorted
        assert result.tools == ["tool_a", "tool_b"]

    @pytest.mark.asyncio
    async def test_connection_with_auth_headers(self):
        """Test that auth headers are extracted from env."""
        config = {
            "url": "https://api.example.com/mcp",
            "env": {"AUTHORIZATION": "Bearer token123"},
        }

        # Create mock tools
        mock_tools_result = MagicMock()
        mock_tools_result.tools = []

        # Mock the session
        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()
        mock_session.list_tools = AsyncMock(return_value=mock_tools_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        # Mock the client context manager
        mock_client_cm = AsyncMock()
        mock_client_cm.__aenter__ = AsyncMock(return_value=(MagicMock(), MagicMock(), MagicMock()))
        mock_client_cm.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("src.mcp_client.streamablehttp_client", return_value=mock_client_cm) as mock_http,
            patch("src.mcp_client.ClientSession", return_value=mock_session),
        ):
            await _test_http_server("auth-server", config, timeout=5.0)

            # Verify headers were passed
            call_kwargs = mock_http.call_args.kwargs
            assert call_kwargs.get("headers") == {"Authorization": "Bearer token123"}

    @pytest.mark.asyncio
    async def test_connection_timeout(self):
        """Test timeout handling for slow HTTP servers."""
        config = {"url": "https://slow.example.com/mcp"}

        async def slow_connect(*args, **kwargs):
            await asyncio.sleep(10)

        mock_client_cm = AsyncMock()
        mock_client_cm.__aenter__ = slow_connect
        mock_client_cm.__aexit__ = AsyncMock(return_value=None)

        with patch("src.mcp_client.streamablehttp_client", return_value=mock_client_cm):
            result = await _test_http_server("slow-server", config, timeout=0.1)

        assert result.success is False
        assert "timeout" in result.error.lower()


@pytest.mark.unit
class TestCheckMcpServer:
    """Tests for check_mcp_server function."""

    @pytest.mark.asyncio
    async def test_routes_remote_to_http(self):
        """Test that remote servers are routed to HTTP handler."""
        config = {"url": "https://api.example.com/mcp"}

        with patch("src.mcp_client._test_http_server") as mock_http:
            mock_http.return_value = MCPTestResult(
                server_name="test",
                success=True,
                tools=["tool1"],
            )

            result = await check_mcp_server("test", config, timeout=5.0)

            mock_http.assert_called_once_with("test", config, 5.0)
            assert result.success is True

    @pytest.mark.asyncio
    async def test_routes_local_to_stdio(self):
        """Test that local servers are routed to stdio handler."""
        config = {"command": "test-cmd"}

        with patch("src.mcp_client._test_stdio_server") as mock_stdio:
            mock_stdio.return_value = MCPTestResult(
                server_name="test",
                success=True,
                tools=["tool1"],
            )

            result = await check_mcp_server("test", config, timeout=5.0)

            mock_stdio.assert_called_once_with("test", config, 5.0)
            assert result.success is True


@pytest.mark.unit
class TestCheckAllMcpServers:
    """Tests for check_all_mcp_servers function."""

    @pytest.mark.asyncio
    async def test_empty_servers_returns_empty_list(self):
        """Test that empty server dict returns empty results."""
        result = await check_all_mcp_servers({})

        assert result == []

    @pytest.mark.asyncio
    async def test_tests_all_servers_in_parallel(self):
        """Test that all servers are tested concurrently."""
        servers = {
            "server1": {"command": "cmd1"},
            "server2": {"url": "https://api.example.com"},
            "server3": {"command": "cmd3"},
        }

        call_order = []

        async def mock_test(server_name, config, timeout):
            call_order.append(server_name)
            await asyncio.sleep(0.01)  # Small delay to test concurrency
            return MCPTestResult(
                server_name=server_name,
                success=True,
                tools=[f"tool_{server_name}"],
            )

        with patch("src.mcp_client.check_mcp_server", side_effect=mock_test):
            results = await check_all_mcp_servers(servers)

        assert len(results) == 3
        # All servers should have been tested
        assert all(r.success for r in results)
        server_names = {r.server_name for r in results}
        assert server_names == {"server1", "server2", "server3"}

    @pytest.mark.asyncio
    async def test_handles_exceptions_gracefully(self):
        """Test that exceptions from individual tests are handled."""
        servers = {
            "good-server": {"command": "good-cmd"},
            "bad-server": {"command": "bad-cmd"},
        }

        async def mock_test(server_name, config, timeout):
            if server_name == "bad-server":
                raise RuntimeError("Unexpected failure")
            return MCPTestResult(
                server_name=server_name,
                success=True,
                tools=["tool1"],
            )

        with patch("src.mcp_client.check_mcp_server", side_effect=mock_test):
            results = await check_all_mcp_servers(servers)

        assert len(results) == 2

        # Find results by name
        good_result = next(r for r in results if r.server_name == "good-server")
        bad_result = next(r for r in results if r.server_name == "bad-server")

        assert good_result.success is True
        assert bad_result.success is False
        assert "unexpected error" in bad_result.error.lower()

    @pytest.mark.asyncio
    async def test_mixed_success_and_failure(self):
        """Test handling of mixed results (some success, some failure)."""
        servers = {
            "working": {"url": "https://working.example.com"},
            "broken": {"command": "broken-cmd"},
        }

        async def mock_test(server_name, config, timeout):
            if server_name == "working":
                return MCPTestResult(
                    server_name=server_name,
                    success=True,
                    tools=["tool1", "tool2"],
                )
            else:
                return MCPTestResult(
                    server_name=server_name,
                    success=False,
                    error="command not found",
                )

        with patch("src.mcp_client.check_mcp_server", side_effect=mock_test):
            results = await check_all_mcp_servers(servers)

        assert len(results) == 2

        working_result = next(r for r in results if r.server_name == "working")
        broken_result = next(r for r in results if r.server_name == "broken")

        assert working_result.success is True
        assert working_result.tools == ["tool1", "tool2"]

        assert broken_result.success is False
        assert broken_result.error == "command not found"

    @pytest.mark.asyncio
    async def test_respects_timeout_parameter(self):
        """Test that timeout is passed to individual server tests."""
        servers = {"server1": {"command": "cmd"}}

        captured_timeout = None

        async def mock_test(server_name, config, timeout):
            nonlocal captured_timeout
            captured_timeout = timeout
            return MCPTestResult(server_name=server_name, success=True)

        with patch("src.mcp_client.check_mcp_server", side_effect=mock_test):
            await check_all_mcp_servers(servers, timeout=42.0)

        assert captured_timeout == 42.0

    @pytest.mark.asyncio
    async def test_default_timeout(self):
        """Test that default timeout is 30 seconds."""
        servers = {"server1": {"command": "cmd"}}

        captured_timeout = None

        async def mock_test(server_name, config, timeout):
            nonlocal captured_timeout
            captured_timeout = timeout
            return MCPTestResult(server_name=server_name, success=True)

        with patch("src.mcp_client.check_mcp_server", side_effect=mock_test):
            await check_all_mcp_servers(servers)

        assert captured_timeout == 30.0
