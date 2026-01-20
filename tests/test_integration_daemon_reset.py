"""Integration tests for Daemon reset/cleanup functionality.

Tests for clearing kiln content and closing PRs/deleting branches.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.daemon import Daemon
from src.interfaces import LinkedPullRequest, TicketItem


# ============================================================================
# Daemon Clear Kiln Content Tests
# ============================================================================


@pytest.mark.integration
class TestDaemonClearKilnContent:
    """Tests for Daemon._clear_kiln_content() method."""

    @pytest.fixture
    def daemon(self, temp_workspace_dir):
        """Create a daemon instance for testing."""
        config = MagicMock()
        config.poll_interval = 60
        config.watched_statuses = ["Research", "Plan"]
        config.max_concurrent_workflows = 2
        config.database_path = f"{temp_workspace_dir}/test.db"
        config.workspace_dir = temp_workspace_dir
        config.project_urls = []
        config.stage_models = {}
        config.github_enterprise_version = None

        with patch("src.ticket_clients.github.GitHubTicketClient"):
            daemon = Daemon(config)
            daemon.ticket_client = MagicMock()
            yield daemon
            daemon.stop()

    def test_clear_kiln_content_legacy_research_marker(self, daemon):
        """Test clearing research block with legacy end marker <!-- /kiln -->."""
        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            title="Test Issue",
            repo="github.com/owner/repo",
            status="Research",
        )

        original_description = "This is the issue description."
        research_content = """
---
<!-- kiln:research -->
## Research Findings
Some research content here.
<!-- /kiln -->"""
        body_with_legacy_research = original_description + research_content

        daemon.ticket_client.get_ticket_body.return_value = body_with_legacy_research

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            daemon._clear_kiln_content(item)

            # Verify subprocess was called with cleaned body
            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            assert "gh" in call_args
            assert "issue" in call_args
            assert "edit" in call_args
            assert "--body" in call_args

            # Get the body that was passed to gh issue edit
            body_index = call_args.index("--body") + 1
            cleaned_body = call_args[body_index]

            # Verify research content was removed
            assert "kiln:research" not in cleaned_body
            assert "Research Findings" not in cleaned_body
            assert "<!-- /kiln -->" not in cleaned_body
            # Verify original description is preserved
            assert original_description in cleaned_body

    def test_clear_kiln_content_legacy_plan_marker(self, daemon):
        """Test clearing plan block with legacy end marker <!-- /kiln -->."""
        item = TicketItem(
            item_id="PVI_456",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=99,
            title="Test Issue with Plan",
            repo="github.com/owner/repo",
            status="Plan",
        )

        original_description = "My original issue description."
        plan_content = """
---
<!-- kiln:plan -->
## Implementation Plan
Step 1: Do something
Step 2: Do another thing
<!-- /kiln -->"""
        body_with_legacy_plan = original_description + plan_content

        daemon.ticket_client.get_ticket_body.return_value = body_with_legacy_plan

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            daemon._clear_kiln_content(item)

            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            body_index = call_args.index("--body") + 1
            cleaned_body = call_args[body_index]

            # Verify plan content was removed
            assert "kiln:plan" not in cleaned_body
            assert "Implementation Plan" not in cleaned_body
            assert "<!-- /kiln -->" not in cleaned_body
            # Verify original description is preserved
            assert original_description in cleaned_body

    def test_clear_kiln_content_mixed_markers(self, daemon):
        """Test clearing content with both legacy and new-style markers."""
        item = TicketItem(
            item_id="PVI_789",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=101,
            title="Test Issue with Mixed Markers",
            repo="github.com/owner/repo",
            status="Plan",
        )

        original_description = "Original description here."
        # Research with legacy end marker
        research_content = """
---
<!-- kiln:research -->
## Research
Research findings.
<!-- /kiln -->"""
        # Plan with new-style end marker
        plan_content = """
---
<!-- kiln:plan -->
## Plan
Implementation steps.
<!-- /kiln:plan -->"""

        body_with_mixed = original_description + research_content + plan_content

        daemon.ticket_client.get_ticket_body.return_value = body_with_mixed

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            daemon._clear_kiln_content(item)

            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            body_index = call_args.index("--body") + 1
            cleaned_body = call_args[body_index]

            # Verify both research and plan content were removed
            assert "kiln:research" not in cleaned_body
            assert "kiln:plan" not in cleaned_body
            assert "Research findings" not in cleaned_body
            assert "Implementation steps" not in cleaned_body
            assert "<!-- /kiln -->" not in cleaned_body
            assert "<!-- /kiln:plan -->" not in cleaned_body
            # Verify original description is preserved
            assert original_description in cleaned_body

    def test_clear_kiln_content_legacy_research_no_separator(self, daemon):
        """Test clearing research block with legacy marker but no separator."""
        item = TicketItem(
            item_id="PVI_111",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=55,
            title="Test Issue",
            repo="github.com/owner/repo",
            status="Research",
        )

        original_description = "Description without separator."
        # Research without --- separator
        research_content = """
