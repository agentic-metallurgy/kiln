"""Unit tests for the child_issue_checker module."""

from unittest.mock import MagicMock

import pytest

from src.child_issue_checker import CHILD_ISSUES_CHECK_CONTEXT, update_parent_pr_status


@pytest.fixture
def mock_client():
    """Fixture providing a mock GitHubTicketClient."""
    return MagicMock()


@pytest.mark.unit
class TestUpdateParentPrStatus:
    """Tests for update_parent_pr_status function."""

    def test_sets_failure_status_when_children_open(self, mock_client):
        """Test that failure status is set when child issues are open."""
        mock_client.get_pr_for_issue.return_value = {
            "number": 100,
            "headRefName": "10-feature",
            "url": "https://github.com/owner/repo/pull/100",
        }
        mock_client.get_child_issues.return_value = [
            {"number": 20, "state": "open"},
            {"number": 21, "state": "closed"},
        ]
        mock_client.get_pr_head_sha.return_value = "abc123def456"

        update_parent_pr_status(mock_client, "github.com/owner/repo", 10)

        mock_client.set_commit_status.assert_called_once_with(
            repo="github.com/owner/repo",
            sha="abc123def456",
            state="failure",
            context=CHILD_ISSUES_CHECK_CONTEXT,
            description="1 child issue(s) still open",
        )

    def test_sets_success_status_when_all_children_closed(self, mock_client):
        """Test that success status is set when all children are closed."""
        mock_client.get_pr_for_issue.return_value = {
            "number": 100,
            "headRefName": "10-feature",
            "url": "https://github.com/owner/repo/pull/100",
        }
        mock_client.get_child_issues.return_value = [
            {"number": 20, "state": "closed"},
            {"number": 21, "state": "closed"},
        ]
        mock_client.get_pr_head_sha.return_value = "abc123def456"

        update_parent_pr_status(mock_client, "github.com/owner/repo", 10)

        mock_client.set_commit_status.assert_called_once_with(
            repo="github.com/owner/repo",
            sha="abc123def456",
            state="success",
            context=CHILD_ISSUES_CHECK_CONTEXT,
            description="All child issues resolved",
        )

    def test_sets_success_status_when_no_children(self, mock_client):
        """Test that success status is set when there are no children."""
        mock_client.get_pr_for_issue.return_value = {
            "number": 100,
            "headRefName": "10-feature",
            "url": "https://github.com/owner/repo/pull/100",
        }
        mock_client.get_child_issues.return_value = []
        mock_client.get_pr_head_sha.return_value = "abc123def456"

        update_parent_pr_status(mock_client, "github.com/owner/repo", 10)

        mock_client.set_commit_status.assert_called_once_with(
            repo="github.com/owner/repo",
            sha="abc123def456",
            state="success",
            context=CHILD_ISSUES_CHECK_CONTEXT,
            description="All child issues resolved",
        )

    def test_does_nothing_when_no_open_pr(self, mock_client):
        """Test that nothing happens when parent has no open PR."""
        mock_client.get_pr_for_issue.return_value = None

        update_parent_pr_status(mock_client, "github.com/owner/repo", 10)

        mock_client.get_child_issues.assert_not_called()
        mock_client.set_commit_status.assert_not_called()

    def test_does_nothing_when_sha_not_found(self, mock_client):
        """Test that nothing happens when PR head SHA cannot be fetched."""
        mock_client.get_pr_for_issue.return_value = {
            "number": 100,
            "headRefName": "10-feature",
            "url": "https://github.com/owner/repo/pull/100",
        }
        mock_client.get_child_issues.return_value = [{"number": 20, "state": "open"}]
        mock_client.get_pr_head_sha.return_value = None

        update_parent_pr_status(mock_client, "github.com/owner/repo", 10)

        mock_client.set_commit_status.assert_not_called()

    def test_counts_multiple_open_children(self, mock_client):
        """Test that description shows correct count of open children."""
        mock_client.get_pr_for_issue.return_value = {
            "number": 100,
            "headRefName": "10-feature",
            "url": "https://github.com/owner/repo/pull/100",
        }
        mock_client.get_child_issues.return_value = [
            {"number": 20, "state": "open"},
            {"number": 21, "state": "open"},
            {"number": 22, "state": "open"},
            {"number": 23, "state": "closed"},
        ]
        mock_client.get_pr_head_sha.return_value = "abc123def456"

        update_parent_pr_status(mock_client, "github.com/owner/repo", 10)

        mock_client.set_commit_status.assert_called_once()
        call_kwargs = mock_client.set_commit_status.call_args[1]
        assert call_kwargs["state"] == "failure"
        assert "3 child issue(s) still open" in call_kwargs["description"]
