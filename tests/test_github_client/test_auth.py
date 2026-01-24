"""Tests for GitHub client authentication and validation functionality."""

import subprocess
from unittest.mock import patch

import pytest

from src.ticket_clients.base import NetworkError
from src.ticket_clients.github import GitHubTicketClient


@pytest.mark.unit
class TestTokenManagement:
    """Tests for GitHubTicketClient token management."""

    def test_get_token_for_host_found(self):
        """Test getting token for a configured host."""
        client = GitHubTicketClient(
            tokens={"github.com": "ghp_abc", "custom.github.com": "ghp_xyz"}
        )

        assert client._get_token_for_host("github.com") == "ghp_abc"
        assert client._get_token_for_host("custom.github.com") == "ghp_xyz"

    def test_get_token_for_host_not_found(self):
        """Test getting token for unconfigured host returns None."""
        client = GitHubTicketClient(tokens={"github.com": "ghp_abc"})

        assert client._get_token_for_host("unknown.host.com") is None

    def test_get_token_for_host_empty_tokens(self):
        """Test getting token with empty tokens dict returns None."""
        client = GitHubTicketClient(tokens={})

        assert client._get_token_for_host("github.com") is None

    def test_get_token_for_host_no_tokens(self):
        """Test getting token when tokens is None returns None."""
        client = GitHubTicketClient(tokens=None)

        assert client._get_token_for_host("github.com") is None

    def test_init_with_tokens_dict(self):
        """Test initializing client with tokens dictionary."""
        tokens = {"github.com": "ghp_public", "github.mycompany.com": "ghp_private"}
        client = GitHubTicketClient(tokens=tokens)

        assert client.tokens == tokens

    def test_init_without_tokens(self):
        """Test initializing client without tokens."""
        client = GitHubTicketClient()

        assert client.tokens == {}


@pytest.mark.unit
@pytest.mark.skip_auto_mock_validation
class TestValidateConnection:
    """Tests for GitHubTicketClient.validate_connection() method."""

    def test_validate_connection_success(self, github_client):
        """Test successful connection validation returns True."""
        mock_response = {"data": {"viewer": {"login": "test-user"}}}

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            result = github_client.validate_connection("github.com")

        assert result is True

    def test_validate_connection_default_hostname(self, github_client):
        """Test that default hostname is github.com."""
        mock_response = {"data": {"viewer": {"login": "test-user"}}}

        with patch.object(
            github_client, "_execute_graphql_query", return_value=mock_response
        ) as mock_query:
            github_client.validate_connection()

            # Verify hostname passed to query
            call_kwargs = mock_query.call_args[1]
            assert call_kwargs["hostname"] == "github.com"

    def test_validate_connection_custom_hostname(self, github_client):
        """Test validation with custom hostname."""
        mock_response = {"data": {"viewer": {"login": "custom-user"}}}

        with patch.object(
            github_client, "_execute_graphql_query", return_value=mock_response
        ) as mock_query:
            result = github_client.validate_connection("custom.github.com")

            # Verify custom hostname was used
            call_kwargs = mock_query.call_args[1]
            assert call_kwargs["hostname"] == "custom.github.com"
            assert result is True

    def test_validate_connection_no_login_raises_error(self, github_client):
        """Test that empty viewer response raises RuntimeError."""
        mock_response = {"data": {"viewer": {}}}

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            with pytest.raises(RuntimeError, match="Could not retrieve authenticated user"):
                github_client.validate_connection()

    def test_validate_connection_null_viewer_raises_error(self, github_client):
        """Test that null viewer raises RuntimeError."""
        mock_response = {"data": {"viewer": None}}

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            with pytest.raises(RuntimeError, match="Could not retrieve authenticated user"):
                github_client.validate_connection()

    def test_validate_connection_subprocess_error(self, github_client):
        """Test that subprocess errors are converted to RuntimeError."""
        import subprocess

        error = subprocess.CalledProcessError(1, "gh")
        error.stderr = "authentication required"
        error.stdout = ""

        with patch.object(github_client, "_execute_graphql_query", side_effect=error):
            with pytest.raises(RuntimeError, match="authentication required"):
                github_client.validate_connection()

    def test_validate_connection_value_error(self, github_client):
        """Test that ValueError from GraphQL is converted to RuntimeError."""
        with patch.object(
            github_client,
            "_execute_graphql_query",
            side_effect=ValueError("GraphQL errors: Bad credentials"),
        ):
            with pytest.raises(RuntimeError, match="Bad credentials"):
                github_client.validate_connection()

    def test_validate_connection_makes_viewer_query(self, github_client):
        """Test that the correct viewer query is made."""
        mock_response = {"data": {"viewer": {"login": "test-user"}}}

        with patch.object(
            github_client, "_execute_graphql_query", return_value=mock_response
        ) as mock_query:
            github_client.validate_connection()

            # Verify query contains viewer request
            query = mock_query.call_args[0][0]
            assert "viewer" in query
            assert "login" in query

    def test_validate_connection_quiet_logs_debug(self, github_client, caplog):
        """Test that quiet=True logs at DEBUG level instead of INFO."""
        import logging

        mock_response = {"data": {"viewer": {"login": "test-user"}}}

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            with caplog.at_level(logging.DEBUG):
                github_client.validate_connection("github.com", quiet=True)

        # Verify the success message was logged
        assert "GitHub authentication successful" in caplog.text
        # Verify it was logged at DEBUG level, not INFO
        auth_records = [
            r for r in caplog.records if "authentication successful" in r.message
        ]
        assert len(auth_records) == 1
        assert auth_records[0].levelno == logging.DEBUG

    def test_validate_connection_default_logs_info(self, github_client, caplog):
        """Test that default (quiet=False) logs at INFO level."""
        import logging

        mock_response = {"data": {"viewer": {"login": "test-user"}}}

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            with caplog.at_level(logging.DEBUG):
                github_client.validate_connection("github.com")

        # Verify the success message was logged at INFO level
        auth_records = [
            r for r in caplog.records if "authentication successful" in r.message
        ]
        assert len(auth_records) == 1
        assert auth_records[0].levelno == logging.INFO