<!-- kiln:research -->
## Research
Content here.
<!-- /kiln -->"""
        body = original_description + research_content

        daemon.ticket_client.get_ticket_body.return_value = body

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            daemon._clear_kiln_content(item)

            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            body_index = call_args.index("--body") + 1
            cleaned_body = call_args[body_index]

            # Verify research content was removed
            assert "kiln:research" not in cleaned_body
            assert "Content here" not in cleaned_body
            # Verify original description is preserved
            assert original_description in cleaned_body

    def test_clear_kiln_content_legacy_plan_no_separator(self, daemon):
        """Test clearing plan block with legacy marker but no separator."""
        item = TicketItem(
            item_id="PVI_222",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=66,
            title="Test Issue",
            repo="github.com/owner/repo",
            status="Plan",
        )

        original_description = "Another description."
        # Plan without --- separator
        plan_content = """
<!-- kiln:plan -->
## Plan
Plan steps here.
<!-- /kiln -->"""
        body = original_description + plan_content

        daemon.ticket_client.get_ticket_body.return_value = body

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            daemon._clear_kiln_content(item)

            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            body_index = call_args.index("--body") + 1
            cleaned_body = call_args[body_index]

            # Verify plan content was removed
            assert "kiln:plan" not in cleaned_body
            assert "Plan steps here" not in cleaned_body
            # Verify original description is preserved
            assert original_description in cleaned_body

    def test_clear_kiln_content_new_style_markers_still_work(self, daemon):
        """Test that new-style markers continue to work (regression test)."""
        item = TicketItem(
            item_id="PVI_333",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=77,
            title="Test Issue",
            repo="github.com/owner/repo",
            status="Plan",
        )

        original_description = "Original content."
        research_content = """
---
<!-- kiln:research -->
## Research
Research data.
<!-- /kiln:research -->"""
        plan_content = """
