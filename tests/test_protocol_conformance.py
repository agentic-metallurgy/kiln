"""Protocol conformance tests for GitHub client implementations.

This module verifies that all GitHub client implementations correctly implement
the TicketClient protocol. It tests three levels of conformance:

1. Structural conformance: isinstance(client, TicketClient) passes
2. Method existence: All protocol methods exist on each client
3. Signature matching: Method signatures match the protocol definition

These tests prevent interface mismatches (like method renames) from going
undetected and ensure all clients are interchangeable via the TicketClient
protocol.
"""

import inspect
from typing import get_type_hints

import pytest

from src.interfaces.ticket import TicketClient
from src.ticket_clients import (
    GHES_VERSION_CLIENTS,
    GitHubEnterprise314Client,
    GitHubEnterprise315Client,
    GitHubEnterprise316Client,
    GitHubEnterprise317Client,
    GitHubEnterprise318Client,
    GitHubEnterprise319Client,
    GitHubTicketClient,
)

# All methods defined in the TicketClient protocol
PROTOCOL_METHODS = [
    "get_board_items",
    "get_board_metadata",
    "update_item_status",
    "archive_item",
    "get_ticket_body",
    "get_ticket_labels",
    "add_label",
    "remove_label",
    "get_repo_labels",
    "create_repo_label",
    "get_comments",
    "get_comments_since",
    "add_comment",
    "add_reaction",
    "get_last_status_actor",
    "get_label_actor",
    "get_linked_prs",
    "remove_pr_issue_link",
    "close_pr",
    "delete_branch",
    "get_pr_state",
]

# All client classes that implement TicketClient
# Combines GitHubTicketClient with all GHES version clients
ALL_CLIENT_CLASSES = [
    GitHubTicketClient,
    GitHubEnterprise314Client,
    GitHubEnterprise315Client,
    GitHubEnterprise316Client,
    GitHubEnterprise317Client,
    GitHubEnterprise318Client,
    GitHubEnterprise319Client,
]
