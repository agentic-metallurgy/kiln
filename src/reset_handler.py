"""Reset label handling for the daemon.

This module provides the ResetHandler class that manages the reset label functionality.
When a user adds the 'reset' label to an issue, the handler clears kiln-generated
content, closes open PRs, deletes branches, and moves the issue back to Backlog.
"""

import re
import subprocess
from pathlib import Path

from src.daemon_utils import get_hostname_from_url, get_worktree_path
from src.labels import Labels
from src.logger import get_logger
from src.security import ActorCategory, check_actor_allowed

logger = get_logger(__name__)


class ResetHandler:
    """Manages reset label handling for issues.

    When the 'reset' label is added to an issue by an authorized user, this class:
    1. Validates the label was added by an allowed user
    2. Removes the reset label
    3. Cleans up the worktree
    4. Closes open PRs and deletes their branches
    5. Removes PR-issue linking keywords
    6. Clears kiln-generated content from the issue body
    7. Removes all labels from the issue
    8. Moves the issue to Backlog status
    """

    def __init__(
        self,
        ticket_client,
        workspace_manager,
        username_self: str,
        team_usernames: list[str] | None = None,
        workspace_dir: str = "",
    ) -> None:
        """Initialize reset handler.

        Args:
            ticket_client: GitHub ticket client for API operations
            workspace_manager: Workspace manager for worktree cleanup
            username_self: The username of the daemon (for actor authorization)
            team_usernames: List of authorized team usernames (optional)
            workspace_dir: Base workspace directory path
        """
        self.ticket_client = ticket_client
        self.workspace_manager = workspace_manager
        self.username_self = username_self
        self.team_usernames = team_usernames or []
        self.workspace_dir = workspace_dir
        logger.debug(
            f"ResetHandler initialized (username_self={username_self}, "
            f"workspace_dir={workspace_dir})"
        )

    def maybe_handle_reset(self, item) -> None:
        """Handle the reset label by clearing kiln content and moving issue to Backlog.

        When a user adds the 'reset' label to an issue, this method:
        1. Validates the label was added by an allowed user
        2. Removes the 'reset' label
        3. Clears kiln-generated content (research/plan sections) from the issue body
        4. Removes workflow-related labels (research_ready, plan_ready, researching, planning)
        5. Moves the issue to Backlog status

        Args:
            item: TicketItem to check (with cached labels)
        """
        # Only process items with the reset label
        if Labels.RESET not in item.labels:
            return

        # Skip closed issues
        if item.state == "CLOSED":
            return

        key = f"{item.repo}#{item.ticket_id}"

        actor = self.ticket_client.get_label_actor(item.repo, item.ticket_id, Labels.RESET)
        actor_category = check_actor_allowed(
            actor, self.username_self, key, "RESET", self.team_usernames
        )
        if actor_category != ActorCategory.SELF:
            # Only remove reset label when actor is known but not allowed (to prevent repeated warnings)
            # When actor is unknown, keep the label for security logging visibility
            if actor_category == ActorCategory.BLOCKED or actor_category == ActorCategory.TEAM:
                self.ticket_client.remove_label(item.repo, item.ticket_id, Labels.RESET)
            return

        logger.info(
            f"RESET: Processing reset for {key} in '{item.status}' "
            f"(label added by allowed user '{actor}')"
        )

        # Remove the reset label first
        self.ticket_client.remove_label(item.repo, item.ticket_id, Labels.RESET)

        # Clean up worktree if it exists (prevents rebase failures on subsequent Research runs)
        repo_name = item.repo.split("/")[-1]
        worktree_path = get_worktree_path(self.workspace_dir, item.repo, item.ticket_id)
        if Path(worktree_path).exists():
            try:
                self.workspace_manager.cleanup_workspace(repo_name, item.ticket_id)
                logger.info(f"RESET: Cleaned up worktree for {key}")
            except Exception as e:
                logger.warning(f"RESET: Failed to cleanup worktree for {key}: {e}")

        # Close open PRs and delete their branches
        self._close_prs_and_delete_branches(item)

        # Remove linking keywords from related PRs (severs PR-issue relationship)
        self._remove_pr_issue_links(item)

        # Clear kiln-generated content from issue body
        self._clear_kiln_content(item)

        # Remove ALL labels from the issue
        for label in item.labels:
            try:
                self.ticket_client.remove_label(item.repo, item.ticket_id, label)
                logger.info(f"RESET: Removed '{label}' label from {key}")
            except Exception as e:
                logger.warning(f"RESET: Failed to remove '{label}' from {key}: {e}")

        # Move issue to Backlog
        try:
            hostname = get_hostname_from_url(item.board_url)
            self.ticket_client.update_item_status(item.item_id, "Backlog", hostname=hostname)
            logger.info(f"RESET: Moved {key} to Backlog")
        except Exception as e:
            logger.error(f"RESET: Failed to move {key} to Backlog: {e}")

    def _clear_kiln_content(self, item) -> None:
        """Clear kiln-generated content from an issue's body.

        Removes the research section (between <!-- kiln:research --> and <!-- /kiln:research -->)
        and the plan section (between <!-- kiln:plan --> and <!-- /kiln:plan -->) from the issue body,
        leaving only the original user-created description.

        Args:
            item: TicketItem whose body should be cleared
        """
        key = f"{item.repo}#{item.ticket_id}"

        # Get current issue body
        body = self.ticket_client.get_ticket_body(item.repo, item.ticket_id)
        if body is None:
            logger.warning(f"RESET: Could not get issue body for {key}")
            return

        original_body = body

        # Remove research section (including separator before it)
        # Pattern: optional separator (---) followed by research section
        research_pattern = r"\n*---\n*<!-- kiln:research -->.*?<!-- /kiln:research -->"
        body = re.sub(research_pattern, "", body, flags=re.DOTALL)

        # Remove plan section (including separator before it)
        plan_pattern = r"\n*---\n*<!-- kiln:plan -->.*?<!-- /kiln:plan -->"
        body = re.sub(plan_pattern, "", body, flags=re.DOTALL)

        # Also handle case where sections don't have separator
        research_pattern_no_sep = r"\n*<!-- kiln:research -->.*?<!-- /kiln:research -->"
        body = re.sub(research_pattern_no_sep, "", body, flags=re.DOTALL)

        plan_pattern_no_sep = r"\n*<!-- kiln:plan -->.*?<!-- /kiln:plan -->"
        body = re.sub(plan_pattern_no_sep, "", body, flags=re.DOTALL)

        # Handle legacy end marker (<!-- /kiln -->) for backwards compatibility
        # Research with legacy end marker and separator
        research_pattern_legacy = r"\n*---\n*<!-- kiln:research -->.*?<!-- /kiln -->"
        body = re.sub(research_pattern_legacy, "", body, flags=re.DOTALL)

        # Research with legacy end marker without separator
        research_pattern_legacy_no_sep = r"\n*<!-- kiln:research -->.*?<!-- /kiln -->"
        body = re.sub(research_pattern_legacy_no_sep, "", body, flags=re.DOTALL)

        # Plan with legacy end marker and separator
        plan_pattern_legacy = r"\n*---\n*<!-- kiln:plan -->.*?<!-- /kiln -->"
        body = re.sub(plan_pattern_legacy, "", body, flags=re.DOTALL)

        # Plan with legacy end marker without separator
        plan_pattern_legacy_no_sep = r"\n*<!-- kiln:plan -->.*?<!-- /kiln -->"
        body = re.sub(plan_pattern_legacy_no_sep, "", body, flags=re.DOTALL)

        # Clean up any trailing whitespace
        body = body.rstrip()

        # Only update if body actually changed
        if body == original_body:
            logger.info(f"RESET: No kiln content to clear from {key}")
            return

        # Update the issue body via gh CLI
        try:
            # Extract hostname and owner/repo from item.repo (format: hostname/owner/repo)
            parts = item.repo.split("/", 1)
            if len(parts) == 2:
                hostname, owner_repo = parts
                repo_ref = owner_repo if hostname == "github.com" else f"{hostname}/{owner_repo}"
            else:
                repo_ref = item.repo

            subprocess.run(
                ["gh", "issue", "edit", str(item.ticket_id), "--repo", repo_ref, "--body", body],
                capture_output=True,
                text=True,
                check=True,
            )
            logger.info(f"RESET: Cleared kiln content from {key}")
        except subprocess.CalledProcessError as e:
            logger.error(f"RESET: Failed to clear kiln content from {key}: {e.stderr}")

    def _close_prs_and_delete_branches(self, item) -> None:
        """Close open PRs and delete their branches for an issue during reset.

        Args:
            item: TicketItem being reset
        """
        key = f"{item.repo}#{item.ticket_id}"

        try:
            linked_prs = self.ticket_client.get_linked_prs(item.repo, item.ticket_id)
        except Exception as e:
            logger.warning(f"RESET: Failed to get linked PRs for {key}: {e}")
            return

        for pr in linked_prs:
            # Skip merged PRs - branch may be protected or needed
            if pr.merged:
                logger.debug(f"RESET: Skipping merged PR #{pr.number} for {key}")
                continue

            # Close the PR first
            if self.ticket_client.close_pr(item.repo, pr.number):
                # Verify PR is actually closed (fresh state check)
                pr_state = self.ticket_client.get_pr_state(item.repo, pr.number)
                if pr_state == "CLOSED":
                    logger.info(f"RESET: Verified PR #{pr.number} is closed for {key}")
                elif pr_state is None:
                    logger.warning(f"RESET: Could not verify PR #{pr.number} state for {key}")
                else:
                    logger.warning(
                        f"RESET: PR #{pr.number} close returned success but state is {pr_state} "
                        f"for {key}"
                    )
            else:
                logger.warning(f"RESET: Failed to close PR #{pr.number} for {key}")

            # Delete the branch if we have the name
            if pr.branch_name and self.ticket_client.delete_branch(item.repo, pr.branch_name):
                logger.info(f"RESET: Deleted branch '{pr.branch_name}' for {key}")

    def _remove_pr_issue_links(self, item) -> None:
        """Remove linking keywords from PRs that are linked to this issue.

        Finds all PRs that have linking keywords (closes, fixes, resolves, etc.)
        pointing to this issue and edits their bodies to remove the keyword
        while preserving the issue reference as a breadcrumb.

        This severs the automatic PR-issue link so merging the PR won't close
        the issue.

        Args:
            item: TicketItem whose linked PRs should be unlinked
        """
        key = f"{item.repo}#{item.ticket_id}"

        # Get all linked PRs
        try:
            linked_prs = self.ticket_client.get_linked_prs(item.repo, item.ticket_id)
        except Exception as e:
            logger.warning(f"RESET: Failed to get linked PRs for {key}: {e}")
            return

        if not linked_prs:
            logger.debug(f"RESET: No linked PRs found for {key}")
            return

        logger.info(f"RESET: Found {len(linked_prs)} linked PRs for {key}")

        # Remove linking keywords from each PR
        for pr in linked_prs:
            # Skip merged PRs - the link is already broken (issue was closed)
            if pr.merged:
                logger.debug(f"RESET: Skipping merged PR #{pr.number} for {key}")
                continue

            try:
                removed = self.ticket_client.remove_pr_issue_link(
                    item.repo, pr.number, item.ticket_id
                )
                if removed:
                    logger.info(f"RESET: Removed linking keyword from PR #{pr.number} for {key}")
                else:
                    logger.debug(
                        f"RESET: No linking keyword to remove from PR #{pr.number} for {key}"
                    )
            except Exception as e:
                logger.warning(
                    f"RESET: Failed to remove linking keyword from PR #{pr.number} for {key}: {e}"
                )
