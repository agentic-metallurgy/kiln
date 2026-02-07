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
        issue_body = """```
feature_branch: my-feature
```

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
        issue_body = """```
feature_branch: develop
```

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
        issue_body = """```
other_setting: value
```

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
        issue_body = """```
feature_branch: release/v2.0
```

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
        issue_body = """```
feature_branch: develop
```

Description.
"""
        daemon.ticket_client.get_ticket_body.return_value = issue_body

        with patch("src.daemon.logger") as mock_logger:
            daemon._auto_prepare_worktree(mock_item)

            # Should log auto-prepared with branch info
            mock_logger.info.assert_any_call(
                "Auto-prepared worktree (branching from parent branch 'develop')"
            )


@pytest.mark.integration
class TestDaemonFrontmatterIntegrationTests:
    """Integration tests for feature_branch functionality across daemon methods."""

    def test_auto_prepare_worktree_with_feature_branch_full_flow(
        self, daemon, mock_item
    ):
        """Integration test: _auto_prepare_worktree with feature_branch frontmatter.

        Verifies the complete flow:
        1. Issue body with frontmatter is fetched
        2. Frontmatter is parsed correctly
        3. feature_branch is extracted
        4. _get_parent_pr_info is NOT called
        5. PrepareWorkflow is invoked with correct context
        """
        issue_body = """```
feature_branch: release/v2.0
```

## Description

This is an issue that should branch from release/v2.0.
"""
        daemon.ticket_client.get_ticket_body.return_value = issue_body

        with patch.object(daemon, "_get_parent_pr_info") as mock_get_parent:
            daemon._auto_prepare_worktree(mock_item)

            # Verify _get_parent_pr_info was NOT called (optimization)
            mock_get_parent.assert_not_called()

            # Verify runner.run was called with correct context
            call_args = daemon.runner.run.call_args
            assert call_args is not None

            workflow = call_args[0][0]  # First arg is workflow
            ctx = call_args[0][1]  # Second arg is context

            # Verify workflow is PrepareWorkflow
            assert workflow.__class__.__name__ == "PrepareWorkflow"

            # Verify context has correct values
            assert ctx.parent_branch == "release/v2.0"
            assert ctx.parent_issue_number is None
            assert ctx.repo == mock_item.repo
            assert ctx.issue_number == mock_item.ticket_id

    def test_auto_prepare_worktree_feature_branch_skips_parent_pr_info(
        self, daemon, mock_item
    ):
        """Integration test: verify _get_parent_pr_info is skipped when feature_branch is set.

        This is an important optimization - when an explicit feature_branch is set,
        we don't need to query for parent issue's PR branch.
        """
        issue_body = """```
feature_branch: develop
```

Description with explicit feature branch.
"""
        daemon.ticket_client.get_ticket_body.return_value = issue_body

        # Setup a mock that would return parent info if called
        with patch.object(daemon, "_get_parent_pr_info") as mock_get_parent:
            mock_get_parent.return_value = (
                123,
                "parent-branch-should-not-be-used",
            )

            daemon._auto_prepare_worktree(mock_item)

            # Verify _get_parent_pr_info was NOT called
            mock_get_parent.assert_not_called()

            # Verify the explicit feature_branch was used
            ctx = daemon.runner.run.call_args[0][1]
            assert ctx.parent_branch == "develop"

    def test_run_workflow_passes_parent_branch_to_context_for_implement(
        self, daemon, mock_item
    ):
        """Integration test: _run_workflow passes parent_branch to context for Implement.

        When running the Implement workflow, parent_branch should be resolved
        from frontmatter (or parent detection) and passed to WorkflowContext.
        This enables PR creation with the correct --base flag.
        """
        issue_body = """```
feature_branch: hotfix/v1.5
```

Description of hotfix issue.
"""
        daemon.ticket_client.get_ticket_body.return_value = issue_body
        mock_item.labels = []  # No labels

        # Setup workflow runner to capture the context
        captured_context = None

        def capture_workflow_execute(ctx, config):
            nonlocal captured_context
            captured_context = ctx

        # Create a mock workflow class that captures the context
        mock_workflow_instance = MagicMock()
        mock_workflow_instance.execute = capture_workflow_execute

        # Replace the workflow class in WORKFLOW_MAP
        original_workflow_class = daemon.WORKFLOW_MAP["Implement"]
        daemon.WORKFLOW_MAP["Implement"] = MagicMock(return_value=mock_workflow_instance)

        try:
            daemon._run_workflow("Implement", mock_item)

            # Verify context has parent_branch from frontmatter
            assert captured_context is not None
            assert captured_context.parent_branch == "hotfix/v1.5"
            assert captured_context.parent_issue_number is None
        finally:
            # Restore original workflow class
            daemon.WORKFLOW_MAP["Implement"] = original_workflow_class

    def test_run_workflow_falls_back_to_parent_detection_for_implement(
        self, daemon, mock_item
    ):
        """Integration test: _run_workflow falls back to parent detection when no frontmatter.

        When no feature_branch is set in frontmatter, _run_workflow should
        call _get_parent_pr_info to detect parent branch from sub-issues.
        """
        issue_body = """## Description

This issue has a parent issue with an open PR.
"""
        daemon.ticket_client.get_ticket_body.return_value = issue_body
        mock_item.labels = []

        # Setup workflow runner to capture the context
        captured_context = None

        def capture_workflow_execute(ctx, config):
            nonlocal captured_context
            captured_context = ctx

        # Create a mock workflow class that captures the context
        mock_workflow_instance = MagicMock()
        mock_workflow_instance.execute = capture_workflow_execute

        # Replace the workflow class in WORKFLOW_MAP
        original_workflow_class = daemon.WORKFLOW_MAP["Implement"]
        daemon.WORKFLOW_MAP["Implement"] = MagicMock(return_value=mock_workflow_instance)

        try:
            with patch.object(daemon, "_get_parent_pr_info") as mock_get_parent:
                mock_get_parent.return_value = (99, "parent-issue-99-branch")

                daemon._run_workflow("Implement", mock_item)

                # Verify _get_parent_pr_info was called
                mock_get_parent.assert_called_once_with(
                    mock_item.repo, mock_item.ticket_id
                )

                # Verify context has parent_branch from parent detection
                assert captured_context is not None
                assert captured_context.parent_branch == "parent-issue-99-branch"
                assert captured_context.parent_issue_number == 99
        finally:
            # Restore original workflow class
            daemon.WORKFLOW_MAP["Implement"] = original_workflow_class

    def test_run_workflow_no_parent_branch_when_no_frontmatter_and_no_parent(
        self, daemon, mock_item
    ):
        """Integration test: _run_workflow sets parent_branch to None when no source.

        When there's no feature_branch in frontmatter and no parent issue,
        parent_branch should be None.
        """
        issue_body = "Simple issue without frontmatter or parent."
        daemon.ticket_client.get_ticket_body.return_value = issue_body
        mock_item.labels = []

        captured_context = None

        def capture_workflow_execute(ctx, config):
            nonlocal captured_context
            captured_context = ctx

        # Create a mock workflow class that captures the context
        mock_workflow_instance = MagicMock()
        mock_workflow_instance.execute = capture_workflow_execute

        # Replace the workflow class in WORKFLOW_MAP
        original_workflow_class = daemon.WORKFLOW_MAP["Implement"]
        daemon.WORKFLOW_MAP["Implement"] = MagicMock(return_value=mock_workflow_instance)

        try:
            with patch.object(daemon, "_get_parent_pr_info") as mock_get_parent:
                mock_get_parent.return_value = (None, None)

                daemon._run_workflow("Implement", mock_item)

                # Verify context has no parent_branch
                assert captured_context is not None
                assert captured_context.parent_branch is None
                assert captured_context.parent_issue_number is None
        finally:
            # Restore original workflow class
            daemon.WORKFLOW_MAP["Implement"] = original_workflow_class
