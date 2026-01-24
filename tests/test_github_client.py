"""Unit tests for the GitHub ticket client module."""

import json
import subprocess
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from src.interfaces import Comment, LinkedPullRequest
from src.ticket_clients.base import NetworkError
from src.ticket_clients.github import GitHubTicketClient
from src.ticket_clients.github_enterprise_3_14 import GitHubEnterprise314Client
from src.ticket_clients.github_enterprise_3_18 import GitHubEnterprise318Client


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
class TestGetLinkedPRs:
    """Tests for GitHubTicketClient.get_linked_prs() method."""

    def test_get_linked_prs_returns_pr_list(self, github_client):
        """Test that linked PRs are returned correctly."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "closedByPullRequestsReferences": {
                            "nodes": [
                                {
                                    "number": 123,
                                    "url": "https://github.com/owner/repo/pull/123",
                                    "body": "Closes #42\n\nSome description",
                                    "state": "OPEN",
                                    "merged": False,
                                    "headRefName": "42-feature-branch",
                                },
                                {
                                    "number": 456,
                                    "url": "https://github.com/owner/repo/pull/456",
                                    "body": "Fixes #42",
                                    "state": "MERGED",
                                    "merged": True,
                                    "headRefName": "42-other-branch",
                                },
                            ]
                        }
                    }
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            prs = github_client.get_linked_prs("github.com/owner/repo", 42)

        assert len(prs) == 2
        assert prs[0].number == 123
        assert prs[0].url == "https://github.com/owner/repo/pull/123"
        assert prs[0].body == "Closes #42\n\nSome description"
        assert prs[0].state == "OPEN"
        assert prs[0].merged is False
        assert prs[0].branch_name == "42-feature-branch"
        assert prs[1].number == 456
        assert prs[1].merged is True
        assert prs[1].branch_name == "42-other-branch"

    def test_get_linked_prs_returns_empty_list_when_no_prs(self, github_client):
        """Test that empty list is returned when there are no linked PRs."""
        mock_response = {
            "data": {"repository": {"issue": {"closedByPullRequestsReferences": {"nodes": []}}}}
        }

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            prs = github_client.get_linked_prs("github.com/owner/repo", 42)

        assert prs == []

    def test_get_linked_prs_returns_empty_list_on_nonexistent_issue(self, github_client):
        """Test that empty list is returned when issue doesn't exist."""
        mock_response = {"data": {"repository": {"issue": None}}}

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            prs = github_client.get_linked_prs("github.com/owner/repo", 99999)

        assert prs == []

    def test_get_linked_prs_returns_empty_list_on_api_error(self, github_client):
        """Test that empty list is returned on API error."""
        with patch.object(
            github_client, "_execute_graphql_query", side_effect=Exception("API error")
        ):
            prs = github_client.get_linked_prs("github.com/owner/repo", 42)

        assert prs == []

    def test_get_linked_prs_skips_null_nodes(self, github_client):
        """Test that null nodes in the response are skipped."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "closedByPullRequestsReferences": {
                            "nodes": [
                                None,
                                {
                                    "number": 123,
                                    "url": "https://github.com/owner/repo/pull/123",
                                    "body": "Closes #42",
                                    "state": "OPEN",
                                    "merged": False,
                                    "headRefName": "42-branch",
                                },
                                None,
                            ]
                        }
                    }
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            prs = github_client.get_linked_prs("github.com/owner/repo", 42)

        assert len(prs) == 1
        assert prs[0].number == 123
        assert prs[0].branch_name == "42-branch"


@pytest.mark.unit
class TestRemovePRIssueLink:
    """Tests for GitHubTicketClient.remove_pr_issue_link() method."""

    def test_remove_pr_issue_link_removes_closes_keyword(self, github_client):
        """Test that 'closes' keyword is removed from PR body."""
        pr_response = {
            "data": {
                "repository": {"pullRequest": {"body": "This PR closes #42 and adds new features."}}
            }
        }

        with (
            patch.object(github_client, "_execute_graphql_query", return_value=pr_response),
            patch.object(github_client, "_run_gh_command") as mock_run,
        ):
            result = github_client.remove_pr_issue_link("github.com/owner/repo", 123, 42)

        assert result is True
        # Verify the new body was passed to gh pr edit
        call_args = mock_run.call_args[0][0]
        assert "pr" in call_args
        assert "edit" in call_args
        assert "123" in call_args
        assert "--body" in call_args
        # The body should have "closes " removed but "#42" preserved
        body_idx = call_args.index("--body") + 1
        new_body = call_args[body_idx]
        assert "closes" not in new_body.lower()
        assert "#42" in new_body

    def test_remove_pr_issue_link_handles_various_keywords(self, github_client):
        """Test that various linking keywords are removed."""
        test_cases = [
            ("Fixes #42", "#42"),
            ("fixes: #42", "#42"),
            ("CLOSES #42", "#42"),
            ("Resolves #42", "#42"),
            ("This PR closes #42", "This PR #42"),
            ("Fix #42 and close #99", "#42 and close #99"),  # Removes "Fix" keyword for #42
        ]

        for original, expected in test_cases:
            result = github_client._remove_closes_keyword(original, 42)
            assert result == expected, (
                f"Failed for '{original}': got '{result}' expected '{expected}'"
            )

    def test_remove_pr_issue_link_returns_false_when_no_keyword(self, github_client):
        """Test that False is returned when no linking keyword is found."""
        pr_response = {
            "data": {
                "repository": {
                    "pullRequest": {"body": "This PR is related to #42 but doesn't close it."}
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query", return_value=pr_response):
            result = github_client.remove_pr_issue_link("github.com/owner/repo", 123, 42)

        assert result is False

    def test_remove_pr_issue_link_returns_false_when_pr_not_found(self, github_client):
        """Test that False is returned when PR doesn't exist."""
        pr_response = {"data": {"repository": {"pullRequest": None}}}

        with patch.object(github_client, "_execute_graphql_query", return_value=pr_response):
            result = github_client.remove_pr_issue_link("github.com/owner/repo", 99999, 42)

        assert result is False

    def test_remove_pr_issue_link_returns_false_on_api_error(self, github_client):
        """Test that False is returned on API error."""
        with patch.object(
            github_client, "_execute_graphql_query", side_effect=Exception("API error")
        ):
            result = github_client.remove_pr_issue_link("github.com/owner/repo", 123, 42)

        assert result is False


