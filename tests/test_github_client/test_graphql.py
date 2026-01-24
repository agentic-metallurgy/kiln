"""Tests for GitHub client GraphQL and sub-issues functionality."""

import json
from unittest.mock import patch

import pytest


@pytest.mark.unit
class TestGetParentIssue:
    """Tests for GitHubTicketClient.get_parent_issue() method."""

    def test_get_parent_issue_returns_parent_number(self, github_client):
        """Test that get_parent_issue returns parent issue number when present."""
        mock_response = {"data": {"repository": {"issue": {"parent": {"number": 42}}}}}

        with patch.object(
            github_client, "_execute_graphql_query_with_headers", return_value=mock_response
        ):
            parent = github_client.get_parent_issue("github.com/owner/repo", 123)

        assert parent == 42

    def test_get_parent_issue_returns_none_when_no_parent(self, github_client):
        """Test that get_parent_issue returns None when issue has no parent."""
        mock_response = {"data": {"repository": {"issue": {"parent": None}}}}

        with patch.object(
            github_client, "_execute_graphql_query_with_headers", return_value=mock_response
        ):
            parent = github_client.get_parent_issue("github.com/owner/repo", 123)

        assert parent is None

    def test_get_parent_issue_returns_none_on_error(self, github_client):
        """Test that get_parent_issue returns None on API errors."""
        with patch.object(
            github_client, "_execute_graphql_query_with_headers", side_effect=Exception("API error")
        ):
            parent = github_client.get_parent_issue("github.com/owner/repo", 123)

        assert parent is None

    def test_get_parent_issue_uses_sub_issues_header(self, github_client):
        """Test that get_parent_issue sends the GraphQL-Features: sub_issues header."""
        mock_response = {"data": {"repository": {"issue": {"parent": None}}}}

        with patch.object(
            github_client, "_execute_graphql_query_with_headers", return_value=mock_response
        ) as mock_query:
            github_client.get_parent_issue("github.com/owner/repo", 123)

            # Verify the headers parameter includes sub_issues
            call_args = mock_query.call_args
            # headers is passed as a keyword argument
            kwargs = call_args.kwargs
            headers = kwargs.get("headers")
            assert headers is not None
            assert "GraphQL-Features: sub_issues" in headers


