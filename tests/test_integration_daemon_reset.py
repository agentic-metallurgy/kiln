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


@pytest.mark.integration
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

    def test_pr_closure_validation_success(self, daemon):
        """Test that PR closure is verified with fresh state check."""
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
        daemon.ticket_client.get_pr_state.return_value = "CLOSED"
        daemon.ticket_client.delete_branch.return_value = True

        daemon._close_prs_and_delete_branches(item)

        # Verify get_pr_state was called to validate closure
        daemon.ticket_client.get_pr_state.assert_called_once_with(
            "github.com/owner/repo", 100
        )

    def test_pr_closure_validation_state_mismatch(self, daemon, caplog):
        """Test warning logged when PR state doesn't match expected after close."""
        import logging

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
        # State check returns OPEN despite close returning True
        daemon.ticket_client.get_pr_state.return_value = "OPEN"
        daemon.ticket_client.delete_branch.return_value = True

        with caplog.at_level(logging.WARNING):
            daemon._close_prs_and_delete_branches(item)

        # Should continue to delete branch even if state mismatch
        daemon.ticket_client.delete_branch.assert_called_once()
        # Warning should be logged about state mismatch
        assert any("state is OPEN" in record.message for record in caplog.records)

    def test_pr_closure_validation_returns_none(self, daemon, caplog):
        """Test warning logged when get_pr_state returns None."""
        import logging

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
        daemon.ticket_client.get_pr_state.return_value = None  # Failed to get state
        daemon.ticket_client.delete_branch.return_value = True

        with caplog.at_level(logging.WARNING):
            daemon._close_prs_and_delete_branches(item)

        # Should continue to delete branch
        daemon.ticket_client.delete_branch.assert_called_once()
        # Warning should be logged about not being able to verify state
        assert any("Could not verify" in record.message for record in caplog.records)

    def test_close_pr_failure_logged(self, daemon, caplog):
        """Test that warning is logged when close_pr returns False."""
        import logging

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
        daemon.ticket_client.close_pr.return_value = False  # Close failed
        daemon.ticket_client.delete_branch.return_value = True

        with caplog.at_level(logging.WARNING):
            daemon._close_prs_and_delete_branches(item)

        # Should still try to delete branch
        daemon.ticket_client.delete_branch.assert_called_once()
        # Warning should be logged about close failure
        assert any("Failed to close PR" in record.message for record in caplog.records)

    def test_close_pr_failure_skips_validation(self, daemon):
        """Test that get_pr_state is not called when close_pr fails."""
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
        daemon.ticket_client.close_pr.return_value = False  # Close failed
        daemon.ticket_client.delete_branch.return_value = True

        daemon._close_prs_and_delete_branches(item)

        # get_pr_state should NOT be called if close_pr failed
        daemon.ticket_client.get_pr_state.assert_not_called()


@pytest.mark.integration
class TestDaemonResetAllowOthersTickets:
    """Tests for reset label handling with ALLOW_OTHERS_TICKETS enabled."""

    @pytest.fixture
    def daemon_allow_others(self, temp_workspace_dir):
        """Create a daemon instance with allow_others_tickets enabled."""
        config = MagicMock()
        config.poll_interval = 60
        config.watched_statuses = ["Research", "Plan"]
        config.max_concurrent_workflows = 2
        config.database_path = f"{temp_workspace_dir}/test.db"
        config.workspace_dir = temp_workspace_dir
        config.project_urls = []
        config.stage_models = {}
        config.github_enterprise_version = None
        config.username_self = "test-user"
        config.allow_others_tickets = True  # Enable bypass
        config.team_usernames = []

        with patch("src.ticket_clients.github.GitHubTicketClient"):
            daemon = Daemon(config)
            daemon.ticket_client = MagicMock()
            yield daemon
            daemon.stop()

    def test_reset_bypasses_actor_check_when_enabled(self, daemon_allow_others):
        """Test _maybe_handle_reset bypasses actor check when allow_others_tickets is enabled."""
        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            title="Test Issue",
            repo="github.com/owner/repo",
            status="Research",
            labels={"reset", "researching"},
            state="OPEN",
        )

        # Mock issue body and linked PRs
        daemon_allow_others.ticket_client.get_ticket_body.return_value = "Issue description"
        daemon_allow_others.ticket_client.get_linked_prs.return_value = []

        daemon_allow_others._maybe_handle_reset(item)

        # Should process reset without calling get_label_actor
        daemon_allow_others.ticket_client.get_label_actor.assert_not_called()
        # Should remove the reset label
        daemon_allow_others.ticket_client.remove_label.assert_called()
        # Should move to Backlog
        daemon_allow_others.ticket_client.update_item_status.assert_called_once_with(
            "PVI_123", "Backlog", hostname="github.com"
        )

    def test_reset_allows_non_self_actor_when_enabled(self, daemon_allow_others):
        """Test _maybe_handle_reset allows non-self actor when allow_others_tickets is enabled."""
        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            title="Test Issue",
            repo="github.com/owner/repo",
            status="Plan",
            labels={"reset", "planning"},
            state="OPEN",
        )

        # Mock issue body and linked PRs (reset added by "other-user")
        daemon_allow_others.ticket_client.get_ticket_body.return_value = "Issue description"
        daemon_allow_others.ticket_client.get_linked_prs.return_value = []

        daemon_allow_others._maybe_handle_reset(item)

        # Should process reset (allowing "other-user"'s action)
        daemon_allow_others.ticket_client.update_item_status.assert_called_once_with(
            "PVI_123", "Backlog", hostname="github.com"
        )

    def test_reset_disabled_blocks_non_self_actor(self, temp_workspace_dir):
        """Test _maybe_handle_reset blocks non-self actor when allow_others_tickets is disabled."""
        config = MagicMock()
        config.poll_interval = 60
        config.watched_statuses = ["Research", "Plan"]
        config.max_concurrent_workflows = 2
        config.database_path = f"{temp_workspace_dir}/test.db"
        config.workspace_dir = temp_workspace_dir
        config.project_urls = []
        config.stage_models = {}
        config.github_enterprise_version = None
        config.username_self = "test-user"
        config.allow_others_tickets = False  # Disable bypass
        config.team_usernames = ["teammate"]

        with patch("src.ticket_clients.github.GitHubTicketClient"):
            daemon = Daemon(config)
            daemon.ticket_client = MagicMock()

            item = TicketItem(
                item_id="PVI_123",
                board_url="https://github.com/orgs/test/projects/1",
                ticket_id=42,
                title="Test Issue",
                repo="github.com/owner/repo",
                status="Research",
                labels={"reset", "researching"},
                state="OPEN",
            )

            # Mock get_label_actor to return a non-allowed user
            daemon.ticket_client.get_label_actor.return_value = "blocked-user"

            daemon._maybe_handle_reset(item)

            # Should call get_label_actor
            daemon.ticket_client.get_label_actor.assert_called_once()
            # Should NOT move to Backlog (blocked user)
            daemon.ticket_client.update_item_status.assert_not_called()

            daemon.stop()
