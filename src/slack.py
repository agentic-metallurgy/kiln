"""Slack integration for kiln phase completion notifications.

This module provides functions to send Slack DM notifications when issues
reach their "final destination" in the workflow pipeline.
"""

import requests

from src.logger import get_logger

logger = get_logger(__name__)

# Module-level state (singleton pattern matching pagerduty.py)
_initialized = False
_bot_token: str | None = None
_user_id: str | None = None

# Slack API endpoint for posting messages
SLACK_API_URL = "https://slack.com/api/chat.postMessage"


def init_slack(bot_token: str | None, user_id: str | None) -> None:
    """Initialize Slack integration with the given credentials.

    This function is idempotent - calling it multiple times is safe.
    If bot_token or user_id is None or empty string, Slack integration is disabled.

    Args:
        bot_token: Slack Bot OAuth token (starts with xoxb-).
                   If None or empty, Slack notifications are disabled.
        user_id: Slack user ID to send DMs to (starts with U).
                 If None or empty, Slack notifications are disabled.
    """
    global _initialized, _bot_token, _user_id

    if _initialized:
        return

    if not bot_token or not user_id:
        logger.debug("Slack not configured (missing bot token or user ID)")
        return

    _bot_token = bot_token
    _user_id = user_id
    _initialized = True
    logger.info("Slack initialized for phase completion notifications")


def send_phase_completion_notification(
    issue_url: str,
    phase: str,
    issue_title: str,
    issue_number: int,
) -> bool:
    """Send a Slack DM notification when an issue completes a phase.

    Sends a direct message to the configured Slack user indicating that
    an issue has reached its final destination in the workflow.

    Args:
        issue_url: Full URL to the GitHub issue
        phase: The completed phase (e.g., "Research", "Plan", "Implement")
        issue_title: Title of the issue
        issue_number: Issue number

    Returns:
        True if notification was sent successfully, False otherwise.
        Returns False without error if Slack is not initialized.
    """
    if not _initialized or not _bot_token or not _user_id:
        return False

    # Build the notification message
    message = f"Issue #{issue_number} has completed {phase}\n{issue_title}\n{issue_url}"

    payload = {
        "channel": _user_id,
        "text": message,
    }

    headers = {
        "Authorization": f"Bearer {_bot_token}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(
            SLACK_API_URL,
            json=payload,
            headers=headers,
            timeout=10,
        )
        response.raise_for_status()

        # Slack API returns 200 even for errors, check response body
        response_data = response.json()
        if not response_data.get("ok"):
            error = response_data.get("error", "unknown error")
            logger.warning(f"Slack API error: {error}")
            return False

        logger.info(f"Slack notification sent for issue #{issue_number} ({phase})")
        return True
    except requests.RequestException as e:
        logger.warning(f"Failed to send Slack notification: {e}")
        return False


def reset_slack() -> None:
    """Reset Slack module state (for testing only).

    This function is intended for use in tests to reset the module
    state between test cases.
    """
    global _initialized, _bot_token, _user_id
    _initialized = False
    _bot_token = None
    _user_id = None
