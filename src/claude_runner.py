"""
Claude CLI wrapper module for running Claude commands with prompts.

This module provides a simple interface to execute the Claude CLI with streaming
JSON output and proper error handling.
"""

import contextlib
import json
import os
import re
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from src.integrations.telemetry import LLMMetrics
from src.logger import get_logger, log_message

logger = get_logger(__name__)


def validate_session_exists(session_id: str) -> bool:
    """Check if a Claude session file exists in any project directory.

    Claude stores session files at ~/.claude/projects/<path-hash>/sessions/<id>.jsonl
    where path-hash is derived from the working directory. When a repository is
    relocated, the path-hash changes and the session becomes inaccessible.

    This function searches across ALL project directories to find the session,
    which handles the case where kiln might be running from a different worktree
    than where the session was originally created.

    Args:
        session_id: The Claude session ID to validate

    Returns:
        True if session file exists anywhere in ~/.claude/projects/, False otherwise
    """
    claude_projects = Path.home() / ".claude" / "projects"
    if not claude_projects.exists():
        logger.debug(f"Claude projects directory not found: {claude_projects}")
        return False

    session_pattern = f"**/sessions/{session_id}.jsonl"
    matches = list(claude_projects.glob(session_pattern))

    if matches:
        logger.debug(f"Session {session_id[:8]}... found at: {matches[0]}")
        return True
    else:
        logger.debug(f"Session {session_id[:8]}... not found in any project directory")
        return False


@dataclass
class ClaudeResult:
    """Result from a Claude CLI execution."""

    response: str
    metrics: LLMMetrics | None = None


class ClaudeRunnerError(Exception):
    """Custom exception for Claude runner errors."""

    pass


class ClaudeTimeoutError(ClaudeRunnerError):
    """Exception raised when Claude execution times out."""

    pass


# Error patterns for user-friendly troubleshooting suggestions
# Each tuple is (regex_pattern, suggestion_message)
ERROR_PATTERNS = [
    (
        r"ANTHROPIC_API_KEY",
        "Remove ANTHROPIC_* environment variables: unset ANTHROPIC_API_KEY",
    ),
    (
        r"authentication|unauthorized|401|auth.*fail",
        "Re-authenticate with GitHub: gh auth login",
    ),
    (
        r"network|connection|timeout|ETIMEDOUT|ECONNREFUSED|ENOTFOUND",
        "Check network connectivity and try again",
    ),
    (
        r"rate.?limit|429|too many requests",
        "Rate limited - wait a few minutes before retrying",
    ),
    (
        r"not found|command not found|ENOENT",
        "Reinstall Claude Code: https://docs.anthropic.com/en/docs/claude-code/overview",
    ),
    (
        r"permission denied|EACCES",
        "Check file/directory permissions in the worktree",
    ),
    (
        r"model.*not.*available|invalid.*model",
        "Check that the specified model is available for your account",
    ),
    (
        r"context.*length|token.*limit|too.*long",
        "The prompt or response exceeded token limits - try breaking into smaller tasks",
    ),
]


def enhance_claude_error(original_error: str) -> str:
    """Enhance a Claude error message with user-friendly troubleshooting suggestions.

    Scans the original error message for known patterns and appends relevant
    "Next steps:" suggestions to help users resolve common issues.

    Args:
        original_error: The raw error message from Claude CLI

    Returns:
        The original error message with appended troubleshooting suggestions
        if any patterns matched, otherwise the original message unchanged.
    """
    suggestions = []

    for pattern, suggestion in ERROR_PATTERNS:
        if re.search(pattern, original_error, re.IGNORECASE) and suggestion not in suggestions:
            suggestions.append(suggestion)

    if suggestions:
        next_steps = "\n".join(f"  - {s}" for s in suggestions)
        return (
            f"{original_error}\n\n"
            f"Next steps:\n{next_steps}\n\n"
            f"For more help: https://docs.anthropic.com/en/docs/claude-code/troubleshooting"
        )

    return original_error


