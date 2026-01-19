"""Unit tests for the child issue checker module."""

from unittest.mock import MagicMock

import pytest

from src.child_issue_checker import CHILD_ISSUES_CONTEXT, update_parent_pr_status


@pytest.mark.unit
class TestUpdateParentPrStatus:
    """Tests for update_parent_pr_status function."""

    def test_update_status_with_open_children(self):
        """Test that status is pending when children are open."""
        mock_client = MagicMock()
        mock_client.get_pr_for_issue.return_value = {"number": 10, "url": "https://..."}
        mock_client.get_pr_head_sha.return_value = "abc123"
        mock_client.get_child_issues.return_value = [
            {"number": 5, "state": "OPEN"},
            {"number": 6, "state": "CLOSED"},
        ]
        mock_client.set_commit_status.return_value = True

        result = update_parent_pr_status(mock_client, "github.com/owner/repo", 1)

        assert result is True
        mock_client.set_commit_status.assert_called_once_with(
            repo="github.com/owner/repo",
            sha="abc123",
            state="pending",
            context=CHILD_ISSUES_CONTEXT,
            description="1 of 2 child issue(s) still open",
        )

    def test_update_status_all_children_closed(self):
        """Test that status is success when all children are closed."""
        mock_client = MagicMock()
        mock_client.get_pr_for_issue.return_value = {"number": 10, "url": "https://..."}
        mock_client.get_pr_head_sha.return_value = "abc123"
        mock_client.get_child_issues.return_value = [
            {"number": 5, "state": "CLOSED"},
            {"number": 6, "state": "CLOSED"},
        ]
        mock_client.set_commit_status.return_value = True

        result = update_parent_pr_status(mock_client, "github.com/owner/repo", 1)

        assert result is True
        mock_client.set_commit_status.assert_called_once_with(
            repo="github.com/owner/repo",
            sha="abc123",
            state="success",
            context=CHILD_ISSUES_CONTEXT,
            description="All 2 child issue(s) resolved",
        )

    def test_update_status_no_children(self):
        """Test that status is success when no children exist."""
        mock_client = MagicMock()
        mock_client.get_pr_for_issue.return_value = {"number": 10, "url": "https://..."}
        mock_client.get_pr_head_sha.return_value = "abc123"
        mock_client.get_child_issues.return_value = []
        mock_client.set_commit_status.return_value = True

        result = update_parent_pr_status(mock_client, "github.com/owner/repo", 1)

        assert result is True
        mock_client.set_commit_status.assert_called_once_with(
            repo="github.com/owner/repo",
            sha="abc123",
            state="success",
            context=CHILD_ISSUES_CONTEXT,
            description="No child issues",
        )

    def test_returns_false_when_no_parent_pr(self):
        """Test that function returns False when parent has no PR."""
        mock_client = MagicMock()
        mock_client.get_pr_for_issue.return_value = None

        result = update_parent_pr_status(mock_client, "github.com/owner/repo", 1)

        assert result is False
        mock_client.set_commit_status.assert_not_called()

    def test_returns_false_when_no_head_sha(self):
        """Test that function returns False when PR HEAD SHA not found."""
        mock_client = MagicMock()
        mock_client.get_pr_for_issue.return_value = {"number": 10, "url": "https://..."}
        mock_client.get_pr_head_sha.return_value = None

        result = update_parent_pr_status(mock_client, "github.com/owner/repo", 1)

        assert result is False
        mock_client.set_commit_status.assert_not_called()

    def test_multiple_open_children(self):
        """Test message when multiple children are open."""
        mock_client = MagicMock()
        mock_client.get_pr_for_issue.return_value = {"number": 10, "url": "https://..."}
        mock_client.get_pr_head_sha.return_value = "abc123"
        mock_client.get_child_issues.return_value = [
            {"number": 5, "state": "OPEN"},
            {"number": 6, "state": "OPEN"},
            {"number": 7, "state": "CLOSED"},
        ]
        mock_client.set_commit_status.return_value = True

        update_parent_pr_status(mock_client, "github.com/owner/repo", 1)

        mock_client.set_commit_status.assert_called_once()
        call_kwargs = mock_client.set_commit_status.call_args[1]
        assert call_kwargs["state"] == "pending"
        assert call_kwargs["description"] == "2 of 3 child issue(s) still open"
