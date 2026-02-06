"""Unit tests for the Slack module.

Tests verify:
- send_startup_ping() success case
- send_startup_ping() when not initialized
- send_startup_ping() API error handling
- send_comment_processed_notification() success case
- send_comment_processed_notification() when not initialized
- send_comment_processed_notification() API error handling
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from src.integrations import slack


@pytest.fixture(autouse=True)
def reset_slack_state():
    """Reset Slack module state before and after each test."""
    slack.reset_slack()
    yield
    slack.reset_slack()


@pytest.mark.unit
class TestSendStartupPing:
    """Tests for send_startup_ping() function."""

    def test_send_startup_ping_returns_false_when_not_initialized(self):
        """Test send_startup_ping() returns False when not initialized."""
        result = slack.send_startup_ping()

        assert result is False

    def test_send_startup_ping_success(self):
        """Test send_startup_ping() returns True on success."""
        slack.init_slack("xoxb-test-token", "U12345")

        with patch("src.integrations.slack.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {"ok": True}
            mock_post.return_value = mock_response

            result = slack.send_startup_ping()

            assert result is True
            mock_post.assert_called_once()

            # Verify the API call details
            call_args = mock_post.call_args
            assert call_args[0][0] == slack.SLACK_API_URL
            assert call_args[1]["timeout"] == 10

            payload = call_args[1]["json"]
            assert payload["channel"] == "U12345"
            assert payload["text"] == "🔥 your kiln is firing"
            assert payload["unfurl_links"] is False
            assert payload["unfurl_media"] is False

            headers = call_args[1]["headers"]
            assert headers["Authorization"] == "Bearer xoxb-test-token"
            assert headers["Content-Type"] == "application/json"

    def test_send_startup_ping_handles_slack_api_error(self):
        """Test send_startup_ping() handles Slack API error response gracefully."""
        slack.init_slack("xoxb-test-token", "U12345")

        with patch("src.integrations.slack.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {"ok": False, "error": "channel_not_found"}
            mock_post.return_value = mock_response

            result = slack.send_startup_ping()

            assert result is False

    def test_send_startup_ping_handles_http_timeout_gracefully(self):
        """Test send_startup_ping() handles timeout gracefully."""
        slack.init_slack("xoxb-test-token", "U12345")

        with patch("src.integrations.slack.requests.post") as mock_post:
            mock_post.side_effect = requests.Timeout("Connection timed out")

            result = slack.send_startup_ping()

            assert result is False

    def test_send_startup_ping_handles_http_connection_error_gracefully(self):
        """Test send_startup_ping() handles connection error gracefully."""
        slack.init_slack("xoxb-test-token", "U12345")

        with patch("src.integrations.slack.requests.post") as mock_post:
            mock_post.side_effect = requests.ConnectionError("Connection refused")

            result = slack.send_startup_ping()

            assert result is False

    def test_send_startup_ping_handles_http_4xx_error_gracefully(self):
        """Test send_startup_ping() handles 4xx HTTP errors gracefully."""
        slack.init_slack("xoxb-test-token", "U12345")

        with patch("src.integrations.slack.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.raise_for_status.side_effect = requests.HTTPError(
                "400 Bad Request"
            )
            mock_post.return_value = mock_response

            result = slack.send_startup_ping()

            assert result is False

    def test_send_startup_ping_handles_http_5xx_error_gracefully(self):
        """Test send_startup_ping() handles 5xx HTTP errors gracefully."""
        slack.init_slack("xoxb-test-token", "U12345")

        with patch("src.integrations.slack.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.raise_for_status.side_effect = requests.HTTPError(
                "500 Internal Server Error"
            )
            mock_post.return_value = mock_response

            result = slack.send_startup_ping()

            assert result is False


@pytest.mark.unit
class TestSendCommentProcessedNotification:
    """Tests for send_comment_processed_notification() function."""

    def test_returns_false_when_not_initialized(self):
        """Test send_comment_processed_notification() returns False when not initialized."""
        result = slack.send_comment_processed_notification(
            issue_number=166,
            issue_title="Test Issue",
            comment_url="https://github.com/org/repo/issues/166#issuecomment-123",
        )

        assert result is False

    def test_success(self):
        """Test send_comment_processed_notification() returns True on success."""
        slack.init_slack("xoxb-test-token", "U12345")

        with patch("src.integrations.slack.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {"ok": True}
            mock_post.return_value = mock_response

            result = slack.send_comment_processed_notification(
                issue_number=166,
                issue_title="Test Issue Title",
                comment_url="https://github.com/org/repo/issues/166#issuecomment-123",
            )

            assert result is True
            mock_post.assert_called_once()

            # Verify the API call details
            call_args = mock_post.call_args
            assert call_args[0][0] == slack.SLACK_API_URL
            assert call_args[1]["timeout"] == 10

            payload = call_args[1]["json"]
            assert payload["channel"] == "U12345"
            assert "💬" in payload["text"]
            assert "Comment processed:" in payload["text"]
            assert "<https://github.com/org/repo/issues/166#issuecomment-123|issue #166>" in payload["text"]
            assert payload["unfurl_links"] is False
            assert payload["unfurl_media"] is False

            headers = call_args[1]["headers"]
            assert headers["Authorization"] == "Bearer xoxb-test-token"
            assert headers["Content-Type"] == "application/json"

    def test_handles_slack_api_error(self):
        """Test send_comment_processed_notification() handles Slack API error response gracefully."""
        slack.init_slack("xoxb-test-token", "U12345")

        with patch("src.integrations.slack.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {"ok": False, "error": "channel_not_found"}
            mock_post.return_value = mock_response

            result = slack.send_comment_processed_notification(
                issue_number=166,
                issue_title="Test Issue",
                comment_url="https://github.com/org/repo/issues/166#issuecomment-123",
            )

            assert result is False

    def test_handles_http_timeout_gracefully(self):
        """Test send_comment_processed_notification() handles timeout gracefully."""
        slack.init_slack("xoxb-test-token", "U12345")

        with patch("src.integrations.slack.requests.post") as mock_post:
            mock_post.side_effect = requests.Timeout("Connection timed out")

            result = slack.send_comment_processed_notification(
                issue_number=166,
                issue_title="Test Issue",
                comment_url="https://github.com/org/repo/issues/166#issuecomment-123",
            )

            assert result is False

    def test_handles_http_connection_error_gracefully(self):
        """Test send_comment_processed_notification() handles connection error gracefully."""
        slack.init_slack("xoxb-test-token", "U12345")

        with patch("src.integrations.slack.requests.post") as mock_post:
            mock_post.side_effect = requests.ConnectionError("Connection refused")

            result = slack.send_comment_processed_notification(
                issue_number=166,
                issue_title="Test Issue",
                comment_url="https://github.com/org/repo/issues/166#issuecomment-123",
            )

            assert result is False


@pytest.mark.unit
class TestSendImplementationBeginningNotification:
    """Tests for send_implementation_beginning_notification() function."""

    def test_returns_false_when_not_initialized(self):
        """Test send_implementation_beginning_notification() returns False when not initialized."""
        result = slack.send_implementation_beginning_notification(
            pr_url="https://github.com/org/repo/pull/42",
            pr_number=42,
        )

        assert result is False

    def test_success(self):
        """Test send_implementation_beginning_notification() returns True on success."""
        slack.init_slack("xoxb-test-token", "U12345")

        with patch("src.integrations.slack.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {"ok": True}
            mock_post.return_value = mock_response

            result = slack.send_implementation_beginning_notification(
                pr_url="https://github.com/org/repo/pull/42",
                pr_number=42,
            )

            assert result is True
            mock_post.assert_called_once()

            # Verify the API call details
            call_args = mock_post.call_args
            assert call_args[0][0] == slack.SLACK_API_URL
            assert call_args[1]["timeout"] == 10

            payload = call_args[1]["json"]
            assert payload["channel"] == "U12345"
            assert "🔥" in payload["text"]
            assert "Firing implementation:" in payload["text"]
            assert "<https://github.com/org/repo/pull/42|PR #42>" in payload["text"]
            assert payload["unfurl_links"] is False
            assert payload["unfurl_media"] is False

            headers = call_args[1]["headers"]
            assert headers["Authorization"] == "Bearer xoxb-test-token"
            assert headers["Content-Type"] == "application/json"

    def test_handles_slack_api_error(self):
        """Test send_implementation_beginning_notification() handles Slack API error gracefully."""
        slack.init_slack("xoxb-test-token", "U12345")

        with patch("src.integrations.slack.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {"ok": False, "error": "channel_not_found"}
            mock_post.return_value = mock_response

            result = slack.send_implementation_beginning_notification(
                pr_url="https://github.com/org/repo/pull/42",
                pr_number=42,
            )

            assert result is False

    def test_handles_http_timeout_gracefully(self):
        """Test send_implementation_beginning_notification() handles timeout gracefully."""
        slack.init_slack("xoxb-test-token", "U12345")

        with patch("src.integrations.slack.requests.post") as mock_post:
            mock_post.side_effect = requests.Timeout("Connection timed out")

            result = slack.send_implementation_beginning_notification(
                pr_url="https://github.com/org/repo/pull/42",
                pr_number=42,
            )

            assert result is False

    def test_handles_http_connection_error_gracefully(self):
        """Test send_implementation_beginning_notification() handles connection error gracefully."""
        slack.init_slack("xoxb-test-token", "U12345")

        with patch("src.integrations.slack.requests.post") as mock_post:
            mock_post.side_effect = requests.ConnectionError("Connection refused")

            result = slack.send_implementation_beginning_notification(
                pr_url="https://github.com/org/repo/pull/42",
                pr_number=42,
            )

            assert result is False


@pytest.mark.unit
class TestSendReadyForValidationNotification:
    """Tests for send_ready_for_validation_notification() function."""

    def test_returns_false_when_not_initialized(self):
        """Test send_ready_for_validation_notification() returns False when not initialized."""
        result = slack.send_ready_for_validation_notification(
            pr_url="https://github.com/org/repo/pull/42",
            pr_number=42,
        )

        assert result is False

    def test_success(self):
        """Test send_ready_for_validation_notification() returns True on success."""
        slack.init_slack("xoxb-test-token", "U12345")

        with patch("src.integrations.slack.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {"ok": True}
            mock_post.return_value = mock_response

            result = slack.send_ready_for_validation_notification(
                pr_url="https://github.com/org/repo/pull/42",
                pr_number=42,
            )

            assert result is True
            mock_post.assert_called_once()

            # Verify the API call details
            call_args = mock_post.call_args
            assert call_args[0][0] == slack.SLACK_API_URL
            assert call_args[1]["timeout"] == 10

            payload = call_args[1]["json"]
            assert payload["channel"] == "U12345"
            assert "☑️" in payload["text"]
            assert "Ready for validation:" in payload["text"]
            assert "<https://github.com/org/repo/pull/42|PR #42>" in payload["text"]
            assert payload["unfurl_links"] is False
            assert payload["unfurl_media"] is False

            headers = call_args[1]["headers"]
            assert headers["Authorization"] == "Bearer xoxb-test-token"
            assert headers["Content-Type"] == "application/json"

    def test_handles_slack_api_error(self):
        """Test send_ready_for_validation_notification() handles Slack API error gracefully."""
        slack.init_slack("xoxb-test-token", "U12345")

        with patch("src.integrations.slack.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {"ok": False, "error": "channel_not_found"}
            mock_post.return_value = mock_response

            result = slack.send_ready_for_validation_notification(
                pr_url="https://github.com/org/repo/pull/42",
                pr_number=42,
            )

            assert result is False

    def test_handles_http_timeout_gracefully(self):
        """Test send_ready_for_validation_notification() handles timeout gracefully."""
        slack.init_slack("xoxb-test-token", "U12345")

        with patch("src.integrations.slack.requests.post") as mock_post:
            mock_post.side_effect = requests.Timeout("Connection timed out")

            result = slack.send_ready_for_validation_notification(
                pr_url="https://github.com/org/repo/pull/42",
                pr_number=42,
            )

            assert result is False

    def test_handles_http_connection_error_gracefully(self):
        """Test send_ready_for_validation_notification() handles connection error gracefully."""
        slack.init_slack("xoxb-test-token", "U12345")

        with patch("src.integrations.slack.requests.post") as mock_post:
            mock_post.side_effect = requests.ConnectionError("Connection refused")

            result = slack.send_ready_for_validation_notification(
                pr_url="https://github.com/org/repo/pull/42",
                pr_number=42,
            )

            assert result is False


@pytest.mark.unit
class TestSendPhaseCompletionNotification:
    """Tests for send_phase_completion_notification() function."""

    def test_returns_false_when_not_initialized(self):
        """Test send_phase_completion_notification() returns False when not initialized."""
        result = slack.send_phase_completion_notification(
            issue_url="https://github.com/org/repo/issues/42",
            phase="Research",
            issue_title="Test Issue",
            issue_number=42,
        )

        assert result is False

    def test_returns_false_for_implement_phase(self):
        """Test send_phase_completion_notification() returns False for Implement phase."""
        slack.init_slack("xoxb-test-token", "U12345")

        result = slack.send_phase_completion_notification(
            issue_url="https://github.com/org/repo/issues/42",
            phase="Implement",
            issue_title="Test Issue",
            issue_number=42,
        )

        assert result is False

    def test_returns_false_for_unknown_phase(self):
        """Test send_phase_completion_notification() returns False for unknown phases."""
        slack.init_slack("xoxb-test-token", "U12345")

        result = slack.send_phase_completion_notification(
            issue_url="https://github.com/org/repo/issues/42",
            phase="Unknown",
            issue_title="Test Issue",
            issue_number=42,
        )

        assert result is False

    def test_success_research_phase(self):
        """Test send_phase_completion_notification() returns True for Research phase."""
        slack.init_slack("xoxb-test-token", "U12345")

        with patch("src.integrations.slack.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {"ok": True}
            mock_post.return_value = mock_response

            result = slack.send_phase_completion_notification(
                issue_url="https://github.com/org/repo/issues/42",
                phase="Research",
                issue_title="Test Issue",
                issue_number=42,
            )

            assert result is True
            mock_post.assert_called_once()

            payload = mock_post.call_args[1]["json"]
            assert payload["channel"] == "U12345"
            assert "🧪" in payload["text"]
            assert "Research complete:" in payload["text"]
            assert "<https://github.com/org/repo/issues/42|Issue #42>" in payload["text"]
            assert payload["unfurl_links"] is False
            assert payload["unfurl_media"] is False

    def test_success_plan_phase(self):
        """Test send_phase_completion_notification() returns True for Plan phase."""
        slack.init_slack("xoxb-test-token", "U12345")

        with patch("src.integrations.slack.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {"ok": True}
            mock_post.return_value = mock_response

            result = slack.send_phase_completion_notification(
                issue_url="https://github.com/org/repo/issues/42",
                phase="Plan",
                issue_title="Test Issue",
                issue_number=42,
            )

            assert result is True
            mock_post.assert_called_once()

            payload = mock_post.call_args[1]["json"]
            assert payload["channel"] == "U12345"
            assert "🗺️" in payload["text"]
            assert "Plan complete:" in payload["text"]
            assert "<https://github.com/org/repo/issues/42|Issue #42>" in payload["text"]
            assert payload["unfurl_links"] is False
            assert payload["unfurl_media"] is False

    def test_handles_slack_api_error(self):
        """Test send_phase_completion_notification() handles Slack API error gracefully."""
        slack.init_slack("xoxb-test-token", "U12345")

        with patch("src.integrations.slack.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {"ok": False, "error": "channel_not_found"}
            mock_post.return_value = mock_response

            result = slack.send_phase_completion_notification(
                issue_url="https://github.com/org/repo/issues/42",
                phase="Research",
                issue_title="Test Issue",
                issue_number=42,
            )

            assert result is False

    def test_handles_http_timeout_gracefully(self):
        """Test send_phase_completion_notification() handles timeout gracefully."""
        slack.init_slack("xoxb-test-token", "U12345")

        with patch("src.integrations.slack.requests.post") as mock_post:
            mock_post.side_effect = requests.Timeout("Connection timed out")

            result = slack.send_phase_completion_notification(
                issue_url="https://github.com/org/repo/issues/42",
                phase="Research",
                issue_title="Test Issue",
                issue_number=42,
            )

            assert result is False

    def test_handles_http_connection_error_gracefully(self):
        """Test send_phase_completion_notification() handles connection error gracefully."""
        slack.init_slack("xoxb-test-token", "U12345")

        with patch("src.integrations.slack.requests.post") as mock_post:
            mock_post.side_effect = requests.ConnectionError("Connection refused")

            result = slack.send_phase_completion_notification(
                issue_url="https://github.com/org/repo/issues/42",
                phase="Research",
                issue_title="Test Issue",
                issue_number=42,
            )

            assert result is False