@pytest.mark.unit
class TestGetTokenScopes:
    """Tests for GitHubTicketClient._get_token_scopes() method."""

    def test_get_token_scopes_parses_header(self, github_client):
        """Test parsing X-OAuth-Scopes header."""
        mock_output = (
            'HTTP/2.0 200 OK\nX-OAuth-Scopes: repo, read:org, project\n\n{"login": "test"}'
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = mock_output
            mock_run.return_value.returncode = 0
            scopes = github_client._get_token_scopes("github.com")

        assert scopes == {"repo", "read:org", "project"}

    def test_get_token_scopes_empty_scopes(self, github_client):
        """Test handling empty X-OAuth-Scopes header."""
        mock_output = 'HTTP/2.0 200 OK\nX-OAuth-Scopes: \n\n{"login": "test"}'

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = mock_output
            mock_run.return_value.returncode = 0
            scopes = github_client._get_token_scopes("github.com")

        assert scopes == set()

    def test_get_token_scopes_no_header_returns_none(self, github_client):
        """Test that missing header returns None (fine-grained PAT)."""
        mock_output = 'HTTP/2.0 200 OK\nContent-Type: application/json\n\n{"login": "test"}'

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = mock_output
            mock_run.return_value.returncode = 0
            scopes = github_client._get_token_scopes("github.com")

        assert scopes is None

    def test_get_token_scopes_case_insensitive_header(self, github_client):
        """Test that header matching is case-insensitive."""
        mock_output = 'HTTP/2.0 200 OK\nx-oauth-scopes: repo, project\n\n{"login": "test"}'

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = mock_output
            mock_run.return_value.returncode = 0
            scopes = github_client._get_token_scopes("github.com")

        assert scopes == {"repo", "project"}

    def test_get_token_scopes_uses_token(self, github_client):
        """Test that configured token is used in API call."""
        mock_output = "HTTP/2.0 200 OK\nX-OAuth-Scopes: repo\n\n{}"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = mock_output
            mock_run.return_value.returncode = 0
            github_client._get_token_scopes("github.com")

            call_kwargs = mock_run.call_args[1]
            assert "GITHUB_TOKEN" in call_kwargs["env"]
            assert call_kwargs["env"]["GITHUB_TOKEN"] == "test-token"

    def test_get_token_scopes_custom_hostname(self, github_client):
        """Test scope fetching with custom hostname."""
        mock_output = "HTTP/2.0 200 OK\nX-OAuth-Scopes: repo\n\n{}"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = mock_output
            mock_run.return_value.returncode = 0
            github_client._get_token_scopes("custom.github.com")

            call_args = mock_run.call_args[0][0]
            assert "--hostname" in call_args
            assert "custom.github.com" in call_args

    def test_get_token_scopes_api_error_returns_none(self, github_client):
        """Test that API errors return None."""
        import subprocess

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, "gh", stderr="API error")
            scopes = github_client._get_token_scopes("github.com")

        assert scopes is None