@pytest.mark.unit
class TestGetPrForIssue:
    """Tests for GitHubTicketClient.get_pr_for_issue() method."""

    def test_get_pr_for_issue_returns_open_pr(self, github_client):
        """Test that get_pr_for_issue returns open PR info."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "closedByPullRequestsReferences": {
                            "nodes": [
                                {
                                    "number": 99,
                                    "url": "https://github.com/owner/repo/pull/99",
                                    "headRefName": "feature-branch",
                                    "state": "OPEN",
                                }
                            ]
                        }
                    }
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            pr = github_client.get_pr_for_issue("github.com/owner/repo", 42)

        assert pr is not None
        assert pr["number"] == 99
        assert pr["url"] == "https://github.com/owner/repo/pull/99"
        assert pr["branch_name"] == "feature-branch"

    def test_get_pr_for_issue_filters_by_state(self, github_client):
        """Test that get_pr_for_issue only returns PRs matching the state filter."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "closedByPullRequestsReferences": {
                            "nodes": [
                                {
                                    "number": 88,
                                    "url": "https://github.com/owner/repo/pull/88",
                                    "headRefName": "old-branch",
                                    "state": "CLOSED",
                                },
                                {
                                    "number": 99,
                                    "url": "https://github.com/owner/repo/pull/99",
                                    "headRefName": "feature-branch",
                                    "state": "OPEN",
                                },
                            ]
                        }
                    }
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            pr = github_client.get_pr_for_issue("github.com/owner/repo", 42)

        # Should return the OPEN PR, not the CLOSED one
        assert pr is not None
        assert pr["number"] == 99

    def test_get_pr_for_issue_returns_none_when_no_matching_pr(self, github_client):
        """Test that get_pr_for_issue returns None when no PR matches."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "closedByPullRequestsReferences": {
                            "nodes": [
                                {
                                    "number": 88,
                                    "url": "https://github.com/owner/repo/pull/88",
                                    "headRefName": "old-branch",
                                    "state": "CLOSED",
                                }
                            ]
                        }
                    }
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            pr = github_client.get_pr_for_issue("github.com/owner/repo", 42)

        assert pr is None

    def test_get_pr_for_issue_returns_none_on_error(self, github_client):
        """Test that get_pr_for_issue returns None on API errors."""
        with patch.object(
            github_client, "_execute_graphql_query", side_effect=Exception("API error")
        ):
            pr = github_client.get_pr_for_issue("github.com/owner/repo", 42)

        assert pr is None

    def test_get_pr_for_issue_handles_empty_nodes(self, github_client):
        """Test that get_pr_for_issue handles empty PR nodes list."""
        mock_response = {
            "data": {"repository": {"issue": {"closedByPullRequestsReferences": {"nodes": []}}}}
        }

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            pr = github_client.get_pr_for_issue("github.com/owner/repo", 42)

        assert pr is None


@pytest.mark.unit
class TestExecuteGraphqlQueryWithHeaders:
    """Tests for GitHubTicketClient._execute_graphql_query_with_headers() method."""

    def test_execute_graphql_query_with_headers_passes_headers(self, github_client):
        """Test that headers are passed to the gh command."""
        mock_response = json.dumps({"data": {"viewer": {"login": "test"}}})

        with patch.object(github_client, "_run_gh_command", return_value=mock_response) as mock_cmd:
            github_client._execute_graphql_query_with_headers(
                "query { viewer { login } }",
                {},
                ["GraphQL-Features: sub_issues", "Custom-Header: value"],
            )

            # Verify headers are added with -H flags
            call_args = mock_cmd.call_args[0][0]
            assert "-H" in call_args
            assert "GraphQL-Features: sub_issues" in call_args
            assert "Custom-Header: value" in call_args

    def test_execute_graphql_query_with_headers_parses_response(self, github_client):
        """Test that response JSON is correctly parsed."""
        mock_response = json.dumps({"data": {"repository": {"name": "test"}}})

        with patch.object(github_client, "_run_gh_command", return_value=mock_response):
            result = github_client._execute_graphql_query_with_headers(
                "query { repository { name } }",
                {},
                ["GraphQL-Features: sub_issues"],
            )

        assert result["data"]["repository"]["name"] == "test"

    def test_execute_graphql_query_with_headers_raises_on_errors(self, github_client):
        """Test that GraphQL errors are raised."""
        mock_response = json.dumps(
            {"data": None, "errors": [{"message": "Field 'parent' doesn't exist"}]}
        )

        with patch.object(github_client, "_run_gh_command", return_value=mock_response):
            with pytest.raises(ValueError) as exc_info:
                github_client._execute_graphql_query_with_headers(
                    "query { invalid }",
                    {},
                    ["GraphQL-Features: sub_issues"],
                )

            assert "parent" in str(exc_info.value) or "GraphQL errors" in str(exc_info.value)


@pytest.mark.unit
class TestGetChildIssues:
    """Tests for GitHubTicketClient.get_child_issues() method."""

    def test_get_child_issues_returns_children(self, github_client):
        """Test that get_child_issues returns child issue info."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "subIssues": {
                            "nodes": [
                                {"number": 10, "state": "OPEN"},
                                {"number": 11, "state": "CLOSED"},
                            ]
                        }
                    }
                }
            }
        }

        with patch.object(
            github_client, "_execute_graphql_query_with_headers", return_value=mock_response
        ):
            children = github_client.get_child_issues("github.com/owner/repo", 5)

        assert len(children) == 2
        assert children[0] == {"number": 10, "state": "OPEN"}
        assert children[1] == {"number": 11, "state": "CLOSED"}

    def test_get_child_issues_returns_empty_when_no_children(self, github_client):
        """Test that get_child_issues returns empty list when no children."""
        mock_response = {"data": {"repository": {"issue": {"subIssues": {"nodes": []}}}}}

        with patch.object(
            github_client, "_execute_graphql_query_with_headers", return_value=mock_response
        ):
            children = github_client.get_child_issues("github.com/owner/repo", 5)

        assert children == []

    def test_get_child_issues_returns_empty_on_error(self, github_client):
        """Test that get_child_issues returns empty list on API errors."""
        with patch.object(
            github_client, "_execute_graphql_query_with_headers", side_effect=Exception("API error")
        ):
            children = github_client.get_child_issues("github.com/owner/repo", 5)

        assert children == []

    def test_get_child_issues_uses_sub_issues_header(self, github_client):
        """Test that get_child_issues sends the sub_issues header."""
        mock_response = {"data": {"repository": {"issue": {"subIssues": {"nodes": []}}}}}

        with patch.object(
            github_client, "_execute_graphql_query_with_headers", return_value=mock_response
        ) as mock_query:
            github_client.get_child_issues("github.com/owner/repo", 5)

            # Verify sub_issues header is passed via kwargs
            call_kwargs = mock_query.call_args
            headers = call_kwargs.kwargs.get("headers", [])
            assert "GraphQL-Features: sub_issues" in headers


