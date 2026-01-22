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
    username_self: str,
    context_key: str,
    action_type: str = "",
    team_usernames: list[str] | None = None,
) -> ActorCategory:
    """Check if an actor is authorized to perform an action.

    This is a security-critical function that validates whether a GitHub user
    matches the configured username or is a known team member. It implements
    a fail-safe pattern:
    - Unknown actor (None) → UNKNOWN (denied, WARNING log)
    - Actor matches username_self → SELF (allowed, INFO log)
    - Actor in team_usernames → TEAM (observed, DEBUG log)
    - Actor doesn't match any known user → BLOCKED (denied, WARNING log)

    Args:
        actor: The GitHub username who performed the action (or None if unknown)
        username_self: The authorized GitHub username from config (this kiln's owner)
        context_key: Issue identifier for audit logging (e.g., "owner/repo#123")
        action_type: Type of action for log prefix (e.g., "YOLO", "RESET")
        team_usernames: Optional list of known team member usernames

    Returns:
        ActorCategory indicating the type of actor:
        - SELF: Actor is the configured username_self (full authorization)
        - TEAM: Actor is a known team member (silent observation)
        - UNKNOWN: Actor could not be determined (security fail-safe)
        - BLOCKED: Actor is known but not authorized

    Side Effects:
        - Logs INFO message when actor is self
        - Logs DEBUG message when actor is a team member
        - Logs WARNING message when actor is unknown or blocked
    """
    prefix = f"{action_type}: " if action_type else ""
    team_usernames = team_usernames or []

    if actor is None:
        logger.warning(
            f"{prefix}BLOCKED - Could not determine actor for {context_key}. Skipping for security."
        )
        return ActorCategory.UNKNOWN

    if actor == username_self:
        logger.info(f"{prefix}Action by self ('{actor}') for {context_key}")
        return ActorCategory.SELF

    if actor in team_usernames:
        logger.debug(
            f"{prefix}Action by team member ('{actor}') for {context_key}. Observing silently."
        )
        return ActorCategory.TEAM

    logger.warning(
        f"{prefix}BLOCKED - Action by '{actor}' not allowed for {context_key} "
        f"(username_self: {username_self})."
    )
    return ActorCategory.BLOCKED