@pytest.mark.unit
class TestRemoveClosesKeyword:
    """Tests for GitHubTicketClient._remove_closes_keyword() helper method."""

    def test_remove_closes_keyword_close(self, github_client):
        """Test removing 'close' keyword."""
        result = github_client._remove_closes_keyword("close #123", 123)
        assert result == "#123"

    def test_remove_closes_keyword_closes(self, github_client):
        """Test removing 'closes' keyword."""
        result = github_client._remove_closes_keyword("closes #123", 123)
        assert result == "#123"

    def test_remove_closes_keyword_closed(self, github_client):
        """Test removing 'closed' keyword."""
        result = github_client._remove_closes_keyword("closed #123", 123)
        assert result == "#123"

    def test_remove_closes_keyword_fix(self, github_client):
        """Test removing 'fix' keyword."""
        result = github_client._remove_closes_keyword("fix #123", 123)
        assert result == "#123"

    def test_remove_closes_keyword_fixes(self, github_client):
        """Test removing 'fixes' keyword."""
        result = github_client._remove_closes_keyword("fixes #123", 123)
        assert result == "#123"

    def test_remove_closes_keyword_fixed(self, github_client):
        """Test removing 'fixed' keyword."""
        result = github_client._remove_closes_keyword("fixed #123", 123)
        assert result == "#123"

    def test_remove_closes_keyword_resolve(self, github_client):
        """Test removing 'resolve' keyword."""
        result = github_client._remove_closes_keyword("resolve #123", 123)
        assert result == "#123"

    def test_remove_closes_keyword_resolves(self, github_client):
        """Test removing 'resolves' keyword."""
        result = github_client._remove_closes_keyword("resolves #123", 123)
        assert result == "#123"

    def test_remove_closes_keyword_resolved(self, github_client):
        """Test removing 'resolved' keyword."""
        result = github_client._remove_closes_keyword("resolved #123", 123)
        assert result == "#123"

    def test_remove_closes_keyword_with_colon(self, github_client):
        """Test removing keyword with colon."""
        result = github_client._remove_closes_keyword("Fixes: #123", 123)
        assert result == "#123"

    def test_remove_closes_keyword_case_insensitive(self, github_client):
        """Test that keyword matching is case insensitive."""
        result = github_client._remove_closes_keyword("CLOSES #123", 123)
        assert result == "#123"

        result = github_client._remove_closes_keyword("Fixes #123", 123)
        assert result == "#123"

    def test_remove_closes_keyword_preserves_surrounding_text(self, github_client):
        """Test that surrounding text is preserved."""
        result = github_client._remove_closes_keyword(
            "This PR closes #123 by refactoring the code.", 123
        )
        assert result == "This PR #123 by refactoring the code."

    def test_remove_closes_keyword_only_removes_specified_issue(self, github_client):
        """Test that only the specified issue number is affected."""
        result = github_client._remove_closes_keyword("closes #123 and fixes #456", 123)
        assert result == "#123 and fixes #456"

    def test_remove_closes_keyword_no_change_when_different_issue(self, github_client):
        """Test that body is unchanged when different issue number."""
        original = "closes #456"
        result = github_client._remove_closes_keyword(original, 123)
        assert result == original

    def test_remove_closes_keyword_no_change_when_no_keyword(self, github_client):
        """Test that body is unchanged when no linking keyword."""
        original = "Related to #123"
        result = github_client._remove_closes_keyword(original, 123)
        assert result == original


