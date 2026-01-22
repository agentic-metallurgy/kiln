"""Unit tests for the pagerduty module."""

import json
import logging
import urllib.error
import urllib.request
from unittest.mock import MagicMock

import pytest

from src.pagerduty import (
    PAGERDUTY_EVENTS_URL,
    _send_event,
    resolve_alert,
    trigger_alert,
)


@pytest.mark.unit
class TestSendEvent:
    """Tests for _send_event function."""

    def test_send_event_success(self, monkeypatch):
        """Test successful event send returns True."""
        mock_response = MagicMock()
        mock_response.status = 202
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        captured_request = {}

        def mock_urlopen(req, timeout=None):
            captured_request["url"] = req.full_url
            captured_request["data"] = req.data
            captured_request["headers"] = dict(req.headers)
            captured_request["method"] = req.method
            captured_request["timeout"] = timeout
            return mock_response

        monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

        result = _send_event(
            routing_key="test-key",
            event_action="trigger",
            dedup_key="test-dedup",
            payload={"summary": "Test alert", "severity": "info", "source": "test"},
        )

        assert result is True
        assert captured_request["url"] == PAGERDUTY_EVENTS_URL
        assert captured_request["method"] == "POST"
        assert captured_request["headers"]["Content-type"] == "application/json"
        assert captured_request["timeout"] == 10

        # Verify the request data
        request_data = json.loads(captured_request["data"].decode("utf-8"))
        assert request_data["routing_key"] == "test-key"
        assert request_data["event_action"] == "trigger"
        assert request_data["dedup_key"] == "test-dedup"
        assert request_data["payload"]["summary"] == "Test alert"

    def test_send_event_resolve_without_payload(self, monkeypatch):
        """Test resolve event can be sent without payload."""
        mock_response = MagicMock()
        mock_response.status = 202
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        captured_request = {}

        def mock_urlopen(req, timeout=None):
            captured_request["data"] = req.data
            return mock_response

        monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

        result = _send_event(
            routing_key="test-key",
            event_action="resolve",
            dedup_key="test-dedup",
            payload=None,
        )

        assert result is True

        # Verify the request data does not include payload
        request_data = json.loads(captured_request["data"].decode("utf-8"))
        assert "payload" not in request_data
        assert request_data["event_action"] == "resolve"

    def test_send_event_empty_routing_key_returns_false(self, monkeypatch):
        """Test empty routing key skips sending and returns False."""
        mock_urlopen = MagicMock()
        monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

        result = _send_event(
            routing_key="",
            event_action="trigger",
            dedup_key="test-dedup",
            payload={"summary": "Test"},
        )

        assert result is False
        mock_urlopen.assert_not_called()

    def test_send_event_unexpected_status_returns_false(self, monkeypatch, caplog):
        """Test non-202 status code logs warning and returns False."""
        mock_response = MagicMock()
        mock_response.status = 400
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        def mock_urlopen(req, timeout=None):
            return mock_response

        monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

        with caplog.at_level(logging.WARNING):
            result = _send_event(
                routing_key="test-key",
                event_action="trigger",
                dedup_key="test-dedup",
                payload={"summary": "Test"},
            )

        assert result is False
        assert "unexpected status: 400" in caplog.text

    def test_send_event_http_error_returns_false(self, monkeypatch, caplog):
        """Test HTTP error logs warning and returns False."""

        def mock_urlopen(req, timeout=None):
            raise urllib.error.HTTPError(
                url=PAGERDUTY_EVENTS_URL,
                code=401,
                msg="Unauthorized",
                hdrs={},
                fp=None,
            )

        monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

        with caplog.at_level(logging.WARNING):
            result = _send_event(
                routing_key="test-key",
                event_action="trigger",
                dedup_key="test-dedup",
                payload={"summary": "Test"},
            )

        assert result is False
        assert "HTTP error: 401 Unauthorized" in caplog.text

    def test_send_event_url_error_returns_false(self, monkeypatch, caplog):
        """Test URL/connection error logs warning and returns False."""

        def mock_urlopen(req, timeout=None):
            raise urllib.error.URLError("Connection refused")

        monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

        with caplog.at_level(logging.WARNING):
            result = _send_event(
                routing_key="test-key",
                event_action="trigger",
                dedup_key="test-dedup",
                payload={"summary": "Test"},
            )

        assert result is False
        assert "connection error: Connection refused" in caplog.text

    def test_send_event_generic_exception_returns_false(self, monkeypatch, caplog):
        """Test generic exception logs warning and returns False."""

        def mock_urlopen(req, timeout=None):
            raise Exception("Something unexpected happened")

        monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

        with caplog.at_level(logging.WARNING):
            result = _send_event(
                routing_key="test-key",
                event_action="trigger",
                dedup_key="test-dedup",
                payload={"summary": "Test"},
            )

        assert result is False
        assert "Failed to send PagerDuty event" in caplog.text
        assert "Something unexpected happened" in caplog.text


