"""Tests for GitHub client pull request-related functionality."""

import subprocess
from unittest.mock import patch

import pytest

from src.interfaces import LinkedPullRequest


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
