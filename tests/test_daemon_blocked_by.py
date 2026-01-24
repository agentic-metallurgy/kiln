"""Unit tests for Daemon blocked_by functionality.

These tests verify that the daemon correctly:
- Normalizes blocked_by from frontmatter (int, list, None)
- Checks if an issue is blocked by other issues without merged PRs
- Handles API errors gracefully (fail-safe behavior)
"""

from unittest.mock import MagicMock, patch

import pytest

from src.daemon import Daemon
from src.interfaces.ticket import LinkedPullRequest


@pytest.fixture
def daemon(temp_workspace_dir):
    """Fixture providing Daemon with mocked dependencies."""
    config = MagicMock()
    config.poll_interval = 60
    config.watched_statuses = ["Research", "Plan", "Implement"]
    config.max_concurrent_workflows = 2
    config.database_path = f"{temp_workspace_dir}/test.db"
    config.workspace_dir = temp_workspace_dir
    config.project_urls = ["https://github.com/orgs/test/projects/1"]
    config.stage_models = {}
    config.github_enterprise_version = None
    config.username_self = "test-bot"

    with patch("src.ticket_clients.github.GitHubTicketClient"):
        daemon = Daemon(config)
        daemon.ticket_client = MagicMock()
        daemon.runner = MagicMock()
        yield daemon
        daemon.stop()


@pytest.fixture
def mock_item():
    """Fixture providing a mock TicketItem."""
    item = MagicMock()
    item.repo = "github.com/test-org/test-repo"
    item.ticket_id = 42
    item.title = "Test Issue"
    item.board_url = "https://github.com/orgs/test-org/projects/1"
    item.labels = []
    return item


@pytest.mark.unit
class TestNormalizeBlockedBy:
    """Tests for _normalize_blocked_by static method."""

    def test_none_returns_empty_list(self):
        """Test that None returns an empty list."""
        result = Daemon._normalize_blocked_by(None)
        assert result == []

    def test_single_int_returns_list_with_one_element(self):
        """Test that a single int returns a list with that int."""
        result = Daemon._normalize_blocked_by(115)
        assert result == [115]

    def test_list_returns_same_list(self):
        """Test that a list returns the same list."""
        result = Daemon._normalize_blocked_by([115, 116])
        assert result == [115, 116]

    def test_empty_list_returns_empty_list(self):
        """Test that an empty list returns an empty list."""
        result = Daemon._normalize_blocked_by([])
        assert result == []


