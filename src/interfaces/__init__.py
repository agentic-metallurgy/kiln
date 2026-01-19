"""Abstract interfaces for ticket system integrations."""

from src.interfaces.ticket import (
    Comment,
    LinkedPullRequest,
    TicketClient,
    TicketItem,
)

__all__ = [
    "Comment",
    "LinkedPullRequest",
    "TicketClient",
    "TicketItem",
]
