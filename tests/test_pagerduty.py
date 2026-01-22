"""Unit tests for the PagerDuty module.

Tests verify:
- Module initialization and state management
- API payload construction (dedup key, severity, custom details)
- Error handling for HTTP failures (timeouts, 4xx, 5xx)
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from src import pagerduty


@pytest.fixture(autouse=True)
def reset_pagerduty_state():
    """Reset PagerDuty module state before and after each test."""
    pagerduty.reset_pagerduty()
    yield
    pagerduty.reset_pagerduty()


@pytest.mark.unit
class TestInitPagerduty:
    """Tests for init_pagerduty() function."""

    def test_init_sets_module_state_correctly(self):
        """Test init_pagerduty() sets module state correctly."""
        pagerduty.init_pagerduty("test-routing-key")

        assert pagerduty._initialized is True
        assert pagerduty._routing_key == "test-routing-key"

    def test_init_is_idempotent(self):
        """Test calling init_pagerduty() multiple times is safe."""
        pagerduty.init_pagerduty("first-key")
        pagerduty.init_pagerduty("second-key")

        # Should still have first key (idempotent)
        assert pagerduty._routing_key == "first-key"
        assert pagerduty._initialized is True

    def test_init_with_none_is_no_op(self):
        """Test init_pagerduty() with None is no-op."""
        pagerduty.init_pagerduty(None)

        assert pagerduty._initialized is False
        assert pagerduty._routing_key is None

    def test_init_with_empty_string_is_no_op(self):
        """Test init_pagerduty() with empty string is no-op."""
        pagerduty.init_pagerduty("")

        assert pagerduty._initialized is False
        assert pagerduty._routing_key is None

    def test_init_logs_info_on_success(self):
        """Test init_pagerduty() logs info message on successful init."""
        with patch.object(pagerduty, "logger") as mock_logger:
            pagerduty.init_pagerduty("test-key")

            mock_logger.info.assert_called_once_with(
                "PagerDuty initialized for hibernation alerts"
            )

    def test_init_logs_debug_when_no_key(self):
        """Test init_pagerduty() logs debug message when no routing key."""
        with patch.object(pagerduty, "logger") as mock_logger:
            pagerduty.init_pagerduty(None)

            mock_logger.debug.assert_called_once_with(
                "PagerDuty not configured (no routing key)"
            )


@pytest.mark.unit
class TestTriggerHibernationAlert:
    """Tests for trigger_hibernation_alert() function."""

    def test_trigger_returns_false_when_not_initialized(self):
        """Test trigger_hibernation_alert() returns False when not initialized."""
        result = pagerduty.trigger_hibernation_alert(
            "test reason", ["https://github.com/orgs/test/projects/1"]
        )

        assert result is False

    def test_trigger_makes_correct_api_call(self):
        """Test trigger_hibernation_alert() makes correct API call."""
        pagerduty.init_pagerduty("test-routing-key")

        with patch("src.pagerduty.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            result = pagerduty.trigger_hibernation_alert(
                "GitHub API unreachable",
                ["https://github.com/orgs/test/projects/1"],
            )

            assert result is True
            mock_post.assert_called_once()

            # Verify the API call details
            call_args = mock_post.call_args
            assert call_args[0][0] == pagerduty.PAGERDUTY_EVENTS_URL
            assert call_args[1]["timeout"] == 10

            payload = call_args[1]["json"]
            assert payload["routing_key"] == "test-routing-key"
            assert payload["event_action"] == "trigger"
            assert payload["dedup_key"] == pagerduty.HIBERNATION_DEDUP_KEY
            assert payload["payload"]["summary"] == "Kiln daemon entered hibernation: GitHub API unreachable"
            assert payload["payload"]["severity"] == "warning"
            assert payload["payload"]["source"] == "kiln-daemon"
            assert payload["payload"]["custom_details"]["reason"] == "GitHub API unreachable"
            assert payload["payload"]["custom_details"]["project_urls"] == [
                "https://github.com/orgs/test/projects/1"
            ]
            assert payload["payload"]["custom_details"]["status"] == "hibernating"

    def test_trigger_handles_http_timeout_gracefully(self):
        """Test trigger_hibernation_alert() handles timeout gracefully."""
        pagerduty.init_pagerduty("test-routing-key")

        with patch("src.pagerduty.requests.post") as mock_post:
            mock_post.side_effect = requests.Timeout("Connection timed out")

            result = pagerduty.trigger_hibernation_alert(
                "test reason", ["https://github.com/orgs/test/projects/1"]
            )

            assert result is False

    def test_trigger_handles_http_connection_error_gracefully(self):
        """Test trigger_hibernation_alert() handles connection error gracefully."""
        pagerduty.init_pagerduty("test-routing-key")

        with patch("src.pagerduty.requests.post") as mock_post:
            mock_post.side_effect = requests.ConnectionError("Connection refused")

            result = pagerduty.trigger_hibernation_alert(
                "test reason", ["https://github.com/orgs/test/projects/1"]
            )

            assert result is False

    def test_trigger_handles_http_4xx_error_gracefully(self):
        """Test trigger_hibernation_alert() handles 4xx HTTP errors gracefully."""
        pagerduty.init_pagerduty("test-routing-key")

        with patch("src.pagerduty.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.raise_for_status.side_effect = requests.HTTPError(
                "400 Bad Request"
            )
            mock_post.return_value = mock_response

            result = pagerduty.trigger_hibernation_alert(
                "test reason", ["https://github.com/orgs/test/projects/1"]
            )

            assert result is False

    def test_trigger_handles_http_5xx_error_gracefully(self):
        """Test trigger_hibernation_alert() handles 5xx HTTP errors gracefully."""
        pagerduty.init_pagerduty("test-routing-key")

        with patch("src.pagerduty.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.raise_for_status.side_effect = requests.HTTPError(
                "500 Internal Server Error"
            )
            mock_post.return_value = mock_response

            result = pagerduty.trigger_hibernation_alert(
                "test reason", ["https://github.com/orgs/test/projects/1"]
            )

            assert result is False

    def test_trigger_logs_warning_on_failure(self):
        """Test trigger_hibernation_alert() logs warning on failure."""
        pagerduty.init_pagerduty("test-routing-key")

        with (
            patch("src.pagerduty.requests.post") as mock_post,
            patch.object(pagerduty, "logger") as mock_logger,
        ):
            mock_post.side_effect = requests.Timeout("Connection timed out")

            pagerduty.trigger_hibernation_alert(
                "test reason", ["https://github.com/orgs/test/projects/1"]
            )

            mock_logger.warning.assert_called_once()
            assert "Failed to trigger PagerDuty alert" in str(
                mock_logger.warning.call_args
            )

    def test_trigger_logs_info_on_success(self):
        """Test trigger_hibernation_alert() logs info on success."""
        pagerduty.init_pagerduty("test-routing-key")

        with (
            patch("src.pagerduty.requests.post") as mock_post,
            patch.object(pagerduty, "logger") as mock_logger,
        ):
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            pagerduty.trigger_hibernation_alert(
                "test reason", ["https://github.com/orgs/test/projects/1"]
            )

            mock_logger.info.assert_called_with(
                "PagerDuty alert triggered for hibernation"
            )

    def test_trigger_with_multiple_project_urls(self):
        """Test trigger_hibernation_alert() with multiple project URLs."""
        pagerduty.init_pagerduty("test-routing-key")

        with patch("src.pagerduty.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            project_urls = [
                "https://github.com/orgs/test/projects/1",
                "https://github.com/orgs/test/projects/2",
                "https://ghes.company.com/orgs/corp/projects/1",
            ]
            result = pagerduty.trigger_hibernation_alert(
                "GitHub API unreachable", project_urls
            )

            assert result is True
            payload = mock_post.call_args[1]["json"]
            assert payload["payload"]["custom_details"]["project_urls"] == project_urls


@pytest.mark.unit
class TestResolveHibernationAlert:
    """Tests for resolve_hibernation_alert() function."""

    def test_resolve_returns_false_when_not_initialized(self):
        """Test resolve_hibernation_alert() returns False when not initialized."""
        result = pagerduty.resolve_hibernation_alert()

        assert result is False

    def test_resolve_makes_correct_api_call(self):
        """Test resolve_hibernation_alert() makes correct API call."""
        pagerduty.init_pagerduty("test-routing-key")

        with patch("src.pagerduty.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            result = pagerduty.resolve_hibernation_alert()

            assert result is True
            mock_post.assert_called_once()

            # Verify the API call details
            call_args = mock_post.call_args
            assert call_args[0][0] == pagerduty.PAGERDUTY_EVENTS_URL
            assert call_args[1]["timeout"] == 10

            payload = call_args[1]["json"]
            assert payload["routing_key"] == "test-routing-key"
            assert payload["event_action"] == "resolve"
            assert payload["dedup_key"] == pagerduty.HIBERNATION_DEDUP_KEY
            # Resolve payload should NOT have the full payload section
            assert "payload" not in payload

    def test_resolve_handles_http_timeout_gracefully(self):
        """Test resolve_hibernation_alert() handles timeout gracefully."""
        pagerduty.init_pagerduty("test-routing-key")

        with patch("src.pagerduty.requests.post") as mock_post:
            mock_post.side_effect = requests.Timeout("Connection timed out")

            result = pagerduty.resolve_hibernation_alert()

            assert result is False

    def test_resolve_handles_http_connection_error_gracefully(self):
        """Test resolve_hibernation_alert() handles connection error gracefully."""
        pagerduty.init_pagerduty("test-routing-key")

        with patch("src.pagerduty.requests.post") as mock_post:
            mock_post.side_effect = requests.ConnectionError("Connection refused")

            result = pagerduty.resolve_hibernation_alert()

            assert result is False

    def test_resolve_handles_http_4xx_error_gracefully(self):
        """Test resolve_hibernation_alert() handles 4xx HTTP errors gracefully."""
        pagerduty.init_pagerduty("test-routing-key")

        with patch("src.pagerduty.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.raise_for_status.side_effect = requests.HTTPError(
                "400 Bad Request"
            )
            mock_post.return_value = mock_response

            result = pagerduty.resolve_hibernation_alert()

            assert result is False

    def test_resolve_handles_http_5xx_error_gracefully(self):
        """Test resolve_hibernation_alert() handles 5xx HTTP errors gracefully."""
        pagerduty.init_pagerduty("test-routing-key")

        with patch("src.pagerduty.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.raise_for_status.side_effect = requests.HTTPError(
                "500 Internal Server Error"
            )
            mock_post.return_value = mock_response

            result = pagerduty.resolve_hibernation_alert()

            assert result is False

    def test_resolve_logs_warning_on_failure(self):
        """Test resolve_hibernation_alert() logs warning on failure."""
        pagerduty.init_pagerduty("test-routing-key")

        with (
            patch("src.pagerduty.requests.post") as mock_post,
            patch.object(pagerduty, "logger") as mock_logger,
        ):
            mock_post.side_effect = requests.Timeout("Connection timed out")

            pagerduty.resolve_hibernation_alert()

            mock_logger.warning.assert_called_once()
            assert "Failed to resolve PagerDuty alert" in str(
                mock_logger.warning.call_args
            )

    def test_resolve_logs_info_on_success(self):
        """Test resolve_hibernation_alert() logs info on success."""
        pagerduty.init_pagerduty("test-routing-key")

        with (
            patch("src.pagerduty.requests.post") as mock_post,
            patch.object(pagerduty, "logger") as mock_logger,
        ):
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            pagerduty.resolve_hibernation_alert()

            mock_logger.info.assert_called_with(
                "PagerDuty alert resolved for hibernation"
            )


@pytest.mark.unit
class TestResetPagerduty:
    """Tests for reset_pagerduty() function."""

    def test_reset_clears_module_state(self):
        """Test reset_pagerduty() clears module state."""
        pagerduty.init_pagerduty("test-key")
        assert pagerduty._initialized is True
        assert pagerduty._routing_key == "test-key"

        pagerduty.reset_pagerduty()

        assert pagerduty._initialized is False
        assert pagerduty._routing_key is None

    def test_reset_allows_reinit(self):
        """Test reset_pagerduty() allows reinitialization with new key."""
        pagerduty.init_pagerduty("first-key")
        pagerduty.reset_pagerduty()
        pagerduty.init_pagerduty("second-key")

        assert pagerduty._routing_key == "second-key"


@pytest.mark.unit
class TestDedupKeyConstant:
    """Tests for dedup key constant."""

    def test_dedup_key_value(self):
        """Test HIBERNATION_DEDUP_KEY has expected value."""
        assert pagerduty.HIBERNATION_DEDUP_KEY == "kiln-hibernation"

    def test_events_url_value(self):
        """Test PAGERDUTY_EVENTS_URL has expected value."""
        assert pagerduty.PAGERDUTY_EVENTS_URL == "https://events.pagerduty.com/v2/enqueue"
