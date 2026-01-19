# Implementing a Ticket Client

This guide explains how to implement a `TicketClient` for a new kanban/ticket system (Jira, Linear, Asana, etc.).

## Overview

The `TicketClient` protocol defines the interface between kiln and external ticket systems. Implementations live in `src/ticket_clients/<provider>.py`.

```
src/
  interfaces/
    ticket.py          # Protocol definition, TicketItem, Comment
  ticket_clients/
    github.py          # GitHub Projects implementation
    jira.py            # Your Jira implementation
    linear.py          # Your Linear implementation
```

## Core Data Types

### TicketItem

Represents a ticket/issue on a board. Your implementation must map provider-specific fields to these:

```python
@dataclass
class TicketItem:
    item_id: str              # Unique board item ID (e.g., Jira issue key "PROJ-123")
    board_url: str            # URL of the board/project
    ticket_id: int            # Numeric ticket identifier
    repo: str                 # Repository identifier ("owner/repo" format)
    status: str               # Current column/status (e.g., "In Progress")
    title: str                # Ticket title
    labels: set[str]          # Set of label/tag names
    state: str = "OPEN"       # "OPEN" or "CLOSED"
    state_reason: str | None  # "COMPLETED", "NOT_PLANNED", etc.
    has_merged_changes: bool  # Whether linked PRs/MRs are merged
    comment_count: int        # Number of comments
```

### Comment

Represents a comment on a ticket:

```python
@dataclass
class Comment:
    id: str                   # Unique comment identifier
    database_id: int          # Numeric ID (for ordering/pagination)
    body: str                 # Comment text (markdown)
    created_at: datetime      # UTC timestamp
    author: str               # Username of author
    is_processed: bool        # Has "processed" marker (e.g., thumbs up reaction)
    is_processing: bool       # Has "in progress" marker (e.g., eyes reaction)
```

## Required Methods

### Board Operations

```python
def get_board_items(self, board_url: str) -> list[TicketItem]:
    """Fetch all tickets from a board.

    Called during each polling cycle to discover work.
    Should return tickets in all statuses (backlog, in progress, done, etc.).
    """

def get_board_metadata(self, board_url: str) -> dict:
    """Fetch board configuration.

    Returns:
        {
            "project_id": str,           # Board's unique ID
            "status_field_id": str,      # ID of the status field
            "status_options": {          # Map of status name -> status ID
                "Backlog": "status_id_1",
                "Research": "status_id_2",
                ...
            }
        }
    """

def update_item_status(self, item_id: str, new_status: str) -> None:
    """Move a ticket to a new status/column.

    Args:
        item_id: The ticket's board item ID
        new_status: Target status name (e.g., "Plan", "Done")
    """

def archive_item(self, board_id: str, item_id: str) -> bool:
    """Archive/hide a completed ticket from the board.

    Returns True if successful.
    """
```

### Ticket Operations

```python
def get_ticket_body(self, repo: str, ticket_id: int) -> str | None:
    """Get the ticket's description/body text.

    This is fetched on-demand when a workflow runs, not during polling.
    """

def add_label(self, repo: str, ticket_id: int, label: str) -> None:
    """Add a label/tag to a ticket."""

def remove_label(self, repo: str, ticket_id: int, label: str) -> None:
    """Remove a label/tag from a ticket."""
```

### Label Management

```python
def get_repo_labels(self, repo: str) -> list[str]:
    """List all available labels in the repository/project."""

def create_repo_label(
    self, repo: str, name: str, description: str = "", color: str = ""
) -> bool:
    """Create a new label if it doesn't exist.

    Returns True if created successfully.
    """
```

### Comment Operations

```python
def get_comments(self, repo: str, ticket_id: int) -> list[Comment]:
    """Get all comments on a ticket, ordered by creation time."""

def get_comments_since(
    self, repo: str, ticket_id: int, since: str | None
) -> list[Comment]:
    """Get comments created after a timestamp.

    Args:
        since: ISO 8601 timestamp (e.g., "2024-01-15T10:30:00Z"), or None for all

    This is the primary method used during polling for efficiency.
    """

def add_comment(self, repo: str, ticket_id: int, body: str) -> Comment:
    """Post a new comment to a ticket.

    Returns the created Comment object.
    """

def add_reaction(self, comment_id: str, reaction: str) -> None:
    """Add a reaction/emoji to a comment.

    Used to mark comments as processed. Common reactions:
    - "THUMBS_UP" or "+1": Comment has been processed
    - "EYES": Comment is currently being processed
    """
```

### Audit

```python
def get_last_status_actor(self, repo: str, ticket_id: int) -> str | None:
    """Get who last changed the ticket's board status.

    Used to verify the status change was made by an authorized user,
    not by the bot itself (prevents infinite loops).
    """
```

## Implementation Example

```python
# src/ticket_clients/jira.py

from src.interfaces import Comment, TicketItem
from src.logger import get_logger

logger = get_logger(__name__)


class JiraTicketClient:
    """Jira implementation of TicketClient protocol."""

    def __init__(self, base_url: str, api_token: str) -> None:
        self.base_url = base_url
        self.api_token = api_token

    def get_board_items(self, board_url: str) -> list[TicketItem]:
        # Parse board_url to extract project key
        # Query Jira API for issues on the board
        # Map Jira issues to TicketItem objects
        issues = self._query_jira_board(board_url)
        return [self._to_ticket_item(issue) for issue in issues]

    def _to_ticket_item(self, issue: dict) -> TicketItem:
        return TicketItem(
            item_id=issue["key"],              # "PROJ-123"
            board_url=issue["board_url"],
            ticket_id=issue["id"],             # Numeric ID
            repo=issue["project"]["key"],      # Project key as "repo"
            status=issue["status"]["name"],
            title=issue["summary"],
            labels=set(issue.get("labels", [])),
            state="CLOSED" if issue["resolution"] else "OPEN",
            state_reason=issue.get("resolution", {}).get("name"),
            has_merged_changes=self._has_linked_merged_prs(issue),
            comment_count=issue["comment"]["total"],
        )

    # ... implement remaining methods
```

## Mapping Provider Concepts

| Abstract Concept | GitHub | Jira | Linear |
|-----------------|--------|------|--------|
| Board | Project (v2) | Board/Sprint | Project/Cycle |
| Ticket | Issue | Issue/Story | Issue |
| Status | Project column | Status field | State |
| Labels | Labels | Labels | Labels |
| Processed marker | 👍 reaction | ? (custom field) | ? (emoji) |
| Processing marker | 👀 reaction | ? (custom field) | ? (emoji) |
| Merged changes | Linked merged PRs | Linked merged PRs | Linked merged PRs |

## Registration

After implementing your client, register it in the daemon's initialization:

```python
# src/daemon.py

from src.ticket_clients.jira import JiraTicketClient

# In Daemon.__init__:
if config.ticket_provider == "jira":
    self.ticket_client = JiraTicketClient(config.jira_url, config.jira_token)
else:
    self.ticket_client = GitHubTicketClient(config.github_token)
```

## Testing

Create tests in `tests/test_<provider>_client.py`. Mock API responses and verify:

1. `get_board_items` returns correctly mapped `TicketItem` objects
2. `get_comments_since` filters by timestamp correctly
3. `add_comment` returns a valid `Comment` object
4. Status updates and label operations work correctly

See `tests/test_github_client.py` for examples.
