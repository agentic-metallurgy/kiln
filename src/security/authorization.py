"""Authorization and access control for Kiln daemon operations."""

import logging
from enum import Enum

logger = logging.getLogger(__name__)


class ActorCategory(Enum):
    """Categorization of actors for authorization decisions.

    Used to determine how to handle actions from different types of users:
    - SELF: The configured username_self (full authorization)
    - TEAM: A known team member (silent observation, no action)
    - UNKNOWN: Actor could not be determined (security fail-safe)
    - BLOCKED: A known user who is not authorized
    """

    SELF = "self"
    TEAM = "team"
    UNKNOWN = "unknown"
    BLOCKED = "blocked"


def check_actor_allowed(
    actor: str | None,
    allowed_username: str,
    context_key: str,
    action_type: str = "",
) -> bool:
    """Check if an actor is authorized to perform an action.

    This is a security-critical function that validates whether a GitHub user
    matches the allowed username. It implements a fail-safe pattern:
    - Unknown actor (None) → denied
    - Actor doesn't match allowed_username → denied
    - Actor matches allowed_username → allowed

    Args:
        actor: The GitHub username who performed the action (or None if unknown)
        allowed_username: The authorized GitHub username from config
        context_key: Issue identifier for audit logging (e.g., "owner/repo#123")
        action_type: Type of action for log prefix (e.g., "YOLO", "RESET")

    Returns:
        True if actor is allowed, False otherwise

    Side Effects:
        Logs WARNING message if actor is not allowed (for audit trail)
    """
    prefix = f"{action_type} BLOCKED: " if action_type else "BLOCKED: "

    if actor is None:
        logger.warning(
            f"{prefix}Could not determine actor for {context_key}. Skipping for security."
        )
        return False

    if actor != allowed_username:
        logger.warning(
            f"{prefix}Action by '{actor}' not allowed for {context_key} "
            f"(allowed_username: {allowed_username})."
        )
        return False

    return True
