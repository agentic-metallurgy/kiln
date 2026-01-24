"""Tests for GitHub client utility functions and helper methods."""

import json
from unittest.mock import patch

import pytest

from src.ticket_clients.base import NetworkError


@pytest.mark.unit
class TestNetworkErrorException:
    """Tests for NetworkError exception class."""

    def test_network_error_can_be_raised(self):
        """Test that NetworkError can be raised with a message."""
        with pytest.raises(NetworkError) as exc_info:
            raise NetworkError("TLS handshake timeout")
        assert "TLS handshake timeout" in str(exc_info.value)


@pytest.mark.unit
class TestTimestampNormalization:
    """Tests for timestamp format handling in GitHub API calls."""

    def test_since_timestamp_plus_format_normalized_to_z(self, github_client):
        """Test that +00:00 timestamps are normalized to Z format for GitHub API.

        GitHub's REST API doesn't handle + in URLs correctly (interprets as space).
        We must convert +00:00 to Z format.
        """
        mock_response = json.dumps([])
        timestamp = "2024-01-15T10:30:00+00:00"

        with patch.object(github_client, "_run_gh_command", return_value=mock_response) as mock_cmd:
            github_client.get_comments_since("owner/repo", 42, timestamp)

            call_args = mock_cmd.call_args[0][0]
            endpoint = call_args[1]

            # MUST use Z format, NOT +00:00 (+ becomes space in URL)
            assert "?since=2024-01-15T10:30:00Z" in endpoint
            assert "+00:00" not in endpoint

    def test_since_timestamp_z_format_unchanged(self, github_client):
        """Test that Z format timestamps are passed through unchanged."""
        mock_response = json.dumps([])
        timestamp = "2024-01-15T10:30:00Z"

        with patch.object(github_client, "_run_gh_command", return_value=mock_response) as mock_cmd:
            github_client.get_comments_since("owner/repo", 42, timestamp)

            call_args = mock_cmd.call_args[0][0]
            endpoint = call_args[1]

            assert "?since=2024-01-15T10:30:00Z" in endpoint

    def test_since_timestamp_none_no_parameter(self, github_client):
        """Test that None timestamp doesn't add since parameter."""
        mock_response = json.dumps([])

        with patch.object(github_client, "_run_gh_command", return_value=mock_response) as mock_cmd:
            github_client.get_comments_since("owner/repo", 42, None)

            call_args = mock_cmd.call_args[0][0]
            endpoint = call_args[1]

            assert "?since=" not in endpoint


@pytest.mark.unit
class TestParseRepo:
    """Tests for GitHubTicketClient._parse_repo() method."""

    def test_parse_repo_github_com(self, github_client):
        """Test parsing github.com repo format."""
        hostname, owner, repo = github_client._parse_repo("github.com/owner/repo")

        assert hostname == "github.com"
        assert owner == "owner"
        assert repo == "repo"

    def test_parse_repo_with_custom_hostname(self, github_client):
        """Test parsing repo format with custom hostname."""
        hostname, owner, repo = github_client._parse_repo("custom.github.com/org/project")

        assert hostname == "custom.github.com"
        assert owner == "org"
        assert repo == "project"

    def test_parse_repo_legacy_format(self, github_client):
        """Test parsing legacy owner/repo format."""
        hostname, owner, repo = github_client._parse_repo("owner/repo")

        assert hostname == "github.com"
        assert owner == "owner"
        assert repo == "repo"


@pytest.mark.unit
class TestGetHostnameForRepo:
    """Tests for GitHubTicketClient._get_hostname_for_repo() method."""

    def test_get_hostname_from_repo_string(self, github_client):
        """Test extracting hostname from repo string."""
        hostname = github_client._get_hostname_for_repo("custom.github.com/owner/repo")

        assert hostname == "custom.github.com"

    def test_get_hostname_from_cache(self, github_client):
        """Test getting hostname from cache for legacy format."""
        github_client._repo_host_map["owner/repo"] = "cached.github.com"

        hostname = github_client._get_hostname_for_repo("owner/repo")

        assert hostname == "cached.github.com"

    def test_get_hostname_defaults_to_github_com(self, github_client):
        """Test default hostname is github.com."""
        hostname = github_client._get_hostname_for_repo("unknown/repo")

        assert hostname == "github.com"


@pytest.mark.unit
class TestGetRepoRef:
    """Tests for GitHubTicketClient._get_repo_ref() method."""

    def test_get_repo_ref_returns_https_url(self, github_client):
        """Test that _get_repo_ref returns HTTPS URL."""
        result = github_client._get_repo_ref("github.com/owner/repo")

        assert result == "https://github.com/owner/repo"

    def test_get_repo_ref_preserves_hostname(self, github_client):
        """Test that custom hostname is preserved."""
        result = github_client._get_repo_ref("custom.github.com/owner/repo")

        assert result == "https://custom.github.com/owner/repo"