@pytest.mark.unit
@pytest.mark.skip_auto_mock_validation
class TestValidateScopes:
    """Tests for GitHubTicketClient.validate_scopes() method."""

    def test_validate_scopes_success(self, github_client):
        """Test successful scope validation with all required scopes."""
        mock_output = (
            'HTTP/2.0 200 OK\nX-OAuth-Scopes: repo, read:org, project\n\n{"login": "test-user"}'
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = mock_output
            mock_run.return_value.returncode = 0
            result = github_client.validate_scopes("github.com")

        assert result is True

    def test_validate_scopes_missing_scopes_raises_error(self, github_client):
        """Test that missing required scopes raises RuntimeError."""
        mock_output = 'HTTP/2.0 200 OK\nX-OAuth-Scopes: repo\n\n{"login": "test-user"}'

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = mock_output
            mock_run.return_value.returncode = 0
            with pytest.raises(RuntimeError, match="should ONLY have these scopes"):
                github_client.validate_scopes("github.com")

    def test_validate_scopes_fine_grained_pat_raises_error(self, github_client):
        """Test that fine-grained PAT (no X-OAuth-Scopes header) raises RuntimeError."""
        mock_output = 'HTTP/2.0 200 OK\nContent-Type: application/json\n\n{"login": "test-user"}'

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = mock_output
            mock_run.return_value.returncode = 0
            with pytest.raises(RuntimeError) as exc_info:
                github_client.validate_scopes("github.com")

        error_msg = str(exc_info.value)
        assert "fine-grained PAT" in error_msg.lower() or "could not verify" in error_msg.lower()
        assert "classic Personal Access Token" in error_msg

    def test_validate_scopes_fine_grained_pat_prefix_detected_early(self, github_client):
        """Test that fine-grained PAT is detected by prefix before API call."""
        # Set a fine-grained PAT token
        github_client.tokens["github.com"] = "github_pat_abc123xyz"

        # Should fail immediately without making API call
        with pytest.raises(RuntimeError) as exc_info:
            github_client.validate_scopes("github.com")

        error_msg = str(exc_info.value)
        assert "Fine-grained PAT detected" in error_msg
        assert "github_pat_" in error_msg
        assert "classic Personal Access Token" in error_msg

    def test_validate_scopes_classic_pat_prefix_allowed(self, github_client):
        """Test that classic PAT prefix (ghp_) passes prefix check."""
        github_client.tokens["github.com"] = "ghp_abc123xyz"
        mock_output = (
            'HTTP/2.0 200 OK\nX-OAuth-Scopes: repo, read:org, project\n\n{"login": "test-user"}'
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = mock_output
            mock_run.return_value.returncode = 0
            result = github_client.validate_scopes("github.com")

        assert result is True

    def test_validate_scopes_custom_hostname(self, github_client):
        """Test scope validation with custom hostname."""
        mock_output = (
            'HTTP/2.0 200 OK\nX-OAuth-Scopes: repo, read:org, project\n\n{"login": "test-user"}'
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = mock_output
            mock_run.return_value.returncode = 0
            github_client.validate_scopes("custom.github.com")

            # Verify --hostname flag was passed
            call_args = mock_run.call_args[0][0]
            assert "--hostname" in call_args
            assert "custom.github.com" in call_args

    def test_validate_scopes_error_message_lists_missing_scopes(self, github_client):
        """Test that error message clearly lists which scopes are missing."""
        mock_output = 'HTTP/2.0 200 OK\nX-OAuth-Scopes: repo\n\n{"login": "test-user"}'

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = mock_output
            mock_run.return_value.returncode = 0
            with pytest.raises(RuntimeError) as exc_info:
                github_client.validate_scopes("github.com")

            error_msg = str(exc_info.value)
            assert "project" in error_msg
            assert "read:org" in error_msg

    def test_validate_scopes_api_error_raises(self, github_client):
        """Test that API errors raise RuntimeError (fail closed for security)."""
        import subprocess

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, "gh", stderr="API error")
            with pytest.raises(RuntimeError) as exc_info:
                github_client.validate_scopes("github.com")

        error_msg = str(exc_info.value)
        assert "Could not verify token scopes" in error_msg

    def test_validate_scopes_required_scopes_constant(self, github_client):
        """Test that REQUIRED_SCOPES contains expected values."""
        assert {"repo", "read:org", "project"} == github_client.REQUIRED_SCOPES

    def test_validate_scopes_excessive_scopes_raises_error(self, github_client):
        """Test that excessive scopes raise RuntimeError."""
        mock_output = (
            "HTTP/2.0 200 OK\n"
            "X-OAuth-Scopes: repo, read:org, project, admin:org\n"
            "\n"
            '{"login": "test-user"}'
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = mock_output
            mock_run.return_value.returncode = 0
            with pytest.raises(RuntimeError, match="should ONLY have these scopes"):
                github_client.validate_scopes("github.com")

    def test_validate_scopes_excessive_scopes_error_provides_guidance(self, github_client):
        """Test that error message provides guidance on required scopes."""
        mock_output = (
            "HTTP/2.0 200 OK\n"
            "X-OAuth-Scopes: repo, read:org, project, admin:org, delete_repo\n"
            "\n"
            '{"login": "test-user"}'
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = mock_output
            mock_run.return_value.returncode = 0
            with pytest.raises(RuntimeError) as exc_info:
                github_client.validate_scopes("github.com")

            error_msg = str(exc_info.value)
            assert "project" in error_msg
            assert "read:org" in error_msg
            assert "repo" in error_msg

    def test_validate_scopes_multiple_excessive_scopes(self, github_client):
        """Test detection of multiple excessive scopes."""
        mock_output = (
            "HTTP/2.0 200 OK\n"
            "X-OAuth-Scopes: repo, read:org, project, admin:org, workflow, user\n"
            "\n"
            '{"login": "test-user"}'
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = mock_output
            mock_run.return_value.returncode = 0
            with pytest.raises(RuntimeError) as exc_info:
                github_client.validate_scopes("github.com")

            error_msg = str(exc_info.value)
            assert "should ONLY have these scopes" in error_msg
            assert "too many or too few" in error_msg

    def test_validate_scopes_excessive_scopes_constant(self, github_client):
        """Test that EXCESSIVE_SCOPES contains expected dangerous scopes."""
        expected = {
            "admin:org",
            "delete_repo",
            "admin:org_hook",
            "admin:repo_hook",
            "admin:public_key",
            "admin:gpg_key",
            "write:org",
            "workflow",
            "delete:packages",
            "codespace",
            "user",
        }
        assert expected == github_client.EXCESSIVE_SCOPES


@pytest.mark.unit
class TestAuthenticationErrorHandling:
    """Tests for authentication error handling in _run_gh_command."""

    def test_auth_error_gh_auth_login_simple(self, github_client):
        """Test that auth error produces simple message in non-debug mode."""
        import subprocess

        error = subprocess.CalledProcessError(
            1, ["gh", "api"], stderr="To get started with GitHub CLI, please run:  gh auth login"
        )

        with patch("subprocess.run", side_effect=error):
            with patch("src.ticket_clients.github.is_debug_mode", return_value=False):
                with pytest.raises(RuntimeError) as exc_info:
                    github_client._run_gh_command(["api", "user"])

                error_msg = str(exc_info.value)
                assert "GitHub authentication failed" in error_msg
                assert "GITHUB_TOKEN" in error_msg
                # Simple mode should NOT include detailed error
                assert "gh auth login" not in error_msg

    def test_auth_error_gh_auth_login_debug(self, github_client):
        """Test that auth error produces rich message in debug mode."""
        import subprocess

        error = subprocess.CalledProcessError(
            1, ["gh", "api"], stderr="To get started with GitHub CLI, please run:  gh auth login"
        )

        with patch("subprocess.run", side_effect=error):
            with patch("src.ticket_clients.github.is_debug_mode", return_value=True):
                with pytest.raises(RuntimeError) as exc_info:
                    github_client._run_gh_command(["api", "user"])

                error_msg = str(exc_info.value)
                assert "GitHub authentication failed" in error_msg
                assert "GITHUB_TOKEN" in error_msg
                assert "gh auth login" in error_msg

    def test_auth_error_unauthorized(self, github_client):
        """Test that unauthorized error produces user-friendly message."""
        import subprocess

        error = subprocess.CalledProcessError(1, ["gh", "api"], stderr="401 Unauthorized")

        with patch("subprocess.run", side_effect=error):
            with pytest.raises(RuntimeError) as exc_info:
                github_client._run_gh_command(["api", "user"])

            error_msg = str(exc_info.value)
            assert "GitHub authentication failed" in error_msg
            assert "GITHUB_TOKEN" in error_msg

    def test_auth_error_not_logged_in(self, github_client):
        """Test that 'not logged in' error produces user-friendly message."""
        import subprocess

        error = subprocess.CalledProcessError(
            1, ["gh", "api"], stderr="You are not logged in to any GitHub hosts"
        )

        with patch("subprocess.run", side_effect=error):
            with pytest.raises(RuntimeError) as exc_info:
                github_client._run_gh_command(["api", "user"])

            error_msg = str(exc_info.value)
            assert "GitHub authentication failed" in error_msg

    def test_auth_error_no_token(self, github_client):
        """Test that 'no token' error produces user-friendly message."""
        import subprocess

        error = subprocess.CalledProcessError(1, ["gh", "api"], stderr="no token found")

        with patch("subprocess.run", side_effect=error):
            with pytest.raises(RuntimeError) as exc_info:
                github_client._run_gh_command(["api", "user"])

            error_msg = str(exc_info.value)
            assert "GitHub authentication failed" in error_msg

    def test_auth_error_authentication_required(self, github_client):
        """Test that 'authentication' error produces user-friendly message."""
        import subprocess

        error = subprocess.CalledProcessError(1, ["gh", "api"], stderr="authentication required")

        with patch("subprocess.run", side_effect=error):
            with pytest.raises(RuntimeError) as exc_info:
                github_client._run_gh_command(["api", "user"])

            error_msg = str(exc_info.value)
            assert "GitHub authentication failed" in error_msg

    def test_non_auth_error_raises_original(self, github_client):
        """Test that non-authentication errors are re-raised as-is."""
        import subprocess

        error = subprocess.CalledProcessError(
            1, ["gh", "api"], stderr="some other error: network timeout"
        )

        with patch("subprocess.run", side_effect=error):
            with pytest.raises(subprocess.CalledProcessError):
                github_client._run_gh_command(["api", "user"])

    def test_auth_error_empty_stderr(self, github_client):
        """Test that empty stderr doesn't cause errors."""
        import subprocess

        error = subprocess.CalledProcessError(1, ["gh", "api"], stderr="")

        with patch("subprocess.run", side_effect=error):
            # Should raise the original error since no auth indicators
            with pytest.raises(subprocess.CalledProcessError):
                github_client._run_gh_command(["api", "user"])

    def test_auth_error_none_stderr(self, github_client):
        """Test that None stderr doesn't cause errors."""
        import subprocess

        error = subprocess.CalledProcessError(1, ["gh", "api"], stderr=None)

        with patch("subprocess.run", side_effect=error):
            # Should raise the original error since no auth indicators
            with pytest.raises(subprocess.CalledProcessError):
                github_client._run_gh_command(["api", "user"])

    def test_auth_error_includes_hostname(self, github_client):
        """Test that error message includes hostname."""
        import subprocess

        error = subprocess.CalledProcessError(1, ["gh", "api"], stderr="gh auth login")

        with patch("subprocess.run", side_effect=error):
            with pytest.raises(RuntimeError) as exc_info:
                github_client._run_gh_command(["api", "user"], hostname="github.mycompany.com")

            error_msg = str(exc_info.value)
            assert "github.mycompany.com" in error_msg


@pytest.mark.unit
class TestNetworkErrorDetection:
    """Tests for NetworkError detection in _run_gh_command."""

    def test_tls_handshake_timeout_raises_network_error(self, github_client):
        """Test that TLS handshake timeout raises NetworkError."""
        import subprocess

        error = subprocess.CalledProcessError(
            1, ["gh", "api"], stderr="dial tcp: TLS handshake timeout"
        )

        with patch("subprocess.run", side_effect=error):
            with pytest.raises(NetworkError) as exc_info:
                github_client._run_gh_command(["api", "user"])

            assert "network error" in str(exc_info.value).lower()

    def test_connection_timeout_raises_network_error(self, github_client):
        """Test that connection timeout raises NetworkError."""
        import subprocess

        error = subprocess.CalledProcessError(
            1, ["gh", "api"], stderr="connection timeout: unable to reach server"
        )

        with patch("subprocess.run", side_effect=error):
            with pytest.raises(NetworkError):
                github_client._run_gh_command(["api", "user"])

    def test_connection_refused_raises_network_error(self, github_client):
        """Test that connection refused raises NetworkError."""
        import subprocess

        error = subprocess.CalledProcessError(
            1, ["gh", "api"], stderr="connection refused"
        )

        with patch("subprocess.run", side_effect=error):
            with pytest.raises(NetworkError):
                github_client._run_gh_command(["api", "user"])

    def test_io_timeout_raises_network_error(self, github_client):
        """Test that i/o timeout raises NetworkError."""
        import subprocess

        error = subprocess.CalledProcessError(
            1, ["gh", "api"], stderr="read: i/o timeout"
        )

        with patch("subprocess.run", side_effect=error):
            with pytest.raises(NetworkError):
                github_client._run_gh_command(["api", "user"])

    def test_dial_tcp_error_raises_network_error(self, github_client):
        """Test that Go network dial errors raise NetworkError."""
        import subprocess

        error = subprocess.CalledProcessError(
            1, ["gh", "api"], stderr="dial tcp: lookup api.github.com: no such host"
        )

        with patch("subprocess.run", side_effect=error):
            with pytest.raises(NetworkError):
                github_client._run_gh_command(["api", "user"])

    def test_no_such_host_raises_network_error(self, github_client):
        """Test that DNS resolution failures raise NetworkError."""
        import subprocess

        error = subprocess.CalledProcessError(
            1, ["gh", "api"], stderr="no such host: api.github.com"
        )

        with patch("subprocess.run", side_effect=error):
            with pytest.raises(NetworkError):
                github_client._run_gh_command(["api", "user"])

    def test_temporary_failure_raises_network_error(self, github_client):
        """Test that temporary DNS failures raise NetworkError."""
        import subprocess

        error = subprocess.CalledProcessError(
            1, ["gh", "api"], stderr="temporary failure in name resolution"
        )

        with patch("subprocess.run", side_effect=error):
            with pytest.raises(NetworkError):
                github_client._run_gh_command(["api", "user"])

    def test_network_error_generic_raises_network_error(self, github_client):
        """Test that generic network error message raises NetworkError."""
        import subprocess

        error = subprocess.CalledProcessError(
            1, ["gh", "api"], stderr="network error: unable to reach GitHub"
        )

        with patch("subprocess.run", side_effect=error):
            with pytest.raises(NetworkError):
                github_client._run_gh_command(["api", "user"])

    def test_non_network_error_raises_called_process_error(self, github_client):
        """Test that non-network errors raise CalledProcessError."""
        import subprocess

        error = subprocess.CalledProcessError(
            1, ["gh", "api"], stderr="unknown error: something else went wrong"
        )

        with patch("subprocess.run", side_effect=error):
            with pytest.raises(subprocess.CalledProcessError):
                github_client._run_gh_command(["api", "user"])

    def test_network_error_takes_precedence_over_auth_error(self, github_client):
        """Test that network errors are detected before auth errors."""
        import subprocess

        # Error message contains both network and auth indicators
        error = subprocess.CalledProcessError(
            1, ["gh", "api"], stderr="TLS handshake timeout during authentication"
        )

        with patch("subprocess.run", side_effect=error):
            # Should raise NetworkError, not RuntimeError (auth)
            with pytest.raises(NetworkError):
                github_client._run_gh_command(["api", "user"])
