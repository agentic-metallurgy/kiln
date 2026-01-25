"""Pytest configuration and shared fixtures."""

import os
import tempfile
from unittest.mock import patch

import pytest
from hypothesis import Verbosity, settings


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "skip_auto_mock_validation: skip the autouse mock_validate_connection fixture",
    )


@pytest.fixture(autouse=True)
def mock_validate_connection(request):
    """Automatically mock GitHubTicketClient validation methods for all tests.

    This prevents tests from making real GitHub API calls during Daemon initialization.
    Tests that specifically need to test validation behavior can use the
    'skip_auto_mock_validation' marker to disable this fixture.
    """
    # Allow tests to opt out by using @pytest.mark.skip_auto_mock_validation
    if "skip_auto_mock_validation" in [marker.name for marker in request.node.iter_markers()]:
        yield
    else:
        with (
            patch(
                "src.ticket_clients.github.GitHubTicketClient.validate_connection",
                return_value=True,
            ),
            patch(
                "src.ticket_clients.github.GitHubTicketClient.validate_scopes",
                return_value=True,
            ),
        ):
            yield


@pytest.fixture
def temp_workspace_dir():
    """Fixture providing a temporary workspace directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def mock_gh_subprocess():
    """Fixture for mocking subprocess calls to gh CLI."""
    with patch("subprocess.run") as mock_run:
        yield mock_run


@pytest.fixture
def mock_claude_subprocess():
    """Fixture for mocking subprocess.Popen for Claude CLI."""
    with patch("subprocess.Popen") as mock_popen:
        yield mock_popen


# Hypothesis configuration for property-based testing
# Register profiles for different environments
settings.register_profile("ci", max_examples=100, verbosity=Verbosity.verbose)
settings.register_profile("dev", max_examples=50)

# Load profile from environment variable, defaulting to "dev"
settings.load_profile(os.getenv("HYPOTHESIS_PROFILE", "dev"))
