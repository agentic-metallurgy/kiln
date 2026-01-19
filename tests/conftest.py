"""Pytest configuration and shared fixtures."""

from unittest.mock import patch

import pytest


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "skip_auto_mock_validation: skip the autouse mock_validate_connection fixture",
    )


@pytest.fixture(autouse=True)
def mock_validate_connection(request):
    """Automatically mock GitHubTicketClient.validate_connection for all tests.

    This prevents tests from making real GitHub API calls during Daemon initialization.
    Tests that specifically need to test validation behavior can use the
    'skip_auto_mock_validation' marker to disable this fixture.
    """
    # Allow tests to opt out by using @pytest.mark.skip_auto_mock_validation
    if "skip_auto_mock_validation" in [marker.name for marker in request.node.iter_markers()]:
        yield
    else:
        with patch(
            "src.ticket_clients.github.GitHubTicketClient.validate_connection",
            return_value=True,
        ):
            yield