@pytest.mark.unit
class TestGetPrHeadSha:
    """Tests for GitHubTicketClient.get_pr_head_sha() method."""

    def test_get_pr_head_sha_returns_sha(self, github_client):
        """Test that get_pr_head_sha returns the HEAD SHA."""
        mock_response = {"data": {"repository": {"pullRequest": {"headRefOid": "abc123def456"}}}}

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            sha = github_client.get_pr_head_sha("github.com/owner/repo", 42)

        assert sha == "abc123def456"

    def test_get_pr_head_sha_returns_none_when_no_pr(self, github_client):
        """Test that get_pr_head_sha returns None when PR not found."""
        mock_response = {"data": {"repository": {"pullRequest": None}}}

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            sha = github_client.get_pr_head_sha("github.com/owner/repo", 42)

        assert sha is None

    def test_get_pr_head_sha_returns_none_on_error(self, github_client):
        """Test that get_pr_head_sha returns None on API errors."""
        with patch.object(
            github_client, "_execute_graphql_query", side_effect=Exception("API error")
        ):
            sha = github_client.get_pr_head_sha("github.com/owner/repo", 42)

        assert sha is None


@pytest.mark.unit
class TestSetCommitStatus:
    """Tests for GitHubTicketClient.set_commit_status() method."""

    def test_set_commit_status_success(self, github_client):
        """Test that set_commit_status calls the correct API."""
        with patch.object(github_client, "_run_gh_command", return_value="{}") as mock_cmd:
            result = github_client.set_commit_status(
                repo="github.com/owner/repo",
                sha="abc123",
                state="success",
                context="kiln/child-issues",
                description="All children resolved",
            )

        assert result is True
        call_args = mock_cmd.call_args[0][0]
        assert "repos/owner/repo/statuses/abc123" in call_args
        assert "-X" in call_args
        assert "POST" in call_args
        assert "state=success" in " ".join(call_args)
        assert "context=kiln/child-issues" in " ".join(call_args)

    def test_set_commit_status_with_target_url(self, github_client):
        """Test that set_commit_status includes target_url when provided."""
        with patch.object(github_client, "_run_gh_command", return_value="{}") as mock_cmd:
            github_client.set_commit_status(
                repo="github.com/owner/repo",
                sha="abc123",
                state="pending",
                context="kiln/child-issues",
                description="1 child still open",
                target_url="https://example.com/details",
            )

        call_args = mock_cmd.call_args[0][0]
        assert "target_url=https://example.com/details" in " ".join(call_args)

    def test_set_commit_status_returns_false_on_error(self, github_client):
        """Test that set_commit_status returns False on API errors."""
        with patch.object(github_client, "_run_gh_command", side_effect=Exception("API error")):
            result = github_client.set_commit_status(
                repo="github.com/owner/repo",
                sha="abc123",
                state="success",
                context="kiln/child-issues",
                description="All resolved",
            )

        assert result is False
