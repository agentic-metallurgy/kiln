"""Issue state management for the daemon.

This module provides the StateManager class that handles issue lifecycle
transitions, cleanup operations, and state normalization. It manages:
- Worktree cleanup for completed and closed issues
- Archiving closed issues that weren't completed
- Moving validated issues with merged PRs to Done
- Setting default Backlog status for new issues
- Cleaning up running workflow labels on shutdown
"""

import threading
from pathlib import Path

from src.daemon_utils import get_hostname_from_url, get_worktree_path
from src.labels import Labels
from src.logger import get_logger

logger = get_logger(__name__)


class StateManager:
    """Manages issue state transitions and cleanup operations.

    This class handles lifecycle transitions for issues on the project board:
    - Cleanup for Done issues (removes worktree, adds cleaned_up label)
    - Archiving closed issues (won't do, duplicate, manual close)
    - Cleanup for closed issues without Done status
    - Moving Validate issues with merged PRs to Done
    - Setting Backlog status for new issues without a status
    - Cleaning up running workflow labels on graceful shutdown
    """

    def __init__(
        self,
        ticket_client,
        workspace_manager,
        project_metadata: dict,
        running_labels: dict[str, str],
        running_labels_lock: threading.Lock,
        workspace_dir: str = "",
    ) -> None:
        """Initialize state manager.

        Args:
            ticket_client: GitHub ticket client for API operations
            workspace_manager: Workspace manager for worktree cleanup
            project_metadata: Dict mapping project URLs to ProjectMetadata objects
            running_labels: Dict tracking issues with running workflow labels
            running_labels_lock: Lock for thread-safe access to running_labels
            workspace_dir: Base workspace directory path
        """
        self.ticket_client = ticket_client
        self.workspace_manager = workspace_manager
        self.project_metadata = project_metadata
        self.running_labels = running_labels
        self.running_labels_lock = running_labels_lock
        self.workspace_dir = workspace_dir
        logger.debug(f"StateManager initialized (workspace_dir={workspace_dir})")

    def maybe_cleanup(self, item) -> None:
        """Clean up worktree for Done issues.

        Uses 'cleaned_up' label to externalize cleanup state.
        Uses cached labels from TicketItem to avoid API calls.

        Args:
            item: TicketItem in Done status (with cached labels)
        """
        # Skip if already cleaned up - use cached labels
        if Labels.CLEANED_UP in item.labels:
            return

        # Clean up worktree if it exists
        repo_name = item.repo.split("/")[-1]
        worktree_path = get_worktree_path(self.workspace_dir, item.repo, item.ticket_id)
        if Path(worktree_path).exists():
            try:
                self.workspace_manager.cleanup_workspace(repo_name, item.ticket_id)
                logger.info("Cleaned up worktree")
            except Exception as e:
                logger.error(f"Cleanup failed: {e}")

        # Mark as cleaned up (prevents repeated checks)
        self.ticket_client.add_label(item.repo, item.ticket_id, Labels.CLEANED_UP)

    def maybe_archive_closed(self, item) -> None:
        """Archive project items for issues closed without actual completion.

        Archives issues closed as:
        - NOT_PLANNED (won't do)
        - DUPLICATE
        - null/manual close (no state_reason)
        - COMPLETED but without a merged PR (manual close as "completed")

        Only issues closed as COMPLETED with a merged PR go to Done.
        Uses cached issue state from TicketItem to avoid API calls.

        Args:
            item: TicketItem to check and potentially archive (with cached state)
        """
        # Only process closed issues
        if item.state != "CLOSED":
            return

        # COMPLETED with merged PR goes to Done, not archived
        if item.state_reason == "COMPLETED" and item.has_merged_changes:
            return

        # Get project metadata for the project ID
        metadata = self.project_metadata.get(item.board_url)
        if not metadata or not metadata.project_id:
            logger.warning(f"No project metadata for {item.board_url}, cannot archive")
            return

        # Archive the project item
        reason = item.state_reason or "manual close"
        logger.info(f"Auto-archiving issue (reason: {reason})")
        hostname = get_hostname_from_url(item.board_url)
        if self.ticket_client.archive_item(metadata.project_id, item.item_id, hostname=hostname):
            logger.info("Archived from project board")

    def maybe_cleanup_closed(self, item) -> None:
        """Clean up worktree for any closed issue.

        This handles closed issues that didn't go through the Done status,
        including manually closed issues and issues closed without merged PRs.
        Non-completed issues are archived by maybe_archive_closed() before this.

        Uses 'cleaned_up' label to externalize cleanup state and prevent
        repeated processing.

        Args:
            item: TicketItem to check (with cached labels and state)
        """
        # Only process closed issues
        if item.state != "CLOSED":
            return

        # Skip if already cleaned up - use cached labels
        if Labels.CLEANED_UP in item.labels:
            return

        # Clean up worktree if it exists
        repo_name = item.repo.split("/")[-1]
        worktree_path = get_worktree_path(self.workspace_dir, item.repo, item.ticket_id)
        if Path(worktree_path).exists():
            try:
                self.workspace_manager.cleanup_workspace(repo_name, item.ticket_id)
                logger.info("Cleaned up worktree for closed issue")
            except Exception as e:
                logger.error(f"Cleanup failed for closed issue: {e}")

        # Mark as cleaned up (prevents repeated checks)
        self.ticket_client.add_label(item.repo, item.ticket_id, Labels.CLEANED_UP)

    def maybe_move_to_done(self, item) -> None:
        """Move issues to Done when PR is merged and issue is closed as COMPLETED.

        Conditions:
        - Item is not already in "Done" status
        - Item is closed as COMPLETED (others are archived instead)
        - Item has at least one merged PR
        - Item is closed (GitHub auto-closes when PR with "closes #X" merges)

        Args:
            item: TicketItem to check
        """
        # Skip items already in Done
        if item.status == "Done":
            return

        # Only process COMPLETED issues (others are archived by maybe_archive_closed)
        if item.state_reason != "COMPLETED":
            return

        # Must have merged PR
        if not item.has_merged_changes:
            return

        # Must be closed
        if item.state != "CLOSED":
            return

        # Move to Done
        logger.info(f"Moving {item.repo}#{item.ticket_id} to Done (PR merged, issue closed)")
        try:
            hostname = get_hostname_from_url(item.board_url)
            self.ticket_client.update_item_status(item.item_id, "Done", hostname=hostname)
            logger.info(f"Moved {item.repo}#{item.ticket_id} to Done")
        except Exception as e:
            logger.error(f"Failed to move {item.repo}#{item.ticket_id} to Done: {e}")

    def maybe_set_backlog(self, item) -> None:
        """Set issues without a status to Backlog.

        When an issue is added to the project board but not assigned a status,
        it shows as "Unknown" in our query. This sets it to Backlog.

        Args:
            item: TicketItem to check
        """
        # Only process items with no status set
        if item.status != "Unknown":
            return

        # Skip closed issues
        if item.state == "CLOSED":
            return

        # Set to Backlog
        logger.info(f"Setting {item.repo}#{item.ticket_id} to Backlog (no status)")
        try:
            hostname = get_hostname_from_url(item.board_url)
            self.ticket_client.update_item_status(item.item_id, "Backlog", hostname=hostname)
            logger.info(f"Set {item.repo}#{item.ticket_id} to Backlog")
        except Exception as e:
            logger.error(f"Failed to set {item.repo}#{item.ticket_id} to Backlog: {e}")

    def cleanup_running_labels(self) -> None:
        """Remove running workflow labels from issues on graceful shutdown.

        This prevents "implementing" (and other running labels) from being left
        on issues when the daemon shuts down, which would otherwise block
        future workflow runs until manually removed.

        Errors during cleanup are logged but don't fail the shutdown.
        """
        with self.running_labels_lock:
            if not self.running_labels:
                logger.debug("No running workflow labels to clean up")
                return

            labels_to_clean = dict(self.running_labels)

        logger.info(f"Cleaning up {len(labels_to_clean)} running workflow label(s)...")

        for key, label in labels_to_clean.items():
            try:
                # Parse key back to repo and issue_number
                # Format: "hostname/owner/repo#issue_number"
                repo, issue_str = key.rsplit("#", 1)
                issue_number = int(issue_str)

                self.ticket_client.remove_label(repo, issue_number, label)
                logger.info(f"Removed '{label}' label from {key} during shutdown")

                # Remove from tracking
                with self.running_labels_lock:
                    self.running_labels.pop(key, None)

            except Exception as e:
                # Don't fail shutdown if label removal fails
                logger.warning(f"Failed to remove '{label}' label from {key} during shutdown: {e}")
