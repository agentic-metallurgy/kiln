"""Tests for the telemetry module."""

import pytest

from src.telemetry import LLMMetrics


@pytest.mark.unit
class TestLLMMetrics:
    """Unit tests for LLMMetrics dataclass."""

    def test_default_values(self):
        """Test LLMMetrics has correct default values."""
        metrics = LLMMetrics()

        assert metrics.duration_ms == 0
        assert metrics.duration_api_ms == 0
        assert metrics.total_cost_usd == 0.0
        assert metrics.input_tokens == 0
        assert metrics.output_tokens == 0
        assert metrics.cache_creation_tokens == 0
        assert metrics.cache_read_tokens == 0
        assert metrics.num_turns == 0
        assert metrics.session_id == ""
        assert metrics.model_usage == {}

    def test_custom_values(self):
        """Test LLMMetrics with custom values."""
        model_usage = {
            "claude-opus-4-5-20251101": {
                "inputTokens": 1000,
                "outputTokens": 200,
                "costUSD": 0.05,
            }
        }
        metrics = LLMMetrics(
            duration_ms=5000,
            duration_api_ms=4000,
            total_cost_usd=0.15,
            input_tokens=1500,
            output_tokens=300,
            cache_creation_tokens=500,
            cache_read_tokens=100,
            num_turns=1,
            session_id="test-session-123",
            model_usage=model_usage,
        )

        assert metrics.duration_ms == 5000
        assert metrics.duration_api_ms == 4000
        assert metrics.total_cost_usd == 0.15
        assert metrics.input_tokens == 1500
        assert metrics.output_tokens == 300
        assert metrics.cache_creation_tokens == 500
        assert metrics.cache_read_tokens == 100
        assert metrics.num_turns == 1
        assert metrics.session_id == "test-session-123"
        assert metrics.model_usage == model_usage


@pytest.mark.unit
class TestGetGitVersion:
    """Unit tests for get_git_version function."""

    def test_returns_string(self):
        """Test get_git_version returns a non-empty string."""
        from src.telemetry import get_git_version

        version = get_git_version()
        assert isinstance(version, str)
        assert len(version) > 0

    def test_returns_unknown_when_git_fails(self, monkeypatch):
        """Test get_git_version returns 'unknown' when git command fails."""
        import subprocess

        from src.telemetry import get_git_version

        def mock_run(*args, **kwargs):
            raise subprocess.CalledProcessError(1, "git")

        monkeypatch.setattr(subprocess, "run", mock_run)
        assert get_git_version() == "unknown"

    def test_returns_unknown_when_git_not_found(self, monkeypatch):
        """Test get_git_version returns 'unknown' when git is not installed."""
        import subprocess

        from src.telemetry import get_git_version

        def mock_run(*args, **kwargs):
            raise FileNotFoundError("git not found")

        monkeypatch.setattr(subprocess, "run", mock_run)
        assert get_git_version() == "unknown"
