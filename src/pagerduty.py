"""PagerDuty integration for kiln hibernation alerts.

This module provides functions to trigger and resolve PagerDuty alerts
when the daemon enters or exits hibernation mode due to network issues.
"""

import requests

from src.logger import get_logger

logger = get_logger(__name__)

# Module-level state (singleton pattern matching telemetry.py)
_initialized = False
_routing_key: str | None = None

# PagerDuty Events API v2 endpoint
PAGERDUTY_EVENTS_URL = "https://events.pagerduty.com/v2/enqueue"

# Dedup key for incident correlation - ensures repeated hibernation events
# update the same incident rather than creating new ones
HIBERNATION_DEDUP_KEY = "kiln-hibernation"


def init_pagerduty(routing_key: str | None) -> None:
    """Initialize PagerDuty integration with the given routing key.

    This function is idempotent - calling it multiple times is safe.
    If routing_key is None or empty string, PagerDuty integration is disabled.

    Args:
        routing_key: PagerDuty Events API v2 routing (integration) key.
                    If None or empty, PagerDuty alerts are disabled.
    """
    global _initialized, _routing_key

    if _initialized:
        return

    if not routing_key:
        logger.debug("PagerDuty not configured (no routing key)")
        return

    _routing_key = routing_key
    _initialized = True
    logger.info("PagerDuty initialized for hibernation alerts")


def trigger_hibernation_alert(reason: str, project_urls: list[str]) -> bool:
    """Trigger a PagerDuty alert when entering hibernation mode.

    Creates or updates a PagerDuty incident indicating the daemon has
    entered hibernation due to network connectivity issues.

    Args:
        reason: Description of why hibernation was triggered (e.g., network error)
        project_urls: List of project URLs being monitored (for context)

    Returns:
        True if alert was sent successfully, False otherwise.
        Returns False without error if PagerDuty is not initialized.
    """
    if not _initialized or not _routing_key:
        return False

    payload = {
        "routing_key": _routing_key,
        "event_action": "trigger",
        "dedup_key": HIBERNATION_DEDUP_KEY,
        "payload": {
            "summary": f"Kiln daemon entered hibernation: {reason}",
            "severity": "warning",
            "source": "kiln-daemon",
            "custom_details": {
                "reason": reason,
                "project_urls": project_urls,
                "status": "hibernating",
            },
        },
    }

    try:
        response = requests.post(
            PAGERDUTY_EVENTS_URL,
            json=payload,
            timeout=10,
        )
        response.raise_for_status()
        logger.info("PagerDuty alert triggered for hibernation")
        return True
    except requests.RequestException as e:
        logger.warning(f"Failed to trigger PagerDuty alert: {e}")
        return False


def resolve_hibernation_alert() -> bool:
    """Resolve the PagerDuty incident when exiting hibernation mode.

    Automatically resolves the hibernation incident, indicating the daemon
    has restored connectivity and resumed normal operation.

    Returns:
        True if resolve was sent successfully, False otherwise.
        Returns False without error if PagerDuty is not initialized.
    """
    if not _initialized or not _routing_key:
        return False

    payload = {
        "routing_key": _routing_key,
        "event_action": "resolve",
        "dedup_key": HIBERNATION_DEDUP_KEY,
    }

    try:
        response = requests.post(
            PAGERDUTY_EVENTS_URL,
            json=payload,
            timeout=10,
        )
        response.raise_for_status()
        logger.info("PagerDuty alert resolved for hibernation")
        return True
    except requests.RequestException as e:
        logger.warning(f"Failed to resolve PagerDuty alert: {e}")
        return False


def reset_pagerduty() -> None:
    """Reset PagerDuty module state (for testing only).

    This function is intended for use in tests to reset the module
    state between test cases.
    """
    global _initialized, _routing_key
    _initialized = False
    _routing_key = None