@pytest.mark.unit
class TestClosePr:
    """Tests for GitHubTicketClient.close_pr() method."""

    def test_close_pr_success(self, github_client):
        """Test successfully closing a PR."""
        with patch.object(github_client, "_run_gh_command") as mock_run:
            result = github_client.close_pr("github.com/owner/repo", 123)

        assert result is True
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert call_args == ["pr", "close", "123", "--repo", "https://github.com/owner/repo"]

    def test_close_pr_returns_false_on_error(self, github_client):
        """Test that False is returned when gh command fails."""
        error = subprocess.CalledProcessError(1, "gh")
        error.stderr = "PR is already closed"
        with patch.object(github_client, "_run_gh_command", side_effect=error):
            result = github_client.close_pr("github.com/owner/repo", 123)

        assert result is False

    def test_close_pr_uses_correct_repo_reference(self, github_client):
        """Test that the full repo URL is used for GHES compatibility."""
        with patch.object(github_client, "_run_gh_command") as mock_run:
            github_client.close_pr("github.example.com/myorg/myrepo", 456)

        call_args = mock_run.call_args[0][0]
        assert "--repo" in call_args
        repo_idx = call_args.index("--repo") + 1
        assert call_args[repo_idx] == "https://github.example.com/myorg/myrepo"

    def test_close_pr_passes_repo_for_hostname_lookup(self, github_client):
        """Test that repo is passed for hostname lookup."""
        with patch.object(github_client, "_run_gh_command") as mock_run:
            github_client.close_pr("github.com/owner/repo", 99)

        mock_run.assert_called_once()
        assert mock_run.call_args[1]["repo"] == "github.com/owner/repo"