@pytest.mark.unit
class TestIsBlockedByUnmergedIssues:
    """Tests for _is_blocked_by_unmerged_issues method."""

    def test_no_blocked_by_returns_false_empty(self, daemon, mock_item):
        """Test returns (False, []) when no blocked_by in frontmatter."""
        daemon.ticket_client.get_ticket_body.return_value = """## Description

This issue has no blocked_by setting.
"""
        result = daemon._is_blocked_by_unmerged_issues(mock_item)
        assert result == (False, [])

    def test_blocker_with_merged_pr_returns_not_blocked(self, daemon, mock_item):
        """Test returns (False, []) when blocker has a merged PR."""
        daemon.ticket_client.get_ticket_body.return_value = """---
blocked_by: 115
---

This issue is blocked by #115.
"""
        # Blocker #115 has a merged PR
        daemon.ticket_client.get_linked_prs.return_value = [
            LinkedPullRequest(
                number=200,
                url="https://github.com/test-org/test-repo/pull/200",
                body="Closes #115",
                state="MERGED",
                merged=True,
                branch_name="fix-115",
            )
        ]

        result = daemon._is_blocked_by_unmerged_issues(mock_item)
        assert result == (False, [])
        daemon.ticket_client.get_linked_prs.assert_called_once_with(
            mock_item.repo, 115
        )

    def test_blocker_without_merged_pr_returns_blocked(self, daemon, mock_item):
        """Test returns (True, [blocker]) when blocker has no merged PR."""
        daemon.ticket_client.get_ticket_body.return_value = """---
blocked_by: 115
---

This issue is blocked by #115.
"""
        # Blocker #115 has an open (not merged) PR
        daemon.ticket_client.get_linked_prs.return_value = [
            LinkedPullRequest(
                number=200,
                url="https://github.com/test-org/test-repo/pull/200",
                body="Closes #115",
                state="OPEN",
                merged=False,
                branch_name="fix-115",
            )
        ]

        result = daemon._is_blocked_by_unmerged_issues(mock_item)
        assert result == (True, [115])

    def test_blocker_with_no_pr_returns_blocked(self, daemon, mock_item):
        """Test returns (True, [blocker]) when blocker has no PR at all."""
        daemon.ticket_client.get_ticket_body.return_value = """---
blocked_by: 115
---

This issue is blocked by #115.
"""
        # Blocker #115 has no linked PRs
        daemon.ticket_client.get_linked_prs.return_value = []

        result = daemon._is_blocked_by_unmerged_issues(mock_item)
        assert result == (True, [115])

    def test_multiple_blockers_one_unmerged_returns_blocked(self, daemon, mock_item):
        """Test returns blocked with only the unmerged blocker when one of two has unmerged PR."""
        daemon.ticket_client.get_ticket_body.return_value = """---
blocked_by: [115, 116]
---

This issue is blocked by both #115 and #116.
"""
        # #115 has a merged PR, #116 does not
        def mock_get_linked_prs(repo, issue_num):
            if issue_num == 115:
                return [
                    LinkedPullRequest(
                        number=200,
                        url="https://github.com/test-org/test-repo/pull/200",
                        body="Closes #115",
                        state="MERGED",
                        merged=True,
                        branch_name="fix-115",
                    )
                ]
            else:  # issue_num == 116
                return [
                    LinkedPullRequest(
                        number=201,
                        url="https://github.com/test-org/test-repo/pull/201",
                        body="Closes #116",
                        state="OPEN",
                        merged=False,
                        branch_name="fix-116",
                    )
                ]

        daemon.ticket_client.get_linked_prs.side_effect = mock_get_linked_prs

        result = daemon._is_blocked_by_unmerged_issues(mock_item)
        assert result == (True, [116])

    def test_multiple_blockers_all_unmerged_returns_all(self, daemon, mock_item):
        """Test returns all blockers when all have unmerged PRs."""
        daemon.ticket_client.get_ticket_body.return_value = """---
blocked_by: [115, 116]
---

This issue is blocked by both #115 and #116.
"""
        # Neither has a merged PR
        daemon.ticket_client.get_linked_prs.return_value = []

        result = daemon._is_blocked_by_unmerged_issues(mock_item)
        assert result == (True, [115, 116])

    def test_multiple_blockers_all_merged_returns_not_blocked(self, daemon, mock_item):
        """Test returns not blocked when all blockers have merged PRs."""
        daemon.ticket_client.get_ticket_body.return_value = """---
blocked_by: [115, 116]
---

This issue is blocked by both #115 and #116.
"""
        # Both have merged PRs
        daemon.ticket_client.get_linked_prs.return_value = [
            LinkedPullRequest(
                number=200,
                url="https://github.com/test-org/test-repo/pull/200",
                body="Closes issue",
                state="MERGED",
                merged=True,
                branch_name="fix-branch",
            )
        ]

        result = daemon._is_blocked_by_unmerged_issues(mock_item)
        assert result == (False, [])

    def test_api_error_returns_fail_safe(self, daemon, mock_item):
        """Test returns (False, []) on API error (fail-safe behavior)."""
        daemon.ticket_client.get_ticket_body.side_effect = Exception("API Error")

        result = daemon._is_blocked_by_unmerged_issues(mock_item)
        assert result == (False, [])

    def test_get_linked_prs_error_returns_fail_safe(self, daemon, mock_item):
        """Test returns (False, []) when get_linked_prs fails (fail-safe)."""
        daemon.ticket_client.get_ticket_body.return_value = """---
blocked_by: 115
---

Blocked by #115.
"""
        daemon.ticket_client.get_linked_prs.side_effect = Exception("API Error")

        result = daemon._is_blocked_by_unmerged_issues(mock_item)
        assert result == (False, [])

    def test_empty_blocked_by_list_returns_not_blocked(self, daemon, mock_item):
        """Test returns (False, []) when blocked_by is an empty list."""
        daemon.ticket_client.get_ticket_body.return_value = """---
blocked_by: []
---

Empty blocked_by list.
"""
        result = daemon._is_blocked_by_unmerged_issues(mock_item)
        assert result == (False, [])

    def test_yaml_list_syntax_works(self, daemon, mock_item):
        """Test that YAML list syntax for blocked_by is parsed correctly."""
        daemon.ticket_client.get_ticket_body.return_value = """---
blocked_by:
  - 115
  - 116
---

YAML list syntax for blocked_by.
"""
        daemon.ticket_client.get_linked_prs.return_value = []

        result = daemon._is_blocked_by_unmerged_issues(mock_item)
        assert result == (True, [115, 116])
