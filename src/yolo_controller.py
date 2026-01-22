"""YOLO mode auto-progression controller for the daemon.

This module provides the YoloController class that manages YOLO label detection
and automatic workflow status progression. When an issue has the 'yolo' label,
it automatically advances through workflow stages without requiring manual status changes.
"""

from src.daemon_utils import get_hostname_from_url
from src.labels import Labels
from src.logger import get_logger
from src.security import ActorCategory, check_actor_allowed

logger = get_logger(__name__)


class YoloController:
    """Manages YOLO mode auto-progression logic.

    YOLO mode allows issues to automatically advance through workflow stages
    when the 'yolo' label is present. This class encapsulates the logic for
    checking whether an issue should advance and performing the advancement.
    """

    # YOLO mode auto-progression: maps current status to next status
    # When YOLO label is present, workflow completion advances to next status
    YOLO_PROGRESSION = {
        "Backlog": "Research",
        "Research": "Plan",
        "Plan": "Implement",
        # Implement → Validate is handled by existing WORKFLOW_CONFIG.next_status
    }

    def __init__(
        self,
        ticket_client,
        username_self: str,
        team_usernames: list[str] | None = None,
        workflow_config: dict | None = None,
    ) -> None:
        """Initialize YOLO controller.

        Args:
            ticket_client: GitHub ticket client for label operations
            username_self: The username of the daemon (for actor authorization)
            team_usernames: List of authorized team usernames (optional)
            workflow_config: Workflow configuration dict with complete_label info (optional)
        """
        self.ticket_client = ticket_client
        self.username_self = username_self
        self.team_usernames = team_usernames or []
        self.workflow_config = workflow_config or {}
        logger.debug(
            f"YoloController initialized (username_self={username_self}, "
            f"team_usernames={len(self.team_usernames)})"
        )

    def should_yolo_advance(self, item) -> bool:
        """Check if an item should advance via YOLO (has yolo label but can't run workflow).

        This handles the case where yolo is added after a workflow stage completes.
        For example, if yolo is added when an issue has research_ready label in Research status,
        it should advance to Plan.

        Args:
            item: TicketItem from GitHub (with cached labels)

        Returns:
            True if item should be advanced to next YOLO status
        """
        # Fast path: if not in cached labels, definitely not present
        if Labels.YOLO not in item.labels:
            return False

        # Skip closed issues
        if item.state == "CLOSED":
            return False

        # Must have a YOLO progression target
        if item.status not in self.YOLO_PROGRESSION:
            return False

        # Skip Backlog - handled separately in _poll() with immediate status change
        if item.status == "Backlog":
            return False

        # Must have the complete label for the current status (indicates stage is done)
        config = self.workflow_config.get(item.status)
        if not config:
            return False

        complete_label = config["complete_label"]
        if not (complete_label and complete_label in item.labels):
            return False

        # Fresh check: verify yolo label is still present (may have been removed since poll started)
        if not self.has_yolo_label(item.repo, item.ticket_id):
            key = f"{item.repo}#{item.ticket_id}"
            logger.debug(f"YOLO: Skipping advancement for {key} - yolo label was removed")
            return False

        return True

    def yolo_advance(self, item) -> None:
        """Advance an item to the next YOLO status.

        Validates that the yolo label was added by an allowed user before advancing.
        Also verifies the label is still present (fresh check) in case it was removed
        after should_yolo_advance() returned True but before this method runs.

        Args:
            item: TicketItem to advance
        """
        key = f"{item.repo}#{item.ticket_id}"
        yolo_next = self.YOLO_PROGRESSION.get(item.status)

        if not yolo_next:
            return

        # Fresh check: verify yolo label is still present before advancing
        if not self.has_yolo_label(item.repo, item.ticket_id):
            logger.info(f"YOLO: Skipping advancement for {key} - yolo label was removed")
            return

        actor = self.ticket_client.get_label_actor(item.repo, item.ticket_id, Labels.YOLO)
        actor_category = check_actor_allowed(
            actor, self.username_self, key, "YOLO", self.team_usernames
        )
        if actor_category != ActorCategory.SELF:
            return

        logger.info(
            f"YOLO: Advancing {key} from '{item.status}' to '{yolo_next}' "
            f"(stage complete, label added by allowed user '{actor}')"
        )
        hostname = get_hostname_from_url(item.board_url)
        self.ticket_client.update_item_status(item.item_id, yolo_next, hostname=hostname)

    def has_yolo_label(self, repo: str, issue_number: int) -> bool:
        """Check if issue currently has yolo label (fresh from GitHub).

        This fetches fresh label data from GitHub to handle the case where
        a user removes the yolo label mid-workflow. Using cached item.labels
        would miss this change.

        Args:
            repo: Repository in 'hostname/owner/repo' format
            issue_number: Issue number

        Returns:
            True if yolo label is currently present, False otherwise.
            Returns False on any error (fail-safe: don't advance if uncertain).
        """
        try:
            current_labels = self.ticket_client.get_issue_labels(repo, issue_number)
            return Labels.YOLO in current_labels
        except Exception as e:
            logger.warning(f"Could not fetch current labels for {repo}#{issue_number}: {e}")
            return False  # Fail safe - don't advance if we can't verify