@pytest.mark.unit
class TestDeleteBranch:
    """Tests for GitHubTicketClient.delete_branch() method."""

    def test_delete_branch_success(self, github_client):
        """Test successfully deleting a branch."""
        with patch.object(github_client, "_run_gh_command") as mock_run:
            result = github_client.delete_branch("github.com/owner/repo", "feature-branch")

        assert result is True
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert call_args == ["api", "repos/owner/repo/git/refs/heads/feature-branch", "-X", "DELETE"]

    def test_delete_branch_returns_false_when_not_found(self, github_client):
        """Test that False is returned when branch doesn't exist."""
        error = subprocess.CalledProcessError(1, "gh")
        error.stderr = "HTTP 404: Not Found"
        with patch.object(github_client, "_run_gh_command", side_effect=error):
            result = github_client.delete_branch("github.com/owner/repo", "nonexistent-branch")

        assert result is False

    def test_delete_branch_returns_false_on_error(self, github_client):
        """Test that False is returned on API error."""
        error = subprocess.CalledProcessError(1, "gh")
        error.stderr = "API error"
        with patch.object(github_client, "_run_gh_command", side_effect=error):
            result = github_client.delete_branch("github.com/owner/repo", "feature-branch")

        assert result is False

    def test_delete_branch_handles_slashes_in_name(self, github_client):
        """Test that branch names with slashes are URL-encoded."""
        with patch.object(github_client, "_run_gh_command") as mock_run:
            github_client.delete_branch("github.com/owner/repo", "feature/my-feature")

        call_args = mock_run.call_args[0][0]
        # Branch name with slash should be URL-encoded
        assert call_args == ["api", "repos/owner/repo/git/refs/heads/feature%2Fmy-feature", "-X", "DELETE"]

    def test_delete_branch_uses_hostname_for_ghes(self, github_client):
        """Test that hostname is passed for GHES compatibility."""
        with patch.object(github_client, "_run_gh_command") as mock_run:
            github_client.delete_branch("github.example.com/myorg/myrepo", "feature-branch")

        mock_run.assert_called_once()
        assert mock_run.call_args[1]["hostname"] == "github.example.com"

    def test_delete_branch_parses_repo_correctly(self, github_client):
        """Test that repo is parsed correctly for API endpoint."""
        with patch.object(github_client, "_run_gh_command") as mock_run:
            github_client.delete_branch("github.com/my-org/my-repo", "fix-bug")

        call_args = mock_run.call_args[0][0]
        assert "repos/my-org/my-repo/git/refs/heads/fix-bug" in call_args[1]


@pytest.mark.unit
class TestGetPrState:
    """Tests for GitHubTicketClient.get_pr_state() method."""

    def test_get_pr_state_returns_open(self, github_client):
        """Test that OPEN state is returned for an open PR."""
        mock_response = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "state": "OPEN",
                        "merged": False,
                    }
                }
            }
        }
        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            result = github_client.get_pr_state("github.com/owner/repo", 123)

        assert result == "OPEN"

    def test_get_pr_state_returns_closed(self, github_client):
        """Test that CLOSED state is returned for a closed PR."""
        mock_response = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "state": "CLOSED",
                        "merged": False,
                    }
                }
            }
        }
        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            result = github_client.get_pr_state("github.com/owner/repo", 123)

        assert result == "CLOSED"

    def test_get_pr_state_returns_merged(self, github_client):
        """Test that MERGED state is returned for a merged PR."""
        mock_response = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "state": "CLOSED",
                        "merged": True,
                    }
                }
            }
        }
        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            result = github_client.get_pr_state("github.com/owner/repo", 123)

        assert result == "MERGED"

    def test_get_pr_state_returns_none_when_pr_not_found(self, github_client):
        """Test that None is returned when PR doesn't exist."""
        mock_response = {
            "data": {
                "repository": {
                    "pullRequest": None
                }
            }
        }
        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            result = github_client.get_pr_state("github.com/owner/repo", 999)

        assert result is None

    def test_get_pr_state_returns_none_on_error(self, github_client):
        """Test that None is returned on API error (fail-safe)."""
        with patch.object(
            github_client, "_execute_graphql_query", side_effect=Exception("API error")
        ):
            result = github_client.get_pr_state("github.com/owner/repo", 123)

        assert result is None

    def test_get_pr_state_queries_correct_repo(self, github_client):
        """Test that the correct repo is queried."""
        mock_response = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "state": "OPEN",
                        "merged": False,
                    }
                }
            }
        }
        with patch.object(
            github_client, "_execute_graphql_query", return_value=mock_response
        ) as mock_query:
            github_client.get_pr_state("github.com/myorg/myrepo", 456)

        # Check the variables passed to the query
        call_args = mock_query.call_args
        variables = call_args[0][1]
        assert variables["owner"] == "myorg"
        assert variables["repo"] == "myrepo"
        assert variables["prNumber"] == 456


