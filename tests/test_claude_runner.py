"""Unit tests for the claude_runner module."""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.claude_runner import (
    ClaudeResult,
    ClaudeRunnerError,
    ClaudeTimeoutError,
    run_claude,
)
from src.integrations.telemetry import LLMMetrics


@pytest.mark.unit
class TestClaudeResult:
    """Tests for ClaudeResult dataclass."""

    def test_result_with_metrics(self):
        """Test creating ClaudeResult with response and metrics."""
        metrics = LLMMetrics(
            duration_ms=1000,
            duration_api_ms=900,
            total_cost_usd=0.05,
            input_tokens=100,
            output_tokens=50,
            cache_creation_tokens=0,
            cache_read_tokens=0,
            num_turns=1,
            session_id="test-session-123",
            model_usage={"claude-sonnet": {"inputTokens": 100, "outputTokens": 50}},
        )
        result = ClaudeResult(response="Hello, world!", metrics=metrics)

        assert result.response == "Hello, world!"
        assert result.metrics is not None
        assert result.metrics.duration_ms == 1000
        assert result.metrics.total_cost_usd == 0.05
        assert result.metrics.input_tokens == 100
        assert result.metrics.output_tokens == 50
        assert result.metrics.session_id == "test-session-123"

    def test_result_without_metrics(self):
        """Test creating ClaudeResult with response only (default None metrics)."""
        result = ClaudeResult(response="Just a response")

        assert result.response == "Just a response"
        assert result.metrics is None

    def test_result_empty_response(self):
        """Test ClaudeResult with empty response string."""
        result = ClaudeResult(response="", metrics=None)

        assert result.response == ""
        assert result.metrics is None


@pytest.mark.unit
class TestClaudeRunnerExceptions:
    """Tests for ClaudeRunnerError and ClaudeTimeoutError exceptions."""

    def test_runner_error_message(self):
        """Test ClaudeRunnerError stores and displays message correctly."""
        error = ClaudeRunnerError("Something went wrong")

        assert str(error) == "Something went wrong"

    def test_runner_error_can_be_raised_and_caught(self):
        """Test ClaudeRunnerError can be raised and caught."""
        with pytest.raises(ClaudeRunnerError, match="Custom error message"):
            raise ClaudeRunnerError("Custom error message")

    def test_timeout_error_message(self):
        """Test ClaudeTimeoutError stores and displays message correctly."""
        error = ClaudeTimeoutError("Operation timed out after 60 seconds")

        assert str(error) == "Operation timed out after 60 seconds"

    def test_timeout_error_can_be_caught_specifically(self):
        """Test ClaudeTimeoutError can be caught specifically."""
        with pytest.raises(ClaudeTimeoutError, match="Specific timeout"):
            raise ClaudeTimeoutError("Specific timeout")