@pytest.mark.unit
class TestTriggerAlert:
    """Tests for trigger_alert function."""

    def test_trigger_alert_constructs_correct_payload(self, monkeypatch):
        """Test trigger_alert constructs the correct payload structure."""
        captured_args = {}

        def mock_send_event(routing_key, event_action, dedup_key, payload=None):
            captured_args["routing_key"] = routing_key
            captured_args["event_action"] = event_action
            captured_args["dedup_key"] = dedup_key
            captured_args["payload"] = payload
            return True

        monkeypatch.setattr("src.pagerduty._send_event", mock_send_event)

        result = trigger_alert(
            routing_key="test-routing-key",
            dedup_key="kiln-hibernation",
            summary="Kiln daemon entered hibernation mode",
            reason="GitHub API unreachable: TLS handshake timeout",
            custom_details={
                "project_urls": ["https://github.com/orgs/test/projects/1"],
                "hibernation_started": "2026-01-21T10:30:00Z",
            },
        )

        assert result is True
        assert captured_args["routing_key"] == "test-routing-key"
        assert captured_args["event_action"] == "trigger"
        assert captured_args["dedup_key"] == "kiln-hibernation"

        payload = captured_args["payload"]
        assert payload["summary"] == "Kiln daemon entered hibernation mode"
        assert payload["severity"] == "info"
        assert payload["source"] == "kiln-daemon"
        assert (
            payload["custom_details"]["reason"]
            == "GitHub API unreachable: TLS handshake timeout"
        )
        assert payload["custom_details"]["project_urls"] == [
            "https://github.com/orgs/test/projects/1"
        ]
        assert payload["custom_details"]["hibernation_started"] == "2026-01-21T10:30:00Z"

    def test_trigger_alert_without_custom_details(self, monkeypatch):
        """Test trigger_alert works without custom_details."""
        captured_args = {}

        def mock_send_event(routing_key, event_action, dedup_key, payload=None):
            captured_args["payload"] = payload
            return True

        monkeypatch.setattr("src.pagerduty._send_event", mock_send_event)

        result = trigger_alert(
            routing_key="test-key",
            dedup_key="kiln-hibernation",
            summary="Test alert",
            reason="Test reason",
        )

        assert result is True
        payload = captured_args["payload"]
        assert payload["custom_details"] == {"reason": "Test reason"}

    def test_trigger_alert_empty_routing_key_returns_false(self, monkeypatch):
        """Test trigger_alert returns False for empty routing key."""
        mock_send_event = MagicMock()
        monkeypatch.setattr("src.pagerduty._send_event", mock_send_event)

        result = trigger_alert(
            routing_key="",
            dedup_key="kiln-hibernation",
            summary="Test alert",
            reason="Test reason",
        )

        assert result is False
        mock_send_event.assert_not_called()

    def test_trigger_alert_uses_info_severity(self, monkeypatch):
        """Test trigger_alert uses 'info' severity as per requirements."""
        captured_args = {}

        def mock_send_event(routing_key, event_action, dedup_key, payload=None):
            captured_args["payload"] = payload
            return True

        monkeypatch.setattr("src.pagerduty._send_event", mock_send_event)

        trigger_alert(
            routing_key="test-key",
            dedup_key="kiln-hibernation",
            summary="Test alert",
            reason="Test reason",
        )

        assert captured_args["payload"]["severity"] == "info"

    def test_trigger_alert_logs_info_message(self, monkeypatch, caplog):
        """Test trigger_alert logs an info message."""

        def mock_send_event(routing_key, event_action, dedup_key, payload=None):
            return True

        monkeypatch.setattr("src.pagerduty._send_event", mock_send_event)

        with caplog.at_level(logging.INFO):
            trigger_alert(
                routing_key="test-key",
                dedup_key="kiln-hibernation",
                summary="Test alert summary",
                reason="Test reason",
            )

        assert "Triggering PagerDuty alert: Test alert summary" in caplog.text


@pytest.mark.unit
class TestResolveAlert:
    """Tests for resolve_alert function."""

    def test_resolve_alert_constructs_correct_request(self, monkeypatch):
        """Test resolve_alert sends correct event action and dedup_key."""
        captured_args = {}

        def mock_send_event(routing_key, event_action, dedup_key, payload=None):
            captured_args["routing_key"] = routing_key
            captured_args["event_action"] = event_action
            captured_args["dedup_key"] = dedup_key
            captured_args["payload"] = payload
            return True

        monkeypatch.setattr("src.pagerduty._send_event", mock_send_event)

        result = resolve_alert(
            routing_key="test-routing-key",
            dedup_key="kiln-hibernation",
        )

        assert result is True
        assert captured_args["routing_key"] == "test-routing-key"
        assert captured_args["event_action"] == "resolve"
        assert captured_args["dedup_key"] == "kiln-hibernation"
        assert captured_args["payload"] is None

    def test_resolve_alert_empty_routing_key_returns_false(self, monkeypatch):
        """Test resolve_alert returns False for empty routing key."""
        mock_send_event = MagicMock()
        monkeypatch.setattr("src.pagerduty._send_event", mock_send_event)

        result = resolve_alert(
            routing_key="",
            dedup_key="kiln-hibernation",
        )

        assert result is False
        mock_send_event.assert_not_called()

    def test_resolve_alert_logs_info_message(self, monkeypatch, caplog):
        """Test resolve_alert logs an info message."""

        def mock_send_event(routing_key, event_action, dedup_key, payload=None):
            return True

        monkeypatch.setattr("src.pagerduty._send_event", mock_send_event)

        with caplog.at_level(logging.INFO):
            resolve_alert(
                routing_key="test-key",
                dedup_key="kiln-hibernation",
            )

        assert "Resolving PagerDuty hibernation alert" in caplog.text


@pytest.mark.unit
class TestPagerDutyConstants:
    """Tests for module constants."""

    def test_pagerduty_events_url_is_correct(self):
        """Test the PagerDuty Events URL is the correct v2 endpoint."""
        assert PAGERDUTY_EVENTS_URL == "https://events.pagerduty.com/v2/enqueue"
