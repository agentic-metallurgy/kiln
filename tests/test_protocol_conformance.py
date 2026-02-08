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
        assert isinstance(client, TicketClient), (
            f"{client_class.__name__} should be an instance of TicketClient protocol"
        )


@pytest.mark.unit
class TestProtocolMethodExistence:
    """Tests that all protocol methods exist on client implementations.

    Verifies each of the 21 TicketClient protocol methods exists on every
    client class and is callable.
    """

    @pytest.mark.parametrize("client_class", ALL_CLIENT_CLASSES, ids=_client_id)
    @pytest.mark.parametrize("method_name", PROTOCOL_METHODS)
    def test_method_exists_and_callable(self, client_class: type, method_name: str) -> None:
        """Verify required method exists and is callable.

        This test checks that each client class has all 21 methods required
        by the TicketClient protocol, and that each method is callable.
        """
        # Create instance with empty tokens dict
        client = client_class(tokens={})

        # Verify method exists
        assert hasattr(client, method_name), (
            f"{client_class.__name__} missing required method: {method_name}"
        )

        # Verify method is callable
        method = getattr(client, method_name)
        assert callable(method), f"{client_class.__name__}.{method_name} is not callable"


def _get_protocol_signature(method_name: str) -> inspect.Signature:
    """Extract the signature of a method from the TicketClient protocol."""
    protocol_method = getattr(TicketClient, method_name)
    return inspect.signature(protocol_method)


def _get_required_params(sig: inspect.Signature) -> list[str]:
    """Extract required parameter names from a signature, excluding 'self'.

    A parameter is required if it has no default value and is not keyword-only
    with a default.
    """
    required = []
    for name, param in sig.parameters.items():
        if name == "self":
            continue
        # Parameter is required if it has no default and is not variadic
        if param.default is inspect.Parameter.empty and param.kind not in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            required.append(name)
    return required


def _get_param_names(sig: inspect.Signature) -> list[str]:
    """Extract parameter names from a signature, excluding 'self'."""
    return [name for name in sig.parameters if name != "self"]


@pytest.mark.unit
class TestProtocolSignatureConformance:
    """Tests that method signatures match the protocol definition.

    Verifies that each client's implementation of protocol methods is compatible
    with the protocol signature. Implementations may have additional optional
    parameters (with defaults) as extensions.

    Note: Type annotations are not enforced at runtime by runtime_checkable.
    """

    @pytest.mark.parametrize("client_class", ALL_CLIENT_CLASSES, ids=_client_id)
    @pytest.mark.parametrize("method_name", PROTOCOL_METHODS)
    def test_method_signature_matches_protocol(self, client_class: type, method_name: str) -> None:
        """Verify method signature is compatible with protocol definition.

        This test ensures that each client method can be called with the
        protocol's signature. Implementations may add extra optional parameters
        but must accept all protocol parameters in the same order.
        """
        # Get protocol signature
        protocol_sig = _get_protocol_signature(method_name)
        protocol_params = _get_param_names(protocol_sig)

        # Get client method signature
        client = client_class(tokens={})
        client_method = getattr(client, method_name)
        client_sig = inspect.signature(client_method)
        client_params = _get_param_names(client_sig)

        # All protocol parameters must be present in client
        for i, protocol_param in enumerate(protocol_params):
            assert i < len(client_params), (
                f"{client_class.__name__}.{method_name} is missing required parameter "
                f"'{protocol_param}' at position {i}. "
                f"Client: {client_params}, Protocol: {protocol_params}"
            )
            assert client_params[i] == protocol_param, (
                f"{client_class.__name__}.{method_name} has parameter "
                f"'{client_params[i]}' at position {i} but protocol expects "
                f"'{protocol_param}'. "
                f"Client: {client_params}, Protocol: {protocol_params}"
            )

        # Any extra client parameters must have default values
        extra_params = client_params[len(protocol_params) :]
        for extra_param in extra_params:
            param = client_sig.parameters[extra_param]
            assert param.default is not inspect.Parameter.empty, (
                f"{client_class.__name__}.{method_name} has extra required parameter "
                f"'{extra_param}' not in protocol. Extra parameters must have defaults. "
                f"Client: {client_params}, Protocol: {protocol_params}"
            )