@pytest.mark.unit
class TestLinkedPullRequest:
    """Tests for LinkedPullRequest dataclass."""

    def test_linked_pr_creation(self):
        """Test creating a LinkedPullRequest instance."""
        pr = LinkedPullRequest(
            number=123,
            url="https://github.com/owner/repo/pull/123",
            body="Closes #42",
            state="OPEN",
            merged=False,
        )

        assert pr.number == 123
        assert pr.url == "https://github.com/owner/repo/pull/123"
        assert pr.body == "Closes #42"
        assert pr.state == "OPEN"
        assert pr.merged is False
        assert pr.branch_name is None

    def test_linked_pr_with_branch_name(self):
        """Test creating a LinkedPullRequest with branch_name."""
        pr = LinkedPullRequest(
            number=123,
            url="https://github.com/owner/repo/pull/123",
            body="Closes #42",
            state="OPEN",
            merged=False,
            branch_name="42-feature-branch",
        )

        assert pr.number == 123
        assert pr.branch_name == "42-feature-branch"

    def test_linked_pr_merged_state(self):
        """Test LinkedPullRequest with merged state."""
        pr = LinkedPullRequest(
            number=456,
            url="https://github.com/owner/repo/pull/456",
            body="Fixes #99",
            state="MERGED",
            merged=True,
        )

        assert pr.state == "MERGED"
        assert pr.merged is True


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


@pytest.fixture
def enterprise_318_client():
    """Fixture providing a GitHubEnterprise318Client instance."""
    return GitHubEnterprise318Client(tokens={"github.mycompany.com": "test-token"})