@pytest.mark.unit
class TestRunClaude:
    """Tests for run_claude function."""

    def _create_mock_process(
        self,
        stdout_lines,
        return_code=0,
        stderr_output="",
    ):
        """Helper to create a mock process with specified output."""
        mock_process = MagicMock()
        mock_process.stdin = MagicMock()
        mock_process.stdout = MagicMock()
        mock_process.stderr = MagicMock()

        # Track line index for readline
        line_index = [0]

        def readline():
            if line_index[0] < len(stdout_lines):
                line = stdout_lines[line_index[0]]
                line_index[0] += 1
                return line
            return ""

        mock_process.stdout.readline = readline
        mock_process.stderr.read.return_value = stderr_output

        # poll() returns None while running, then return_code when done
        poll_values = [None] * len(stdout_lines) + [return_code]
        mock_process.poll.side_effect = poll_values

        mock_process.wait.return_value = return_code

        return mock_process

    def test_run_claude_success(self, mock_claude_subprocess, tmp_path):
        """Test run_claude returns successful result with response text."""
        result_event = json.dumps(
            {
                "type": "result",
                "result": "This is the response from Claude.",
                "usage": {"input_tokens": 100, "output_tokens": 50},
                "duration_ms": 1500,
                "total_cost_usd": 0.02,
                "num_turns": 1,
                "session_id": "session-abc-123",
            }
        )
        mock_process = self._create_mock_process([result_event + "\n"])
        mock_claude_subprocess.return_value = mock_process

        result = run_claude("What is 2+2?", str(tmp_path))

        assert result.response == "This is the response from Claude."
        assert result.metrics is not None
        assert result.metrics.input_tokens == 100
        assert result.metrics.output_tokens == 50
        assert result.metrics.duration_ms == 1500
        assert result.metrics.session_id == "session-abc-123"
        mock_process.stdin.write.assert_called_once_with("What is 2+2?")
        mock_process.stdin.close.assert_called_once()

    def test_run_claude_with_model_flag(self, mock_claude_subprocess, tmp_path):
        """Test run_claude passes model flag to CLI."""
        result_event = json.dumps({"type": "result", "result": "Response"})
        mock_process = self._create_mock_process([result_event + "\n"])
        mock_claude_subprocess.return_value = mock_process

        run_claude("Prompt", str(tmp_path), model="opus")

        # Check that --model opus was included in the command
        call_args = mock_claude_subprocess.call_args
        cmd = call_args[0][0]
        assert "--model" in cmd
        assert "opus" in cmd

    def test_run_claude_with_resume_session(self, mock_claude_subprocess, tmp_path):
        """Test run_claude passes resume session flag to CLI."""
        result_event = json.dumps({"type": "result", "result": "Resumed response"})
        mock_process = self._create_mock_process([result_event + "\n"])
        mock_claude_subprocess.return_value = mock_process

        run_claude("Continue the task", str(tmp_path), resume_session="session-to-resume")

        call_args = mock_claude_subprocess.call_args
        cmd = call_args[0][0]
        assert "--resume" in cmd
        assert "session-to-resume" in cmd

    def test_run_claude_timeout_total(self, mock_claude_subprocess, tmp_path):
        """Test run_claude raises ClaudeTimeoutError on total timeout."""
        mock_process = MagicMock()
        mock_process.stdin = MagicMock()
        mock_process.stdout = MagicMock()

        # Simulate very slow output by returning empty strings indefinitely
        # We'll mock time.time to simulate elapsed time
        mock_process.stdout.readline.return_value = ""
        mock_process.poll.return_value = None

        mock_claude_subprocess.return_value = mock_process

        with patch("src.claude_runner.time") as mock_time:
            # First call is start_time, second is current_time check
            # Make it appear that timeout has exceeded
            mock_time.time.side_effect = [0, 0, 2000]  # start, last_activity, current (2000s elapsed)

            with pytest.raises(ClaudeTimeoutError, match="exceeded total timeout"):
                run_claude("Prompt", str(tmp_path), timeout=1800)

        mock_process.kill.assert_called_once()

    def test_run_claude_timeout_inactivity(self, mock_claude_subprocess, tmp_path):
        """Test run_claude raises ClaudeTimeoutError on inactivity timeout."""
        mock_process = MagicMock()
        mock_process.stdin = MagicMock()
        mock_process.stdout = MagicMock()
        mock_process.stdout.readline.return_value = ""
        mock_process.poll.return_value = None

        mock_claude_subprocess.return_value = mock_process

        with patch("src.claude_runner.time") as mock_time:
            # start_time, last_activity_time, current_time
            # Total timeout not exceeded but inactivity exceeded
            mock_time.time.side_effect = [0, 0, 400]  # 400s > 300s inactivity timeout

            with pytest.raises(ClaudeTimeoutError, match="exceeded inactivity timeout"):
                run_claude("Prompt", str(tmp_path), inactivity_timeout=300)

        mock_process.kill.assert_called_once()

    def test_run_claude_nonzero_exit(self, mock_claude_subprocess, tmp_path):
        """Test run_claude raises ClaudeRunnerError on non-zero exit code."""
        result_event = json.dumps({"type": "result", "result": "Partial response"})
        mock_process = self._create_mock_process(
            [result_event + "\n"],
            return_code=1,
            stderr_output="Claude CLI error: authentication failed",
        )
        mock_claude_subprocess.return_value = mock_process

        with pytest.raises(ClaudeRunnerError, match="failed with exit code 1"):
            run_claude("Prompt", str(tmp_path))

    def test_run_claude_nonzero_exit_with_nonjson_stdout(self, mock_claude_subprocess, tmp_path):
        """Test run_claude captures non-JSON stdout in error when process fails."""
        # Simulate Claude outputting an error message before JSON stream
        mock_process = self._create_mock_process(
            ["Error: Something went wrong before JSON output\n"],
            return_code=1,
            stderr_output="",
        )
        mock_claude_subprocess.return_value = mock_process

        with pytest.raises(ClaudeRunnerError, match="Something went wrong before JSON output"):
            run_claude("Prompt", str(tmp_path))

    def test_run_claude_nonzero_exit_combines_stderr_and_nonjson_stdout(
        self, mock_claude_subprocess, tmp_path
    ):
        """Test run_claude combines stderr and non-JSON stdout in error message."""
        mock_process = self._create_mock_process(
            ["CLI startup error\n"],
            return_code=1,
            stderr_output="stderr content",
        )
        mock_claude_subprocess.return_value = mock_process

        with pytest.raises(ClaudeRunnerError) as exc_info:
            run_claude("Prompt", str(tmp_path))

        error_msg = str(exc_info.value)
        assert "stderr content" in error_msg
        assert "CLI startup error" in error_msg

    def test_run_claude_error_event(self, mock_claude_subprocess, tmp_path):
        """Test run_claude raises ClaudeRunnerError when error event is received."""
        error_event = json.dumps({"type": "error", "message": "Rate limit exceeded"})
        mock_process = self._create_mock_process([error_event + "\n"])
        mock_claude_subprocess.return_value = mock_process

        with pytest.raises(ClaudeRunnerError, match="Claude error: Rate limit exceeded"):
            run_claude("Prompt", str(tmp_path))

    def test_run_claude_extracts_metrics(self, mock_claude_subprocess, tmp_path):
        """Test run_claude extracts all metrics fields from result event."""
        result_event = json.dumps(
            {
                "type": "result",
                "result": "Response with full metrics",
                "usage": {
                    "input_tokens": 500,
                    "output_tokens": 200,
                    "cache_creation_input_tokens": 100,
                    "cache_read_input_tokens": 50,
                },
                "duration_ms": 5000,
                "duration_api_ms": 4500,
                "total_cost_usd": 0.15,
                "num_turns": 3,
                "session_id": "full-metrics-session",
                "modelUsage": {
                    "claude-opus": {"inputTokens": 500, "outputTokens": 200},
                },
            }
        )
        mock_process = self._create_mock_process([result_event + "\n"])
        mock_claude_subprocess.return_value = mock_process

        result = run_claude("Prompt with metrics", str(tmp_path))

        assert result.metrics is not None
        assert result.metrics.duration_ms == 5000
        assert result.metrics.duration_api_ms == 4500
        assert result.metrics.total_cost_usd == 0.15
        assert result.metrics.num_turns == 3
        assert result.metrics.session_id == "full-metrics-session"
        assert result.metrics.input_tokens == 500
        assert result.metrics.output_tokens == 200
        assert result.metrics.cache_creation_tokens == 100
        assert result.metrics.cache_read_tokens == 50
        assert "claude-opus" in result.metrics.model_usage

    def test_run_claude_no_response_raises_error(self, mock_claude_subprocess, tmp_path):
        """Test run_claude raises error when no response text is extracted."""
        # Send only a system message, no result
        system_event = json.dumps({"type": "system", "message": "Starting..."})
        mock_process = self._create_mock_process([system_event + "\n"])
        mock_claude_subprocess.return_value = mock_process

        with pytest.raises(ClaudeRunnerError, match="No response received from Claude"):
            run_claude("Prompt", str(tmp_path))

    def test_run_claude_handles_malformed_json(self, mock_claude_subprocess, tmp_path):
        """Test run_claude gracefully handles malformed JSON lines."""
        lines = [
            "not valid json\n",
            "{incomplete: json\n",
            json.dumps({"type": "result", "result": "Valid response"}) + "\n",
        ]
        mock_process = self._create_mock_process(lines)
        mock_claude_subprocess.return_value = mock_process

        # Should not raise, should skip malformed lines and extract valid result
        result = run_claude("Prompt", str(tmp_path))

        assert result.response == "Valid response"

    def test_run_claude_directory_not_found(self, mock_claude_subprocess, tmp_path):
        """Test run_claude raises error for non-existent directory."""
        mock_claude_subprocess.side_effect = FileNotFoundError("No such directory")

        with pytest.raises(ClaudeRunnerError, match="Failed to execute Claude CLI"):
            run_claude("Prompt", "/nonexistent/directory")

    def test_run_claude_with_telemetry_enabled(self, mock_claude_subprocess, tmp_path):
        """Test run_claude sets CLAUDE_CODE_ENABLE_TELEMETRY env var when enabled."""
        result_event = json.dumps({"type": "result", "result": "Response"})
        mock_process = self._create_mock_process([result_event + "\n"])
        mock_claude_subprocess.return_value = mock_process

        run_claude("Prompt", str(tmp_path), enable_telemetry=True)

        call_args = mock_claude_subprocess.call_args
        env = call_args[1].get("env", {})
        assert env.get("CLAUDE_CODE_ENABLE_TELEMETRY") == "1"

    def test_run_claude_with_telemetry_disabled(self, mock_claude_subprocess, tmp_path):
        """Test run_claude does not set telemetry env var when disabled."""
        result_event = json.dumps({"type": "result", "result": "Response"})
        mock_process = self._create_mock_process([result_event + "\n"])
        mock_claude_subprocess.return_value = mock_process

        run_claude("Prompt", str(tmp_path), enable_telemetry=False)

        call_args = mock_claude_subprocess.call_args
        env = call_args[1].get("env", {})
        assert env.get("CLAUDE_CODE_ENABLE_TELEMETRY") != "1"

    def test_run_claude_with_mcp_config_path(self, mock_claude_subprocess, tmp_path):
        """Test run_claude passes --mcp-config flag to CLI when path is provided."""
        result_event = json.dumps({"type": "result", "result": "Response with MCP"})
        mock_process = self._create_mock_process([result_event + "\n"])
        mock_claude_subprocess.return_value = mock_process

        mcp_path = str(tmp_path / ".mcp.kiln.json")
        run_claude("Prompt", str(tmp_path), mcp_config_path=mcp_path)

        call_args = mock_claude_subprocess.call_args
        cmd = call_args[0][0]
        assert "--mcp-config" in cmd
        assert mcp_path in cmd
        # Verify --mcp-config appears before the path
        mcp_config_index = cmd.index("--mcp-config")
        assert cmd[mcp_config_index + 1] == mcp_path

    def test_run_claude_without_mcp_config_path(self, mock_claude_subprocess, tmp_path):
        """Test run_claude does not include --mcp-config flag when path is not provided."""
        result_event = json.dumps({"type": "result", "result": "Response"})
        mock_process = self._create_mock_process([result_event + "\n"])
        mock_claude_subprocess.return_value = mock_process

        run_claude("Prompt", str(tmp_path))

        call_args = mock_claude_subprocess.call_args
        cmd = call_args[0][0]
        assert "--mcp-config" not in cmd

    def test_run_claude_with_mcp_config_path_none(self, mock_claude_subprocess, tmp_path):
        """Test run_claude does not include --mcp-config flag when path is explicitly None."""
        result_event = json.dumps({"type": "result", "result": "Response"})
        mock_process = self._create_mock_process([result_event + "\n"])
        mock_claude_subprocess.return_value = mock_process

        run_claude("Prompt", str(tmp_path), mcp_config_path=None)

        call_args = mock_claude_subprocess.call_args
        cmd = call_args[0][0]
        assert "--mcp-config" not in cmd


