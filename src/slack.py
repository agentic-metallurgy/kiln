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

# Emoji mapping for phase completion notifications
PHASE_EMOJIS = {"Research": "🧪", "Plan": "🗺️"}


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
        logger.info("Slack not configured (missing bot token or user ID)")
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
        phase: The completed phase (e.g., "Research", "Plan")
        issue_title: Title of the issue (kept for backwards compatibility)
        issue_number: Issue number

    Returns:
        True if notification was sent successfully, False otherwise.
        Returns False without error if Slack is not initialized or phase
        is not in PHASE_EMOJIS (e.g., "Implement" is handled separately).
    """
    if not _initialized or not _bot_token or not _user_id:
        return False

    # Get emoji for this phase, return False if not supported
    emoji = PHASE_EMOJIS.get(phase)
    if not emoji:
        return False

    # Build the notification message with emoji and Slack mrkdwn link
    message = f"{emoji} {phase} complete: <{issue_url}|Issue #{issue_number}>"

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
            logger.error(f"Slack API error: {error}")
            return False

        logger.info(f"Slack notification sent for issue #{issue_number} ({phase})")
        return True
    except requests.RequestException as e:
        logger.error(f"Failed to send Slack notification: {e}")
        return False


def send_implementation_beginning_notification(pr_url: str, pr_number: int) -> bool:
    """Send a Slack DM notification when implementation begins.

    Sends a direct message to the configured Slack user indicating that
    implementation has started and a draft PR has been created.

    Args:
        pr_url: Full URL to the pull request
        pr_number: Pull request number

    Returns:
        True if notification was sent successfully, False otherwise.
        Returns False without error if Slack is not initialized.
    """
    if not _initialized or not _bot_token or not _user_id:
        return False

    message = f"🔥 Firing implementation: <{pr_url}|PR #{pr_number}>"

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

        response_data = response.json()
        if not response_data.get("ok"):
            error = response_data.get("error", "unknown error")
            logger.error(f"Slack API error sending implementation beginning notification: {error}")
            return False

        logger.info(f"Slack notification sent for implementation beginning PR #{pr_number}")
        return True
    except requests.RequestException as e:
        logger.error(f"Failed to send Slack implementation beginning notification: {e}")
        return False


def send_ready_for_validation_notification(pr_url: str, pr_number: int) -> bool:
    """Send a Slack DM notification when PR is ready for validation.

    Sends a direct message to the configured Slack user indicating that
    implementation is complete and the PR is ready for review.

    Args:
        pr_url: Full URL to the pull request
        pr_number: Pull request number

    Returns:
        True if notification was sent successfully, False otherwise.
        Returns False without error if Slack is not initialized.
    """
    if not _initialized or not _bot_token or not _user_id:
        return False

    message = f"☑️ Ready for validation: <{pr_url}|PR #{pr_number}>"

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

        response_data = response.json()
        if not response_data.get("ok"):
            error = response_data.get("error", "unknown error")
            logger.error(f"Slack API error sending ready for validation notification: {error}")
            return False

        logger.info(f"Slack notification sent for ready for validation PR #{pr_number}")
        return True
    except requests.RequestException as e:
        logger.error(f"Failed to send Slack ready for validation notification: {e}")
        return False


def send_startup_ping() -> bool:
    """Send a startup notification DM to the configured Slack user.

    Sends a "kiln is firing" message to indicate the daemon has started
    and Slack integration is working.

    Returns:
        True if notification was sent successfully, False otherwise.
        Returns False without error if Slack is not initialized.
    """
    if not _initialized or not _bot_token or not _user_id:
        return False

    message = "🔥 your kiln is firing"

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

        response_data = response.json()
        if not response_data.get("ok"):
            error = response_data.get("error", "unknown error")
            logger.error(f"Slack API error sending startup ping: {error}")
            return False

        logger.info("Slack startup ping sent successfully")
        return True
    except requests.RequestException as e:
        logger.error(f"Failed to send Slack startup ping: {e}")
        return False


def send_comment_processed_notification(
    issue_number: int,
    issue_title: str,
    comment_url: str,
) -> bool:
    """Send a Slack DM notification when a comment has been processed.

    Sends a direct message to the configured Slack user indicating that
    their feedback has been applied and a response is ready.

    Args:
        issue_number: The issue number
        issue_title: Title of the issue
        comment_url: Full URL to the response comment

    Returns:
        True if notification was sent successfully, False otherwise.
        Returns False without error if Slack is not initialized.
    """
    if not _initialized or not _bot_token or not _user_id:
        return False

    message = f"Comment processed for issue `#{issue_number} - {issue_title}` -- <{comment_url}|read here>"

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

        response_data = response.json()
        if not response_data.get("ok"):
            error = response_data.get("error", "unknown error")
            logger.error(f"Slack API error sending comment notification: {error}")
            return False

        logger.info(f"Slack notification sent for processed comment on issue #{issue_number}")
        return True
    except requests.RequestException as e:
        logger.error(f"Failed to send Slack comment notification: {e}")
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
