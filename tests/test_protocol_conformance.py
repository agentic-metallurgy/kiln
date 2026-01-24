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

import pytest

from src.interfaces.ticket import TicketClient
from src.ticket_clients import (
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


# Helper to get client class name for test IDs
def _client_id(client_class: type) -> str:
    """Generate a readable test ID from client class."""
    return client_class.__name__


@pytest.mark.unit
class TestProtocolStructuralConformance:
    """Tests that all client classes structurally conform to TicketClient protocol.

    Uses isinstance() with @runtime_checkable to verify that each client
    implementation is recognized as a TicketClient at runtime.
    """

    @pytest.mark.parametrize("client_class", ALL_CLIENT_CLASSES, ids=_client_id)
    def test_isinstance_ticket_client(self, client_class: type) -> None:
        """Verify client class instances pass isinstance(client, TicketClient) check.

        This test creates an instance of each client class with mock credentials
        and verifies it is recognized as implementing the TicketClient protocol.
        """
        # Create instance with empty tokens dict (clients accept tokens dict, not single token)
        client = client_class(tokens={})

        # Verify isinstance check passes
        assert isinstance(
            client, TicketClient
        ), f"{client_class.__name__} should be an instance of TicketClient protocol"
