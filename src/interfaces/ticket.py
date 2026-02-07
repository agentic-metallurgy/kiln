"""Abstract ticket client protocol and data types.

This module defines the interface that all ticket system integrations
must implement (GitHub, Jira, Linear, etc.).
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


@dataclass
class TicketItem:
    """Abstract representation of a ticket/issue on a board.

    Attributes:
        item_id: Unique identifier for the board item
        board_url: URL of the board/project this item belongs to
        ticket_id: Numeric identifier for the ticket
        repo: Repository identifier in format "hostname/owner/repo"
              (e.g., "github.com/owner/repo" or "github.example.com/owner/repo")
        status: Current status/column on the board
        title: Ticket title
        labels: Set of label names on the ticket
        state: Ticket state ("OPEN" or "CLOSED")
        state_reason: Reason for state (e.g., "COMPLETED", "NOT_PLANNED")
        has_merged_changes: Whether the ticket has merged code changes
        comment_count: Number of comments on the ticket
    """

    item_id: str
    board_url: str
    ticket_id: int
    repo: str
    status: str
    title: str
    labels: set[str] = field(default_factory=set)
    state: str = "OPEN"
    state_reason: str | None = None
    has_merged_changes: bool = False
    comment_count: int = 0


@dataclass
class Comment:
    """Abstract representation of a ticket comment.

    Attributes:
        id: Unique string identifier (node ID)
        database_id: Numeric identifier (database ID)
        body: Comment body text
        created_at: When the comment was created
        author: Username of the comment author
        is_processed: Whether the comment has been processed (e.g., thumbs up)
        is_processing: Whether the comment is currently being processed (e.g., eyes)
    """

    id: str
    database_id: int
    body: str
    created_at: datetime
    author: str
    is_processed: bool = False
    is_processing: bool = False


@dataclass
class LinkedPullRequest:
    """Abstract representation of a pull request linked to a ticket.

    Attributes:
        number: PR number
        url: Full URL to the PR
        body: PR description/body text
        state: PR state (OPEN, CLOSED, MERGED)
        merged: Whether the PR has been merged
        branch_name: Name of the PR's head branch (for cleanup operations)
        title: PR title for display purposes
    """

    number: int
    url: str
    body: str
    state: str
    merged: bool
    branch_name: str | None = None
    title: str | None = None


@runtime_checkable
class TicketClient(Protocol):
    """Protocol defining the interface for ticket system clients.

    All ticket system integrations (GitHub, Jira, Linear) must implement
    this protocol to work with the daemon and workflow system.
    """

    # Board operations
    def get_board_items(self, board_url: str) -> list[TicketItem]:
        """Get all items from a board/project."""
        ...

    def get_board_metadata(self, board_url: str) -> dict[str, Any]:
        """Get board metadata (status options, field IDs, etc.)."""
        ...

    def update_item_status(self, item_id: str, new_status: str) -> None:
        """Update the status/column of a board item."""
        ...

    def archive_item(self, board_id: str, item_id: str) -> bool:
        """Archive a board item. Returns True if successful."""
        ...

    # Ticket operations
    def get_ticket_body(self, repo: str, ticket_id: int) -> str | None:
        """Get the body/description of a ticket."""
        ...

    def get_ticket_labels(self, repo: str, ticket_id: int) -> set[str]:
        """Get the current labels on a ticket.

        Args:
            repo: Repository in hostname/owner/repo format
            ticket_id: Issue number

        Returns:
            Set of label names currently on the ticket, empty set if issue does not exist
        """
        ...

    def add_label(self, repo: str, ticket_id: int, label: str) -> None:
        """Add a label to a ticket."""
        ...

    def remove_label(self, repo: str, ticket_id: int, label: str) -> None:
        """Remove a label from a ticket."""
        ...

    # Repo label management
    def get_repo_labels(self, repo: str) -> list[str]:
        """Get all labels defined in a repo."""
        ...

    def create_repo_label(
        self, repo: str, name: str, description: str = "", color: str = ""
    ) -> bool:
        """Create a label in a repo. Returns True if successful."""
        ...

    # Comment operations
    def get_comments(self, repo: str, ticket_id: int) -> list[Comment]:
        """Get all comments on a ticket."""
        ...

    def get_comments_since(self, repo: str, ticket_id: int, since: str | None) -> list[Comment]:
        """Get comments created after a timestamp (ISO 8601)."""
        ...

    def add_comment(self, repo: str, ticket_id: int, body: str) -> Comment:
        """Add a comment to a ticket."""
        ...

    def add_reaction(self, comment_id: str, reaction: str, repo: str | None = None) -> None:
        """Add a reaction to a comment.

        Args:
            comment_id: Unique identifier for the comment
            reaction: Reaction type (e.g., THUMBS_UP, EYES)
            repo: Optional repository to help implementations determine the host
        """
        ...

    # Security/audit
    def get_last_status_actor(self, repo: str, ticket_id: int) -> str | None:
        """Get the username of who last changed the ticket's board status."""
        ...

    def get_label_actor(self, repo: str, ticket_id: int, label_name: str) -> str | None:
        """Get the username of who added a specific label to the ticket."""
        ...

    # PR operations (for reset functionality)
    def get_linked_prs(self, repo: str, ticket_id: int) -> list["LinkedPullRequest"]:
        """Get pull requests that are linked to close this ticket.

        Returns PRs that have linking keywords (closes, fixes, resolves, etc.)
        pointing to this issue.

        Args:
            repo: Repository in 'hostname/owner/repo' format
            ticket_id: Issue number

        Returns:
            List of LinkedPullRequest objects
        """
        ...

    def remove_pr_issue_link(self, repo: str, pr_number: int, issue_number: int) -> bool:
        """Remove the linking keyword from a PR body while preserving the issue reference.

        Edits the PR body to remove keywords like 'closes', 'fixes', 'resolves'
        while keeping the issue number as a breadcrumb (e.g., 'closes #44' -> '#44').

        Args:
            repo: Repository in 'hostname/owner/repo' format
            pr_number: PR number to edit
            issue_number: Issue number whose linking keyword should be removed

        Returns:
            True if the PR was edited, False if no linking keyword was found
        """
        ...

    def close_pr(self, repo: str, pr_number: int) -> bool:
        """Close a pull request without merging.

        Args:
            repo: Repository in 'hostname/owner/repo' format
            pr_number: PR number to close

        Returns:
            True if PR was closed successfully, False otherwise
        """
        ...

    def delete_branch(self, repo: str, branch_name: str) -> bool:
        """Delete a remote branch.

        Args:
            repo: Repository in 'hostname/owner/repo' format
            branch_name: Name of the branch to delete

        Returns:
            True if branch was deleted successfully, False otherwise
        """
        ...

    def get_pr_state(self, repo: str, pr_number: int) -> str | None:
        """Get the current state of a pull request.

        Fetches fresh state from the GitHub API for validation purposes.

        Args:
            repo: Repository in 'hostname/owner/repo' format
            pr_number: PR number to check

        Returns:
            PR state string: "OPEN", "CLOSED", or "MERGED"
            None on error (fail-safe - don't block workflow)
        """
        ...

    # Issue lifecycle operations
    def create_issue(self, repo: str, title: str, body: str) -> int:
        """Create a new issue and return its number.

        Args:
            repo: Repository in 'hostname/owner/repo' format
            title: Issue title
            body: Issue body/description

        Returns:
            The new issue number

        Raises:
            subprocess.CalledProcessError: If issue creation fails
        """
        ...