@pytest.mark.unit
class TestGitHubEnterprise318Client:
    """Tests for GitHubEnterprise318Client behavior and capabilities."""

    def test_supports_sub_issues_returns_true(self, enterprise_318_client):
        """Test that supports_sub_issues property returns True for GHES 3.18."""
        assert enterprise_318_client.supports_sub_issues is True

    def test_supports_linked_prs_returns_true(self, enterprise_318_client):
        """Test that supports_linked_prs property returns True (inherited from 3.14)."""
        assert enterprise_318_client.supports_linked_prs is True

    def test_supports_status_actor_check_returns_true(self, enterprise_318_client):
        """Test that supports_status_actor_check property returns True (inherited from 3.14)."""
        assert enterprise_318_client.supports_status_actor_check is True

    def test_client_description_returns_correct_string(self, enterprise_318_client):
        """Test that client_description returns 'GitHub Enterprise Server 3.18'."""
        assert enterprise_318_client.client_description == "GitHub Enterprise Server 3.18"

    def test_inherits_from_enterprise_314_client(self, enterprise_318_client):
        """Test that GitHubEnterprise318Client inherits from GitHubEnterprise314Client."""
        assert isinstance(enterprise_318_client, GitHubEnterprise314Client)

    def test_get_parent_issue_with_parent(self, enterprise_318_client):
        """Test get_parent_issue returns parent issue number when present."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "parent": {
                            "number": 42
                        }
                    }
                }
            }
        }

        with patch.object(
            enterprise_318_client, "_execute_graphql_query_with_headers", return_value=mock_response
        ):
            result = enterprise_318_client.get_parent_issue(
                "github.mycompany.com/owner/repo", 123
            )

        assert result == 42

    def test_get_parent_issue_without_parent(self, enterprise_318_client):
        """Test get_parent_issue returns None when issue has no parent."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "parent": None
                    }
                }
            }
        }

        with patch.object(
            enterprise_318_client, "_execute_graphql_query_with_headers", return_value=mock_response
        ):
            result = enterprise_318_client.get_parent_issue(
                "github.mycompany.com/owner/repo", 123
            )

        assert result is None

    def test_get_parent_issue_nonexistent_issue(self, enterprise_318_client):
        """Test get_parent_issue returns None for nonexistent issue."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": None
                }
            }
        }

        with patch.object(
            enterprise_318_client, "_execute_graphql_query_with_headers", return_value=mock_response
        ):
            result = enterprise_318_client.get_parent_issue(
                "github.mycompany.com/owner/repo", 99999
            )

        assert result is None

    def test_get_parent_issue_uses_sub_issues_header(self, enterprise_318_client):
        """Test get_parent_issue uses the GraphQL-Features: sub_issues header."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "parent": None
                    }
                }
            }
        }

        with patch.object(
            enterprise_318_client, "_execute_graphql_query_with_headers", return_value=mock_response
        ) as mock_query:
            enterprise_318_client.get_parent_issue("github.mycompany.com/owner/repo", 123)

            call_args = mock_query.call_args
            # Check positional or keyword args for headers
            if len(call_args[0]) >= 3:
                headers = call_args[0][2]
            else:
                headers = call_args[1].get("headers", [])
            assert "GraphQL-Features: sub_issues" in headers

    def test_get_parent_issue_handles_api_error(self, enterprise_318_client):
        """Test get_parent_issue returns None on API error."""
        with patch.object(
            enterprise_318_client,
            "_execute_graphql_query_with_headers",
            side_effect=Exception("API error"),
        ):
            result = enterprise_318_client.get_parent_issue(
                "github.mycompany.com/owner/repo", 123
            )

        assert result is None

    def test_get_child_issues_with_children(self, enterprise_318_client):
        """Test get_child_issues returns list of child issues."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "subIssues": {
                            "nodes": [
                                {"number": 101, "state": "OPEN"},
                                {"number": 102, "state": "CLOSED"},
                                {"number": 103, "state": "OPEN"},
                            ]
                        }
                    }
                }
            }
        }

        with patch.object(
            enterprise_318_client, "_execute_graphql_query_with_headers", return_value=mock_response
        ):
            result = enterprise_318_client.get_child_issues(
                "github.mycompany.com/owner/repo", 42
            )

        assert len(result) == 3
        assert result[0] == {"number": 101, "state": "OPEN"}
        assert result[1] == {"number": 102, "state": "CLOSED"}
        assert result[2] == {"number": 103, "state": "OPEN"}

    def test_get_child_issues_without_children(self, enterprise_318_client):
        """Test get_child_issues returns empty list when no children."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "subIssues": {
                            "nodes": []
                        }
                    }
                }
            }
        }

        with patch.object(
            enterprise_318_client, "_execute_graphql_query_with_headers", return_value=mock_response
        ):
            result = enterprise_318_client.get_child_issues(
                "github.mycompany.com/owner/repo", 42
            )

        assert result == []

    def test_get_child_issues_nonexistent_issue(self, enterprise_318_client):
        """Test get_child_issues returns empty list for nonexistent issue."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": None
                }
            }
        }

        with patch.object(
            enterprise_318_client, "_execute_graphql_query_with_headers", return_value=mock_response
        ):
            result = enterprise_318_client.get_child_issues(
                "github.mycompany.com/owner/repo", 99999
            )

        assert result == []

    def test_get_child_issues_uses_sub_issues_header(self, enterprise_318_client):
        """Test get_child_issues uses the GraphQL-Features: sub_issues header."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "subIssues": {
                            "nodes": []
                        }
                    }
                }
            }
        }

        with patch.object(
            enterprise_318_client, "_execute_graphql_query_with_headers", return_value=mock_response
        ) as mock_query:
            enterprise_318_client.get_child_issues("github.mycompany.com/owner/repo", 42)

            call_args = mock_query.call_args
            # Check positional or keyword args for headers
            if len(call_args[0]) >= 3:
                headers = call_args[0][2]
            else:
                headers = call_args[1].get("headers", [])
            assert "GraphQL-Features: sub_issues" in headers

    def test_get_child_issues_handles_api_error(self, enterprise_318_client):
        """Test get_child_issues returns empty list on API error."""
        with patch.object(
            enterprise_318_client,
            "_execute_graphql_query_with_headers",
            side_effect=Exception("API error"),
        ):
            result = enterprise_318_client.get_child_issues(
                "github.mycompany.com/owner/repo", 42
            )

        assert result == []

    def test_get_child_issues_handles_null_nodes(self, enterprise_318_client):
        """Test get_child_issues handles null entries in nodes array."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "subIssues": {
                            "nodes": [
                                {"number": 101, "state": "OPEN"},
                                None,  # Can occur with deleted issues
                                {"number": 103, "state": "OPEN"},
                            ]
                        }
                    }
                }
            }
        }

        with patch.object(
            enterprise_318_client, "_execute_graphql_query_with_headers", return_value=mock_response
        ):
            result = enterprise_318_client.get_child_issues(
                "github.mycompany.com/owner/repo", 42
            )

        assert len(result) == 2
        assert result[0] == {"number": 101, "state": "OPEN"}
        assert result[1] == {"number": 103, "state": "OPEN"}


@pytest.mark.unit
class TestGHES318VersionRegistry:
    """Tests for GHES 3.18 version in the client registry."""

    def test_get_github_client_returns_318_client(self):
        """Test that get_github_client returns GitHubEnterprise318Client for version 3.18."""
        from src.ticket_clients import get_github_client

        client = get_github_client(enterprise_version="3.18")

        assert isinstance(client, GitHubEnterprise318Client)
        assert client.client_description == "GitHub Enterprise Server 3.18"

    def test_version_registry_contains_318(self):
        """Test that GHES_VERSION_CLIENTS dict contains 3.18."""
        from src.ticket_clients import GHES_VERSION_CLIENTS

        assert "3.18" in GHES_VERSION_CLIENTS
        assert GHES_VERSION_CLIENTS["3.18"] is GitHubEnterprise318Client


@pytest.mark.unit
class TestGHES316Client:
    """Tests for GitHubEnterprise316Client."""

    def test_get_github_client_returns_ghes_316_client(self):
        """Test that get_github_client returns GitHubEnterprise316Client for version 3.16."""
        from src.ticket_clients import GitHubEnterprise316Client, get_github_client

        client = get_github_client(enterprise_version="3.16")
        assert isinstance(client, GitHubEnterprise316Client)

    def test_client_description_returns_expected_value(self):
        """Test that client_description returns 'GitHub Enterprise Server 3.16'."""
        from src.ticket_clients import GitHubEnterprise316Client

        client = GitHubEnterprise316Client()
        assert client.client_description == "GitHub Enterprise Server 3.16"

    def test_ghes_316_inherits_from_ghes_314(self):
        """Test that GitHubEnterprise316Client inherits from GitHubEnterprise314Client."""
        from src.ticket_clients import GitHubEnterprise314Client, GitHubEnterprise316Client

        assert issubclass(GitHubEnterprise316Client, GitHubEnterprise314Client)

    def test_supports_linked_prs_property(self):
        """Test that supports_linked_prs returns True (inherited from GHES 3.14)."""
        from src.ticket_clients import GitHubEnterprise316Client

        client = GitHubEnterprise316Client()
        assert client.supports_linked_prs is True

    def test_supports_sub_issues_property(self):
        """Test that supports_sub_issues returns False (inherited from GHES 3.14)."""
        from src.ticket_clients import GitHubEnterprise316Client

        client = GitHubEnterprise316Client()
        assert client.supports_sub_issues is False

    def test_supports_status_actor_check_property(self):
        """Test that supports_status_actor_check returns True (inherited from GHES 3.14)."""
        from src.ticket_clients import GitHubEnterprise316Client

        client = GitHubEnterprise316Client()
        assert client.supports_status_actor_check is True