def run_claude(
    prompt: str,
    cwd: str,
    model: str | None = None,
    timeout: int = 1800,
    inactivity_timeout: int = 300,
    issue_context: str | None = None,  # noqa: ARG001
    resume_session: str | None = None,
    execution_stage: str | None = None,
    mcp_config_path: str | None = None,
    process_registrar: Callable[[subprocess.Popen[str]], None] | None = None,
) -> ClaudeResult:
    """
    Run the Claude CLI with a given prompt and return the response with metrics.

    This function executes the Claude CLI with streaming JSON output format,
    processes the stream to extract the response text and usage metrics,
    and handles errors appropriately.

    Args:
        prompt: The prompt to send to Claude via stdin
        cwd: The working directory in which to execute the Claude command
        model: Claude model to use (e.g., "haiku", "sonnet", "opus"). If None, uses CLI default.
        timeout: Maximum execution time in seconds (default: 1800 = 30 minutes)
        inactivity_timeout: Timeout if no output for this many seconds (default: 300 = 5 minutes)
        issue_context: Issue reference for logging (e.g., "owner/repo#123")
        resume_session: Optional session ID to resume. If provided, adds --resume flag.
        execution_stage: Workflow stage name for logging (e.g., "research", "plan", "implement")
        mcp_config_path: Path to MCP configuration file. If provided, adds --mcp-config flag.
        process_registrar: Optional callback invoked immediately after subprocess spawn.
            Called with the Popen object, enabling external tracking/termination.

    Returns:
        ClaudeResult containing response text and optional LLMMetrics

    Raises:
        ClaudeTimeoutError: If execution exceeds the timeout duration
        ClaudeRunnerError: If Claude process fails or returns an error
        FileNotFoundError: If the cwd directory does not exist
        subprocess.SubprocessError: For other subprocess-related errors

    Example:
        >>> result = run_claude("What is 2+2?", "/path/to/project")
        >>> print(result.response)
        "4"
    """
    log_message(logger, "Running Claude CLI with prompt", prompt)
    logger.debug(f"Working directory: {cwd}")
    logger.debug(f"Timeout: {timeout}s total, {inactivity_timeout}s inactivity")
    if resume_session:
        logger.info(f"Attempting session resume: {resume_session[:8]}...")
    else:
        logger.debug("Starting new session (no resume)")

    # Build the command
    cmd = [
        "claude",
        "--print",
        "--output-format",
        "stream-json",
        "--dangerously-skip-permissions",
        "--verbose",
    ]

    if model:
        cmd.extend(["--model", model])

    if resume_session:
        cmd.extend(["--resume", resume_session])

    if mcp_config_path:
        cmd.extend(["--mcp-config", mcp_config_path])

    try:
        # Start the process with stdin as PIPE for prompt input
        logger.debug(f"Executing command: {' '.join(cmd)}")

        # Build environment for Claude subprocess
        env = {**os.environ}

        # Auth handled via keyring (gh auth login stores token there)
        # No env var injection needed - Claude inherits user's keyring access

        # Claude runs as the user and inherits ~/.config/gh/hosts.yml
        # All gh commands use full URLs (https://hostname/owner/repo/issues/N)
        # so gh auto-detects which host to authenticate against from the URL

        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            text=True,
            bufsize=1,  # Line buffered
            env=env,
        )

        # Register process immediately for external termination capability
        if process_registrar:
            process_registrar(process)

        # Send the prompt to stdin and close it
        logger.debug("Sending prompt to Claude via stdin")
        assert process.stdin is not None, "stdin should be available"
        process.stdin.write(prompt)
        process.stdin.close()

        # Track timeout
        start_time = time.time()
        last_activity_time = time.time()
        response_parts = []
        non_json_output = []  # Capture non-JSON output for error reporting
        llm_metrics: LLMMetrics | None = None

        # Read stdout line by line
        logger.debug("Reading streaming JSON output")
        assert process.stdout is not None, "stdout should be available"
        while True:
            current_time = time.time()

            # Check total timeout
            if current_time - start_time > timeout:
                process.kill()
                logger.error(f"Claude execution timed out after {timeout} seconds (total)")
                raise ClaudeTimeoutError(
                    f"Claude execution exceeded total timeout of {timeout} seconds"
                )

            # Check inactivity timeout
            if current_time - last_activity_time > inactivity_timeout:
                process.kill()
                logger.error(
                    f"Claude execution timed out after {inactivity_timeout} seconds of inactivity"
                )
                raise ClaudeTimeoutError(
                    f"Claude execution exceeded inactivity timeout of {inactivity_timeout} seconds"
                )

            # Read a line from stdout
            line = process.stdout.readline()

            # If no more output and process has finished, break
            if not line and process.poll() is not None:
                break

            # Skip empty lines
            if not line or not line.strip():
                continue

            # Got output, reset inactivity timer
            last_activity_time = time.time()

            # Parse JSON line
            try:
                data = json.loads(line.strip())
                logger.debug(f"Received JSON object: {data.get('type', 'unknown')}")

                # Extract text from different event types
                # Claude CLI stream-json format sends: system, assistant, result
                if isinstance(data, dict):
                    # Check for result type with "result" field (final response)
                    if data.get("type") == "result" and "result" in data:
                        response_parts.append(data["result"])
                        log_message(logger, "Extracted result", data["result"])

                        # Extract metrics from result event
                        usage = data.get("usage", {})
                        llm_metrics = LLMMetrics(
                            duration_ms=data.get("duration_ms", 0),
                            duration_api_ms=data.get("duration_api_ms", 0),
                            total_cost_usd=data.get("total_cost_usd", 0.0),
                            num_turns=data.get("num_turns", 0),
                            session_id=data.get("session_id", ""),
                            model_usage=data.get("modelUsage", {}),
                            input_tokens=usage.get("input_tokens", 0),
                            output_tokens=usage.get("output_tokens", 0),
                            cache_creation_tokens=usage.get("cache_creation_input_tokens", 0),
                            cache_read_tokens=usage.get("cache_read_input_tokens", 0),
                        )
                        # Log cache stats at INFO level for resumption debugging
                        cache_read = llm_metrics.cache_read_tokens
                        cache_created = llm_metrics.cache_creation_tokens
                        if cache_read > 0:
                            logger.info(f"Session cache HIT: {cache_read} tokens read from cache")
                        elif cache_created > 0:
                            logger.info(
                                f"Session cache MISS: {cache_created} tokens cached (new session or expired)"
                            )
                        logger.debug(
                            f"Extracted metrics: tokens={llm_metrics.input_tokens}/"
                            f"{llm_metrics.output_tokens}, cost=${llm_metrics.total_cost_usd:.4f}"
                        )

                    # Check for assistant message with content array
                    elif data.get("type") == "assistant" and "message" in data:
                        message = data["message"]
                        if "content" in message and isinstance(message["content"], list):
                            for item in message["content"]:
                                if isinstance(item, dict) and item.get("type") == "text":
                                    response_parts.append(item["text"])
                                    log_message(logger, "Extracted assistant text", item["text"])

                    # Check for error messages
                    elif data.get("type") == "error":
                        error_msg = data.get("message", data.get("text", "Unknown error"))
                        logger.error(f"Claude returned error: {error_msg}")
                        enhanced_error = enhance_claude_error(f"Claude error: {error_msg}")
                        raise ClaudeRunnerError(enhanced_error)

            except json.JSONDecodeError as e:
                # Capture non-JSON output for error reporting (e.g., early CLI errors)
                logger.warning(f"Failed to parse JSON line: {line[:100]}... Error: {e}")
                non_json_output.append(line.strip())
                # Continue processing, don't fail on partial JSON
                continue

        # Wait for process to complete
        return_code = process.wait(timeout=5)

        # Read stderr before closing (needed for error messages)
        stderr_output = ""
        if process.stderr:
            with contextlib.suppress(Exception):
                stderr_output = process.stderr.read()

        # Explicitly close pipes to prevent FD leaks
        try:
            if process.stdout:
                process.stdout.close()
            if process.stderr:
                process.stderr.close()
        except Exception as e:
            logger.warning(f"Error closing Claude process pipes: {e}")

        # Check return code
        if return_code != 0:
            logger.error(f"Claude process exited with code {return_code}")
            if stderr_output:
                logger.error(f"Stderr: {stderr_output}")
            if non_json_output:
                logger.error(f"Non-JSON stdout: {non_json_output}")
            # Combine stderr and non-JSON stdout for complete error context
            error_details = stderr_output.strip()
            if non_json_output:
                non_json_str = "\n".join(non_json_output)
                if error_details:
                    error_details = f"{error_details}\nStdout: {non_json_str}"
                else:
                    error_details = non_json_str
            raw_error = f"Claude process failed with exit code {return_code}: {error_details}"
            enhanced_error = enhance_claude_error(raw_error)
            raise ClaudeRunnerError(enhanced_error)

        # Combine response parts
        final_response = "".join(response_parts)

        if not final_response:
            logger.warning("No response text extracted from Claude output")
            if stderr_output:
                logger.error(f"Stderr: {stderr_output}")
            enhanced_error = enhance_claude_error("No response received from Claude")
            raise ClaudeRunnerError(enhanced_error)

        stage_info = f" {execution_stage}" if execution_stage else ""
        logger.info(
            f"Claude{stage_info} execution completed successfully. Response length: {len(final_response)}"
        )
        return ClaudeResult(response=final_response, metrics=llm_metrics)

    except FileNotFoundError as e:
        logger.error(f"Command or directory not found: {e}")
        enhanced_error = enhance_claude_error(f"Failed to execute Claude CLI: {e}")
        raise ClaudeRunnerError(enhanced_error) from e

    except subprocess.TimeoutExpired as e:
        logger.error(f"Process wait timeout: {e}")
        raise ClaudeTimeoutError("Claude process timed out during cleanup") from e

    except Exception as e:
        # Catch any other unexpected errors
        if isinstance(e, (ClaudeRunnerError, ClaudeTimeoutError)):
            raise
        logger.error(f"Unexpected error running Claude: {e}", exc_info=True)
        enhanced_error = enhance_claude_error(f"Unexpected error: {e}")
        raise ClaudeRunnerError(enhanced_error) from e
