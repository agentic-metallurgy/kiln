"""PagerDuty Events API v2 client for hibernation alerts.

This module provides functions to trigger and resolve PagerDuty alerts when
the kiln daemon enters/exits hibernation mode due to network connectivity issues.

Uses Python's stdlib urllib.request to avoid adding new dependencies.
"""

import json
import urllib.error
import urllib.request
from typing import Any

from src.logger import get_logger

logger = get_logger(__name__)

PAGERDUTY_EVENTS_URL = "https://events.pagerduty.com/v2/enqueue"


def _send_event(
    routing_key: str,
    event_action: str,
    dedup_key: str,
    payload: dict[str, Any] | None = None,
) -> bool:
    """Send an event to PagerDuty Events API v2.

    Args:
        routing_key: PagerDuty routing/integration key
        event_action: Event action ("trigger" or "resolve")
        dedup_key: Deduplication key to link trigger/resolve events
        payload: Event payload (required for trigger, optional for resolve)

    Returns:
        True if event was sent successfully, False otherwise
    """
    if not routing_key:
        logger.debug("PagerDuty routing key not configured, skipping event")
        return False

    data: dict[str, Any] = {
        "routing_key": routing_key,
        "event_action": event_action,
        "dedup_key": dedup_key,
    }
    if payload:
        data["payload"] = payload

    try:
        request_data = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(
            PAGERDUTY_EVENTS_URL,
            data=request_data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 202:
                logger.debug(f"PagerDuty event sent successfully: {event_action}")
                return True
            else:
                logger.warning(
                    f"PagerDuty API returned unexpected status: {response.status}"
                )
                return False
    except urllib.error.HTTPError as e:
        logger.warning(f"PagerDuty API HTTP error: {e.code} {e.reason}")
        return False
    except urllib.error.URLError as e:
        logger.warning(f"PagerDuty API connection error: {e.reason}")
        return False
    except Exception as e:
        logger.warning(f"Failed to send PagerDuty event: {e}")
        return False


def trigger_alert(
    routing_key: str,
    dedup_key: str,
    summary: str,
    reason: str,
    custom_details: dict[str, Any] | None = None,
) -> bool:
    """Trigger a PagerDuty alert for hibernation entry.

    Args:
        routing_key: PagerDuty routing/integration key
        dedup_key: Deduplication key (e.g., "kiln-hibernation")
        summary: Alert summary (e.g., "Kiln daemon entered hibernation mode")
        reason: Reason for hibernation (e.g., "GitHub API unreachable: TLS timeout")
        custom_details: Additional details to include in the alert

    Returns:
        True if alert was triggered successfully, False otherwise
    """
    if not routing_key:
        return False

    details = {"reason": reason}
    if custom_details:
        details.update(custom_details)

    payload = {
        "summary": summary,
        "severity": "info",
        "source": "kiln-daemon",
        "custom_details": details,
    }

    logger.info(f"Triggering PagerDuty alert: {summary}")
    return _send_event(routing_key, "trigger", dedup_key, payload)


def resolve_alert(
    routing_key: str,
    dedup_key: str,
) -> bool:
    """Resolve a PagerDuty alert for hibernation exit.

    Args:
        routing_key: PagerDuty routing/integration key
        dedup_key: Deduplication key matching the trigger event

    Returns:
        True if alert was resolved successfully, False otherwise
    """
    if not routing_key:
        return False

    logger.info("Resolving PagerDuty hibernation alert")
    return _send_event(routing_key, "resolve", dedup_key)
