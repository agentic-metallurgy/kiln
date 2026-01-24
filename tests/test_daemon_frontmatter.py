"""Unit tests for Daemon frontmatter integration.

These tests verify that the daemon correctly:
- Parses frontmatter from issue body
- Uses explicit feature_branch when set
- Skips parent PR lookup when feature_branch is set
- Falls back to parent detection when no feature_branch
"""

from unittest.mock import MagicMock, patch

import pytest

from src.daemon import Daemon


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
    return item


@pytest.mark.unit
class TestDaemonFrontmatterIntegration:
    """Tests for frontmatter parsing in _auto_prepare_worktree."""

    def test_feature_branch_from_frontmatter_used(self, daemon, mock_item):
        """Test that explicit feature_branch from frontmatter is used."""
        issue_body = """---
feature_branch: my-feature
---

Issue description here.
"""
        daemon.ticket_client.get_ticket_body.return_value = issue_body

        with patch("src.daemon.logger") as mock_logger:
            daemon._auto_prepare_worktree(mock_item)

            # Should log that we're using explicit feature_branch
            mock_logger.info.assert_any_call(
                "Using explicit feature_branch 'my-feature' from issue frontmatter"
            )

    def test_feature_branch_skips_parent_pr_lookup(self, daemon, mock_item):
        """Test that _get_parent_pr_info is NOT called when feature_branch is set."""
        issue_body = """---
feature_branch: develop
---

Issue description.
"""
        daemon.ticket_client.get_ticket_body.return_value = issue_body

        with patch.object(daemon, "_get_parent_pr_info") as mock_get_parent:
            daemon._auto_prepare_worktree(mock_item)

            # Should NOT call _get_parent_pr_info
            mock_get_parent.assert_not_called()

    def test_no_frontmatter_falls_back_to_parent_detection(self, daemon, mock_item):
        """Test that parent PR detection is used when no frontmatter."""
        issue_body = """## Description

No frontmatter in this issue.
"""
        daemon.ticket_client.get_ticket_body.return_value = issue_body

        with patch.object(daemon, "_get_parent_pr_info") as mock_get_parent:
            mock_get_parent.return_value = (100, "parent-branch")
            daemon._auto_prepare_worktree(mock_item)

            # Should call _get_parent_pr_info
            mock_get_parent.assert_called_once_with(
                mock_item.repo, mock_item.ticket_id
            )

    def test_empty_frontmatter_falls_back_to_parent_detection(self, daemon, mock_item):
        """Test that parent detection is used with empty frontmatter."""
        issue_body = """---
other_setting: value
---

No feature_branch setting.
"""
        daemon.ticket_client.get_ticket_body.return_value = issue_body

        with patch.object(daemon, "_get_parent_pr_info") as mock_get_parent:
            mock_get_parent.return_value = (None, None)
            daemon._auto_prepare_worktree(mock_item)

            # Should call _get_parent_pr_info since no feature_branch
            mock_get_parent.assert_called_once()

    def test_feature_branch_passed_to_workflow_context(self, daemon, mock_item):
        """Test that feature_branch is passed as parent_branch in context."""
        issue_body = """---
feature_branch: release/v2.0
---

Issue description.
"""
        daemon.ticket_client.get_ticket_body.return_value = issue_body

        daemon._auto_prepare_worktree(mock_item)

        # Check the context passed to runner.run()
        call_args = daemon.runner.run.call_args
        ctx = call_args[0][1]  # Second positional argument is the context
        assert ctx.parent_branch == "release/v2.0"
        assert ctx.parent_issue_number is None  # Should be None for explicit feature_branch

    def test_parent_branch_from_parent_issue_passed_to_context(self, daemon, mock_item):
        """Test that parent branch from parent issue is passed correctly."""
        issue_body = "No frontmatter"
        daemon.ticket_client.get_ticket_body.return_value = issue_body

        with patch.object(daemon, "_get_parent_pr_info") as mock_get_parent:
            mock_get_parent.return_value = (99, "parent-pr-branch")
            daemon._auto_prepare_worktree(mock_item)

            # Check the context passed to runner.run()
            call_args = daemon.runner.run.call_args
            ctx = call_args[0][1]
            assert ctx.parent_branch == "parent-pr-branch"
            assert ctx.parent_issue_number == 99

    def test_none_issue_body_falls_back_to_parent_detection(self, daemon, mock_item):
        """Test that None issue body falls back to parent detection."""
        daemon.ticket_client.get_ticket_body.return_value = None

        with patch.object(daemon, "_get_parent_pr_info") as mock_get_parent:
            mock_get_parent.return_value = (None, None)
            daemon._auto_prepare_worktree(mock_item)

            mock_get_parent.assert_called_once()

    def test_feature_branch_logs_auto_prepared_message(self, daemon, mock_item):
        """Test that auto-prepared log message includes feature branch info."""
        issue_body = """---
feature_branch: develop
---

Description.
"""
        daemon.ticket_client.get_ticket_body.return_value = issue_body

        with patch("src.daemon.logger") as mock_logger:
            daemon._auto_prepare_worktree(mock_item)

            # Should log auto-prepared with branch info
            mock_logger.info.assert_any_call(
                "Auto-prepared worktree (branching from parent branch 'develop')"
            )