@pytest.mark.unit
class TestRunClaudeJsonStreamParsing:
    """Tests for JSON stream parsing in run_claude."""

    def _create_mock_process(self, stdout_lines, return_code=0):
        """Helper to create a mock process with specified output."""
        mock_process = MagicMock()
        mock_process.stdin = MagicMock()
        mock_process.stdout = MagicMock()
        mock_process.stderr = MagicMock()
        mock_process.stderr.read.return_value = ""

        line_index = [0]

        def readline():
            if line_index[0] < len(stdout_lines):
                line = stdout_lines[line_index[0]]
                line_index[0] += 1
                return line
            return ""

        mock_process.stdout.readline = readline
        poll_values = [None] * len(stdout_lines) + [return_code]
        mock_process.poll.side_effect = poll_values
        mock_process.wait.return_value = return_code

        return mock_process

    def test_parses_result_event(self, mock_claude_subprocess, tmp_path):
        """Test parsing result event type extracts response."""
        result_event = json.dumps(
            {"type": "result", "result": "Final answer: 42"}
        )
        mock_process = self._create_mock_process([result_event + "\n"])
        mock_claude_subprocess.return_value = mock_process

        result = run_claude("Prompt", str(tmp_path))

        assert result.response == "Final answer: 42"

    def test_parses_assistant_event_with_text_content(self, mock_claude_subprocess, tmp_path):
        """Test parsing assistant event with text content array."""
        assistant_event = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "text", "text": "First part. "},
                        {"type": "text", "text": "Second part."},
                    ]
                },
            }
        )
        result_event = json.dumps({"type": "result", "result": "Final"})
        mock_process = self._create_mock_process(
            [assistant_event + "\n", result_event + "\n"]
        )
        mock_claude_subprocess.return_value = mock_process

        result = run_claude("Prompt", str(tmp_path))

        # Both assistant text parts and result should be combined
        assert "First part." in result.response
        assert "Second part." in result.response

    def test_parses_error_event(self, mock_claude_subprocess, tmp_path):
        """Test parsing error event raises ClaudeRunnerError."""
        error_event = json.dumps(
            {"type": "error", "message": "API connection failed"}
        )
        mock_process = self._create_mock_process([error_event + "\n"])
        mock_claude_subprocess.return_value = mock_process

        with pytest.raises(ClaudeRunnerError, match="Claude error: API connection failed"):
            run_claude("Prompt", str(tmp_path))

    def test_parses_error_event_with_text_field(self, mock_claude_subprocess, tmp_path):
        """Test parsing error event that uses 'text' instead of 'message' field."""
        error_event = json.dumps(
            {"type": "error", "text": "Alternative error format"}
        )
        mock_process = self._create_mock_process([error_event + "\n"])
        mock_claude_subprocess.return_value = mock_process

        with pytest.raises(ClaudeRunnerError, match="Claude error: Alternative error format"):
            run_claude("Prompt", str(tmp_path))

    def test_skips_empty_lines(self, mock_claude_subprocess, tmp_path):
        """Test that empty lines are skipped during parsing."""
        lines = [
            "\n",
            "   \n",
            json.dumps({"type": "result", "result": "Response after empty lines"}) + "\n",
        ]
        mock_process = self._create_mock_process(lines)
        mock_claude_subprocess.return_value = mock_process

        result = run_claude("Prompt", str(tmp_path))

        assert result.response == "Response after empty lines"

    def test_skips_unknown_event_types(self, mock_claude_subprocess, tmp_path):
        """Test that unknown event types are ignored without error."""
        lines = [
            json.dumps({"type": "system", "content": "Initializing..."}) + "\n",
            json.dumps({"type": "progress", "percent": 50}) + "\n",
            json.dumps({"type": "result", "result": "Final response"}) + "\n",
        ]
        mock_process = self._create_mock_process(lines)
        mock_claude_subprocess.return_value = mock_process

        result = run_claude("Prompt", str(tmp_path))

        assert result.response == "Final response"

    def test_handles_non_dict_json_raises_error(self, mock_claude_subprocess, tmp_path):
        """Test that non-dict JSON values raise an error (current behavior)."""
        lines = [
            '"just a string"\n',
        ]
        mock_process = self._create_mock_process(lines)
        mock_claude_subprocess.return_value = mock_process

        # Non-dict JSON causes an error since the code tries to call .get() on it
        # before checking isinstance(data, dict)
        with pytest.raises(ClaudeRunnerError, match="Unexpected error"):
            run_claude("Prompt", str(tmp_path))
