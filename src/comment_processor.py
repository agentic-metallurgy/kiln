"""Comment processing module for agentic-metallurgy.

This module handles processing user comments on GitHub issues, including:
- Fetching and filtering new comments
- Applying user feedback via Claude workflows
- Generating and posting diff responses
"""

import difflib
import html
import json
import subprocess
import textwrap
from typing import TYPE_CHECKING

from src.database import Database
from src.interfaces import Comment, TicketClient, TicketItem
from src.labels import Labels
from src.logger import clear_issue_context, get_logger, set_issue_context
from src.workflows import ProcessCommentsWorkflow, WorkflowContext

if TYPE_CHECKING:
    from src.daemon import WorkflowRunner

logger = get_logger(__name__)


class CommentProcessor:
    """Handles user comment fetching, filtering, and processing.

    This class processes user feedback on kiln-generated posts (research/plan sections)
    by running Claude workflows to apply requested changes and posting diffs.
    """

    # Bot usernames for logging categorization (not filtered - allowlist handles this)
    BOT_USERNAMES = {"kiln-bot", "github-actions[bot]"}

    # HTML comment markers for kiln posts (guaranteed idempotent identification)
    KILN_POST_MARKERS = {
        "research": "<!-- kiln:research -->",
        "plan": "<!-- kiln:plan -->",
    }
    KILN_POST_END_MARKERS = {
        "research": "<!-- /kiln:research -->",
        "plan": "<!-- /kiln:plan -->",
    }
    # Legacy end marker (for backwards compatibility during transition)
    KILN_POST_END_MARKER = "<!-- /kiln -->"

    # Marker for kiln response comments (diff replies to user feedback)
    KILN_RESPONSE_MARKER = "<!-- kiln:response -->"

    # Legacy markers for backwards compatibility (visible headers)
    KILN_POST_LEGACY_MARKERS = {
        "research": "## Research Findings",
        "plan": "## Implementation Plan",
    }

    def __init__(
        self,
        ticket_client: TicketClient,
        database: Database,
        runner: "WorkflowRunner",
        workspace_dir: str,
        username_self: str | None = None,
        team_usernames: list[str] | None = None,
    ) -> None:
        """Initialize the comment processor.

        Args:
            ticket_client: Ticket system client for fetching/posting comments
            database: Database for tracking processed comments
            runner: WorkflowRunner for executing Claude workflows
            workspace_dir: Base directory for worktrees
            username_self: Username allowed to trigger comment processing
            team_usernames: List of team member usernames (logged at DEBUG, not WARNING)
        """
        self.ticket_client = ticket_client
        self.database = database
        self.runner = runner
        self.workspace_dir = workspace_dir
        self.username_self = username_self
        self.team_usernames = team_usernames or []
        logger.debug("CommentProcessor initialized")

    def _get_worktree_path(self, repo: str, issue_number: int) -> str:
        """Get the worktree path for a repo and issue.

        Args:
            repo: Repository in 'owner/repo' format
            issue_number: Issue number

        Returns:
            Path to the worktree directory
        """
        repo_name = repo.split("/")[-1] if "/" in repo else repo
        return f"{self.workspace_dir}/{repo_name}-issue-{issue_number}"

    def process(self, item: TicketItem) -> None:
        """Process unprocessed user comments for a single issue.

        This is the main entry point, called from the Daemon's thread pool.

        Args:
            item: The project item to process comments for
        """
        # Set logging context for comment processing
        set_issue_context(item.repo, item.ticket_id)

        # Skip comment processing entirely for Backlog items - nothing to edit there
        if item.status == "Backlog":
            logger.debug("Skipping comment processing for Backlog item")
            return

        try:
            # Get the last processed timestamp from database
            stored_state = self.database.get_issue_state(item.repo, item.ticket_id)
            last_timestamp = stored_state.last_processed_comment_timestamp if stored_state else None
            last_known_count = stored_state.last_known_comment_count if stored_state else None

            # Quick check: if comment count hasn't changed, skip REST API call
            if last_known_count is not None and item.comment_count == last_known_count:
                logger.debug(f"No new comments (count={item.comment_count})")
                return

            # If no timestamp, need to initialize from existing comments
            if last_timestamp is None:
                # Fetch all comments to find the latest processed one
                all_comments = self.ticket_client.get_comments(item.repo, item.ticket_id)
                if all_comments:
                    # Find latest kiln post or thumbs-up comment to set as starting point
                    last_timestamp = self._initialize_comment_timestamp(item, all_comments)
                    if last_timestamp:
                        self.database.update_issue_state(
                            item.repo,
                            item.ticket_id,
                            item.status,
                            last_processed_comment_timestamp=last_timestamp,
                            last_known_comment_count=item.comment_count,
                            project_url=item.board_url,
                        )

            # Fetch only comments since the last processed timestamp (REST API optimization)
            logger.debug(f"Fetching comments since {last_timestamp}")
            new_comments = self.ticket_client.get_comments_since(
                item.repo, item.ticket_id, last_timestamp
            )

            if not new_comments:
                logger.debug("No new comments")
                return

            # Determine target type: try plan first, then research, fallback to description
            target_type = self._get_target_type(item)

            # Filter out bot comments, kiln posts, kiln responses, already-processed comments (thumbs up),
            # comments being processed by another thread (eyes reaction), and non-allowed users
            # Check for both new HTML markers and legacy visible markers
            all_markers = tuple(self.KILN_POST_MARKERS.values()) + tuple(
                self.KILN_POST_LEGACY_MARKERS.values()
            )

            # Log filtered comments with appropriate severity:
            # - Team member comments: DEBUG (silent in normal operation)
            # - Unknown/blocked user comments: WARNING (audit trail)
            team_authors: set[str] = set()
            blocked_authors: set[str] = set()
            for c in new_comments:
                if c.author not in self.BOT_USERNAMES and c.author != self.username_self:
                    if c.author in self.team_usernames:
                        team_authors.add(c.author)
                    else:
                        blocked_authors.add(c.author)
            if team_authors:
                logger.debug(
                    f"Filtered out comments from team members: {team_authors}. "
                    "Team member comments are observed silently."
                )
            if blocked_authors:
                logger.warning(
                    f"BLOCKED: Filtered out comments from non-allowed users: {blocked_authors}. "
                    f"Allowed username: {self.username_self}"
                )

            user_comments = [
                c
                for c in new_comments
                if c.author == self.username_self  # Must be from allowed username
                and not self._is_kiln_post(c.body, all_markers)
                and not self._is_kiln_response(c.body)
                and not c.is_processed  # Skip already-processed comments
                and not c.is_processing  # Skip comments being processed by another thread
            ]

            if not user_comments:
                logger.debug(f"All {len(new_comments)} comments filtered out")
                # Update stored count even when no actionable comments, to avoid re-checking
                self.database.update_issue_state(
                    item.repo,
                    item.ticket_id,
                    item.status,
                    last_known_comment_count=item.comment_count,
                    project_url=item.board_url,
                )
                return

            logger.info(f"Processing {len(user_comments)} user comment(s) (target: {target_type})")

            # Add editing label to indicate we're processing comments
            self.ticket_client.add_label(item.repo, item.ticket_id, Labels.EDITING)

            # Add eyes reaction to all comments to indicate we're processing them
            for comment in user_comments:
                try:
                    self.ticket_client.add_reaction(comment.id, "EYES", repo=item.repo)
                except Exception as e:
                    logger.warning(f"Failed to add eyes reaction to {comment.database_id}: {e}")

            # Merge multiple comments into one, with later comments taking precedence
            # for any conflicting instructions
            if len(user_comments) == 1:
                merged_body = user_comments[0].body
            else:
                # Combine comments chronologically, noting which is latest for conflict resolution
                comment_parts = []
                for i, comment in enumerate(user_comments, 1):
                    comment_parts.append(f"[Comment {i} of {len(user_comments)}]:\n{comment.body}")
                merged_body = (
                    "Multiple user comments to apply (in chronological order). "
                    "If there are conflicting instructions, prefer the LATER comments as they are likely corrections:\n\n"
                    + "\n\n---\n\n".join(comment_parts)
                )
                logger.info(f"Merged {len(user_comments)} comments")

            workspace_path = self._get_worktree_path(item.repo, item.ticket_id)

            # Capture BEFORE state of the target section
            before_content = self._extract_section_content(item.repo, item.ticket_id, target_type)

            try:
                # Create a synthetic comment with merged body for processing
                merged_comment = Comment(
                    id=user_comments[-1].id,  # Use last comment's ID
                    database_id=user_comments[-1].database_id,
                    body=merged_body,
                    created_at=user_comments[-1].created_at,
                    author=user_comments[-1].author,
                    is_processed=False,
                )
                self._apply_comment_to_kiln_post(item, merged_comment, target_type, workspace_path)

                # Capture AFTER state and generate diff
                after_content = self._extract_section_content(
                    item.repo, item.ticket_id, target_type
                )
                diff_text = self._generate_diff(before_content, after_content, target_type)
                if diff_text:
                    diff_text = self._wrap_diff(diff_text)

                # Post response comment with diff (always collapsed)
                # Use HTML <pre> with escaping to prevent diff content from breaking the markup
                if diff_text:
                    escaped_diff = html.escape(diff_text)
                    response_body = f"""{self.KILN_RESPONSE_MARKER}
Applied changes to **{target_type}**:

<details>
<summary>Diff</summary>

<pre lang="diff">
{escaped_diff}
</pre>

</details>
"""
                else:
                    response_body = f"""{self.KILN_RESPONSE_MARKER}
Processed feedback for **{target_type}**. No textual changes detected (may have been a formatting or structural update).
"""
                response_comment = self.ticket_client.add_comment(
                    item.repo, item.ticket_id, response_body
                )

                # React with thumbs up to ALL comments to indicate successful processing
                for comment in user_comments:
                    try:
                        self.ticket_client.add_reaction(comment.id, "THUMBS_UP", repo=item.repo)
                    except Exception as e:
                        logger.warning(f"Failed to add thumbs up to {comment.database_id}: {e}")

                # Update last processed to the RESPONSE comment (past both user comment and our reply)
                self.database.update_issue_state(
                    item.repo,
                    item.ticket_id,
                    item.status,
                    last_processed_comment_timestamp=response_comment.created_at.isoformat(),
                    last_known_comment_count=item.comment_count
                    + 1,  # +1 for the response we just posted
                    project_url=item.board_url,
                )
                logger.info(f"Processed {len(user_comments)} comment(s)")
            except Exception as e:
                logger.error(f"Failed to process comments: {e}")
            finally:
                # Always remove editing label when done (success or failure)
                try:
                    self.ticket_client.remove_label(item.repo, item.ticket_id, Labels.EDITING)
                except Exception as e:
                    logger.warning(f"Failed to remove editing label: {e}")
        finally:
            clear_issue_context()

    def _is_kiln_post(self, body: str, markers: tuple[str, ...]) -> bool:
        """Check if a comment body is a kiln-generated post.

        Checks if the body starts with any of the given markers (after stripping whitespace).

        Args:
            body: The comment body to check
            markers: Tuple of marker strings to check for

        Returns:
            True if this is a kiln post, False otherwise
        """
        stripped = body.lstrip()
        return any(stripped.startswith(marker) for marker in markers)

    def _is_kiln_response(self, body: str) -> bool:
        """Check if a comment body is a kiln response comment.

        Response comments are kiln's replies showing diffs after applying
        user feedback. These should not be processed as user feedback.

        Args:
            body: The comment body to check

        Returns:
            True if this is a kiln response, False otherwise
        """
        return body.lstrip().startswith(self.KILN_RESPONSE_MARKER)

    def _generate_diff(self, before: str, after: str, target_type: str) -> str:
        """Generate a unified diff between before and after content.

        Args:
            before: Content before changes
            after: Content after changes
            target_type: The section type ("description", "research", "plan")

        Returns:
            Unified diff string formatted for markdown display
        """
        before_lines = before.splitlines()
        after_lines = after.splitlines()

        diff_lines = list(
            difflib.unified_diff(
                before_lines,
                after_lines,
                fromfile=f"{target_type} (before)",
                tofile=f"{target_type} (after)",
                lineterm="",
            )
        )

        if not diff_lines:
            return ""

        # Skip the --- and +++ header lines, just show the hunks
        # Start from index 2 to skip the file headers
        return "\n".join(diff_lines[2:])

    def _wrap_diff_line(self, line: str, width: int = 70) -> str:
        """Wrap a single diff line to fit within width, preserving diff prefix.

        Args:
            line: A single line from unified diff output
            width: Maximum line width (default 70)

        Returns:
            The line wrapped to fit within width, with diff prefix preserved
        """
        if not line or len(line) <= width:
            return line

        # Don't wrap hunk headers
        if line.startswith("@@"):
            return line

        # Determine diff prefix (+, -, or space for context)
        prefix = ""
        if line[0] in ("+", "-", " "):
            prefix = line[0]
            content = line[1:]
        else:
            content = line

        # Wrap content, continuation lines get the same prefix
        wrapped = textwrap.wrap(
            content,
            width=width - len(prefix),
            break_long_words=True,
            break_on_hyphens=False,
        )
        return "\n".join(prefix + part for part in wrapped)

    def _wrap_diff(self, diff_text: str, width: int = 70) -> str:
        """Wrap all lines in a diff to fit within width.

        Args:
            diff_text: Complete diff output
            width: Maximum line width (default 70)

        Returns:
            Diff with all lines wrapped
        """
        lines = diff_text.split("\n")
        wrapped_lines = [self._wrap_diff_line(line, width) for line in lines]
        return "\n".join(wrapped_lines)

    def _extract_section_content(self, repo: str, issue_number: int, target_type: str) -> str:
        """Extract the content of a specific section from the issue description.

        Args:
            repo: Repository in 'hostname/owner/repo' format
            issue_number: Issue number
            target_type: Section type ("description", "research", "plan")

        Returns:
            The section content, or empty string if not found
        """
        # Get issue body via gh CLI using full URL (works for github.com and GHES)
        # repo is in hostname/owner/repo format
        try:
            issue_url = f"https://{repo}/issues/{issue_number}"
            proc = subprocess.run(
                ["gh", "issue", "view", issue_url, "--json", "body"],
                capture_output=True,
                text=True,
                check=True,
            )
            body: str = json.loads(proc.stdout).get("body", "") or ""
        except Exception:
            return ""

        if target_type == "description":
            # Return everything before the first kiln section
            for marker in self.KILN_POST_MARKERS.values():
                if marker in body:
                    idx = body.find(marker)
                    # Find the --- separator before the marker
                    sep_idx = body.rfind("---", 0, idx)
                    if sep_idx != -1:
                        return str(body[:sep_idx].strip())
                    return str(body[:idx].strip())
            return str(body.strip())

        # For research/plan, extract the section between markers
        start_marker = self.KILN_POST_MARKERS.get(target_type)
        end_marker = self.KILN_POST_END_MARKERS.get(target_type)
        if not start_marker or not end_marker:
            return ""

        start_idx = body.find(start_marker)
        if start_idx == -1:
            return ""

        end_idx = body.find(end_marker, start_idx)
        if end_idx == -1:
            # Try legacy end marker
            end_idx = body.find(self.KILN_POST_END_MARKER, start_idx)

        if end_idx == -1:
            return str(body[start_idx + len(start_marker) :].strip())

        return str(body[start_idx + len(start_marker) : end_idx].strip())

    def _initialize_comment_timestamp(self, _item: TicketItem, comments: list[Comment]) -> str | None:
        """Initialize the comment timestamp pointer using cached comments.

        Returns timestamp for use with the REST API's `since` parameter.

        Finds the latest "processed" comment timestamp, which is either:
        1. The latest kiln post (research/plan) - these should never be processed
        2. The latest user comment with a thumbs up reaction - already processed

        Args:
            item: The project item to initialize
            comments: Pre-fetched list of comments

        Returns:
            ISO 8601 timestamp of the latest processed comment, or None if no comments
        """
        if not comments:
            return None

        # Build markers for identifying kiln posts
        all_markers = tuple(self.KILN_POST_MARKERS.values()) + tuple(
            self.KILN_POST_LEGACY_MARKERS.values()
        )
        all_end_markers = tuple(self.KILN_POST_END_MARKERS.values()) + (self.KILN_POST_END_MARKER,)

        # Scan comments in reverse (newest first) to find latest processed
        for comment in reversed(comments):
            # Check if it's a kiln post (by start marker or end marker)
            is_kiln = self._is_kiln_post(comment.body, all_markers) or any(
                marker in comment.body for marker in all_end_markers
            )

            # Check if it's an already-processed user comment (has thumbs up)
            is_processed_user_comment = comment.is_processed

            if is_kiln or is_processed_user_comment:
                timestamp = comment.created_at.isoformat()
                logger.debug(
                    f"Initialized comment timestamp to {timestamp} "
                    f"(kiln={is_kiln}, thumbs_up={is_processed_user_comment})"
                )
                return timestamp

        return None

    def _get_target_type(self, item: TicketItem) -> str:
        """Get the target type for editing based on issue status.

        With description-based storage, target is determined by status alone.

        Args:
            item: The project item

        Returns:
            Target type: "plan", "research", or "description"
        """
        # For Plan status, target the plan section
        if item.status == "Plan":
            return "plan"

        # For Research status, target the research section
        if item.status == "Research":
            return "research"

        # Fallback to description for other cases
        return "description"

    def _apply_comment_to_kiln_post(
        self, item: TicketItem, comment: Comment, target_type: str, workspace_path: str
    ) -> None:
        """Apply a user comment to edit the target (description, research, or plan).

        Args:
            item: The project item
            comment: The user comment to apply
            target_type: The target type ("description", "research", or "plan")
            workspace_path: Path to the worktree
        """
        # Determine parent workflow based on target type
        parent_workflow = {
            "research": "Research",
            "plan": "Plan",
            "description": None,  # No session for description edits
        }.get(target_type)

        # Look up parent session ID if applicable
        resume_session = None
        if parent_workflow:
            resume_session = self.database.get_workflow_session_id(
                item.repo, item.ticket_id, parent_workflow
            )
            if resume_session:
                logger.info(
                    f"Resuming {parent_workflow} session for comment: {resume_session[:8]}..."
                )
            else:
                logger.info(f"No prior {parent_workflow} session found, starting fresh for comment")

        # Create context with comment details
        ctx = WorkflowContext(
            repo=item.repo,
            issue_number=item.ticket_id,
            issue_title=item.title,
            workspace_path=workspace_path,
            project_url=item.board_url,
            comment_body=comment.body,
            target_type=target_type,
        )

        # Run the comment processing workflow
        workflow = ProcessCommentsWorkflow()
        session_id = self.runner.run(workflow, ctx, "process_comments", resume_session)

        # Store updated session ID if we got one (must be a proper string)
        if session_id and parent_workflow and isinstance(session_id, str):
            self.database.set_workflow_session_id(
                item.repo, item.ticket_id, parent_workflow, session_id
            )
            logger.info(f"Saved updated {parent_workflow} session: {session_id[:8]}...")