---
<!-- kiln:plan -->
## Plan
Plan data.
<!-- /kiln:plan -->"""
        body = original_description + research_content + plan_content

        daemon.ticket_client.get_ticket_body.return_value = body

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            daemon._clear_kiln_content(item)

            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            body_index = call_args.index("--body") + 1
            cleaned_body = call_args[body_index]

            # Verify both sections were removed
            assert "kiln:research" not in cleaned_body
            assert "kiln:plan" not in cleaned_body
            assert "Research data" not in cleaned_body
            assert "Plan data" not in cleaned_body
            # Verify original description is preserved
            assert original_description in cleaned_body


# ============================================================================
# Daemon Close PRs and Delete Branches Tests
# ============================================================================


class TestDaemonClosePrsAndDeleteBranches:
    """Tests for Daemon._close_prs_and_delete_branches() method."""

    @pytest.fixture
    def daemon(self, temp_workspace_dir):
        """Create a daemon instance for testing."""
        config = MagicMock()
        config.poll_interval = 60
        config.watched_statuses = ["Research", "Plan"]
        config.max_concurrent_workflows = 2
        config.database_path = f"{temp_workspace_dir}/test.db"
        config.workspace_dir = temp_workspace_dir
        config.project_urls = []
        config.stage_models = {}
        config.github_enterprise_version = None

        with patch("src.ticket_clients.github.GitHubTicketClient"):
            daemon = Daemon(config)
            daemon.ticket_client = MagicMock()
            yield daemon
            daemon.stop()

    def test_close_pr_and_delete_branch_for_open_pr(self, daemon):
        """Test that open PRs are closed and their branches are deleted."""
        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            title="Test Issue",
            repo="github.com/owner/repo",
            status="Implement",
        )

        linked_prs = [
            LinkedPullRequest(
                number=100,
                url="https://github.com/owner/repo/pull/100",
                body="Closes #42",
                state="OPEN",
                merged=False,
                branch_name="42-feature-branch",
            )
        ]

        daemon.ticket_client.get_linked_prs.return_value = linked_prs
        daemon.ticket_client.close_pr.return_value = True
        daemon.ticket_client.delete_branch.return_value = True

        daemon._close_prs_and_delete_branches(item)

        daemon.ticket_client.get_linked_prs.assert_called_once_with(
            "github.com/owner/repo", 42
        )
        daemon.ticket_client.close_pr.assert_called_once_with(
            "github.com/owner/repo", 100
        )
        daemon.ticket_client.delete_branch.assert_called_once_with(
            "github.com/owner/repo", "42-feature-branch"
        )

    def test_skip_merged_pr(self, daemon):
        """Test that merged PRs are skipped (not closed, branch not deleted)."""
        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            title="Test Issue",
            repo="github.com/owner/repo",
            status="Implement",
        )

        linked_prs = [
            LinkedPullRequest(
                number=100,
                url="https://github.com/owner/repo/pull/100",
                body="Closes #42",
                state="MERGED",
                merged=True,
                branch_name="42-feature-branch",
            )
        ]

        daemon.ticket_client.get_linked_prs.return_value = linked_prs

        daemon._close_prs_and_delete_branches(item)

        daemon.ticket_client.get_linked_prs.assert_called_once()
        daemon.ticket_client.close_pr.assert_not_called()
        daemon.ticket_client.delete_branch.assert_not_called()

    def test_continue_processing_on_close_failure(self, daemon):
        """Test that branch deletion is attempted even if PR close fails."""
        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            title="Test Issue",
            repo="github.com/owner/repo",
            status="Implement",
        )

        linked_prs = [
            LinkedPullRequest(
                number=100,
                url="https://github.com/owner/repo/pull/100",
                body="Closes #42",
                state="OPEN",
                merged=False,
                branch_name="42-feature-branch",
            )
        ]

        daemon.ticket_client.get_linked_prs.return_value = linked_prs
        daemon.ticket_client.close_pr.return_value = False  # Failure
        daemon.ticket_client.delete_branch.return_value = True

        daemon._close_prs_and_delete_branches(item)

        # Both methods should be called even if close_pr fails
        daemon.ticket_client.close_pr.assert_called_once()
        daemon.ticket_client.delete_branch.assert_called_once()

    def test_multiple_prs_processed(self, daemon):
        """Test that all linked PRs are processed."""
        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            title="Test Issue",
            repo="github.com/owner/repo",
            status="Implement",
        )

        linked_prs = [
            LinkedPullRequest(
                number=100,
                url="https://github.com/owner/repo/pull/100",
                body="Closes #42",
                state="OPEN",
                merged=False,
                branch_name="42-feature-branch-1",
            ),
            LinkedPullRequest(
                number=101,
                url="https://github.com/owner/repo/pull/101",
                body="Closes #42",
                state="OPEN",
                merged=False,
                branch_name="42-feature-branch-2",
            ),
        ]

        daemon.ticket_client.get_linked_prs.return_value = linked_prs
        daemon.ticket_client.close_pr.return_value = True
        daemon.ticket_client.delete_branch.return_value = True

        daemon._close_prs_and_delete_branches(item)

        assert daemon.ticket_client.close_pr.call_count == 2
        assert daemon.ticket_client.delete_branch.call_count == 2

    def test_no_linked_prs(self, daemon):
        """Test handling when there are no linked PRs."""
        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            title="Test Issue",
            repo="github.com/owner/repo",
            status="Implement",
        )

        daemon.ticket_client.get_linked_prs.return_value = []

        daemon._close_prs_and_delete_branches(item)

        daemon.ticket_client.get_linked_prs.assert_called_once()
        daemon.ticket_client.close_pr.assert_not_called()
        daemon.ticket_client.delete_branch.assert_not_called()

    def test_pr_without_branch_name(self, daemon):
        """Test handling PR without branch_name (branch deletion is skipped)."""
        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            title="Test Issue",
            repo="github.com/owner/repo",
            status="Implement",
        )

        linked_prs = [
            LinkedPullRequest(
                number=100,
                url="https://github.com/owner/repo/pull/100",
                body="Closes #42",
                state="OPEN",
                merged=False,
                branch_name=None,  # No branch name
            )
        ]

        daemon.ticket_client.get_linked_prs.return_value = linked_prs
        daemon.ticket_client.close_pr.return_value = True

        daemon._close_prs_and_delete_branches(item)

        daemon.ticket_client.close_pr.assert_called_once()
        daemon.ticket_client.delete_branch.assert_not_called()

    def test_get_linked_prs_failure(self, daemon):
        """Test handling when get_linked_prs raises an exception."""
        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            title="Test Issue",
            repo="github.com/owner/repo",
            status="Implement",
        )

        daemon.ticket_client.get_linked_prs.side_effect = Exception("API error")

        # Should not raise, just log warning and return
        daemon._close_prs_and_delete_branches(item)

        daemon.ticket_client.close_pr.assert_not_called()
        daemon.ticket_client.delete_branch.assert_not_called()

    def test_mixed_merged_and_open_prs(self, daemon):
        """Test that only open PRs are processed, merged ones are skipped."""
        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            title="Test Issue",
            repo="github.com/owner/repo",
            status="Implement",
        )

        linked_prs = [
            LinkedPullRequest(
                number=100,
                url="https://github.com/owner/repo/pull/100",
                body="Closes #42",
                state="MERGED",
                merged=True,
                branch_name="42-merged-branch",
            ),
            LinkedPullRequest(
                number=101,
                url="https://github.com/owner/repo/pull/101",
                body="Closes #42",
                state="OPEN",
                merged=False,
                branch_name="42-open-branch",
            ),
        ]

        daemon.ticket_client.get_linked_prs.return_value = linked_prs
        daemon.ticket_client.close_pr.return_value = True
        daemon.ticket_client.delete_branch.return_value = True

        daemon._close_prs_and_delete_branches(item)

        # Only the open PR should be processed
        daemon.ticket_client.close_pr.assert_called_once_with(
            "github.com/owner/repo", 101
        )
        daemon.ticket_client.delete_branch.assert_called_once_with(
            "github.com/owner/repo", "42-open-branch"
        )
