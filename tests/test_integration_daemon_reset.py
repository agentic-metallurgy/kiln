"""Integration tests for ResetHandler reset/cleanup functionality.

Tests for clearing kiln content and closing PRs/deleting branches.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.interfaces import LinkedPullRequest, TicketItem
from src.reset_handler import ResetHandler

# ============================================================================
# ResetHandler Clear Kiln Content Tests
# ============================================================================


@pytest.mark.integration
class TestResetHandlerClearKilnContent:
    """Tests for ResetHandler._clear_kiln_content() method."""

    @pytest.fixture
    def reset_handler(self, temp_workspace_dir):
        """Create a ResetHandler instance for testing."""
        ticket_client = MagicMock()
        workspace_manager = MagicMock()

        handler = ResetHandler(
            ticket_client=ticket_client,
            workspace_manager=workspace_manager,
            username_self="kiln-bot",
            team_usernames=[],
            workspace_dir=temp_workspace_dir,
        )
        yield handler

    def test_clear_kiln_content_legacy_research_marker(self, reset_handler):
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

        reset_handler.ticket_client.get_ticket_body.return_value = body_with_legacy_research

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            reset_handler._clear_kiln_content(item)

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

    def test_clear_kiln_content_legacy_plan_marker(self, reset_handler):
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

        reset_handler.ticket_client.get_ticket_body.return_value = body_with_legacy_plan

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            reset_handler._clear_kiln_content(item)

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

    def test_clear_kiln_content_mixed_markers(self, reset_handler):
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

        reset_handler.ticket_client.get_ticket_body.return_value = body_with_mixed

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            reset_handler._clear_kiln_content(item)

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

    def test_clear_kiln_content_legacy_research_no_separator(self, reset_handler):
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

        reset_handler.ticket_client.get_ticket_body.return_value = body

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            reset_handler._clear_kiln_content(item)

            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            body_index = call_args.index("--body") + 1
            cleaned_body = call_args[body_index]

            # Verify research content was removed
            assert "kiln:research" not in cleaned_body
            assert "Content here" not in cleaned_body
            # Verify original description is preserved
            assert original_description in cleaned_body

    def test_clear_kiln_content_legacy_plan_no_separator(self, reset_handler):
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

        reset_handler.ticket_client.get_ticket_body.return_value = body

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            reset_handler._clear_kiln_content(item)

            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            body_index = call_args.index("--body") + 1
            cleaned_body = call_args[body_index]

            # Verify plan content was removed
            assert "kiln:plan" not in cleaned_body
            assert "Plan steps here" not in cleaned_body
            # Verify original description is preserved
            assert original_description in cleaned_body

    def test_clear_kiln_content_new_style_markers_still_work(self, reset_handler):
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

        reset_handler.ticket_client.get_ticket_body.return_value = body

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            reset_handler._clear_kiln_content(item)

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
# ResetHandler Close PRs and Delete Branches Tests
# ============================================================================


class TestResetHandlerClosePrsAndDeleteBranches:
    """Tests for ResetHandler._close_prs_and_delete_branches() method."""

    @pytest.fixture
    def reset_handler(self, temp_workspace_dir):
        """Create a ResetHandler instance for testing."""
        ticket_client = MagicMock()
        workspace_manager = MagicMock()

        handler = ResetHandler(
            ticket_client=ticket_client,
            workspace_manager=workspace_manager,
            username_self="kiln-bot",
            team_usernames=[],
            workspace_dir=temp_workspace_dir,
        )
        yield handler

    def test_close_pr_and_delete_branch_for_open_pr(self, reset_handler):
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

        reset_handler.ticket_client.get_linked_prs.return_value = linked_prs
        reset_handler.ticket_client.close_pr.return_value = True
        reset_handler.ticket_client.delete_branch.return_value = True

        reset_handler._close_prs_and_delete_branches(item)

        reset_handler.ticket_client.get_linked_prs.assert_called_once_with("github.com/owner/repo", 42)
        reset_handler.ticket_client.close_pr.assert_called_once_with("github.com/owner/repo", 100)
        reset_handler.ticket_client.delete_branch.assert_called_once_with(
            "github.com/owner/repo", "42-feature-branch"
        )

    def test_skip_merged_pr(self, reset_handler):
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

        reset_handler.ticket_client.get_linked_prs.return_value = linked_prs

        reset_handler._close_prs_and_delete_branches(item)

        reset_handler.ticket_client.get_linked_prs.assert_called_once()
        reset_handler.ticket_client.close_pr.assert_not_called()
        reset_handler.ticket_client.delete_branch.assert_not_called()

    def test_continue_processing_on_close_failure(self, reset_handler):
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

        reset_handler.ticket_client.get_linked_prs.return_value = linked_prs
        reset_handler.ticket_client.close_pr.return_value = False  # Failure
        reset_handler.ticket_client.delete_branch.return_value = True

        reset_handler._close_prs_and_delete_branches(item)

        # Both methods should be called even if close_pr fails
        reset_handler.ticket_client.close_pr.assert_called_once()
        reset_handler.ticket_client.delete_branch.assert_called_once()

    def test_multiple_prs_processed(self, reset_handler):
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

        reset_handler.ticket_client.get_linked_prs.return_value = linked_prs
        reset_handler.ticket_client.close_pr.return_value = True
        reset_handler.ticket_client.delete_branch.return_value = True

        reset_handler._close_prs_and_delete_branches(item)

        assert reset_handler.ticket_client.close_pr.call_count == 2
        assert reset_handler.ticket_client.delete_branch.call_count == 2

    def test_no_linked_prs(self, reset_handler):
        """Test handling when there are no linked PRs."""
        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            title="Test Issue",
            repo="github.com/owner/repo",
            status="Implement",
        )

        reset_handler.ticket_client.get_linked_prs.return_value = []

        reset_handler._close_prs_and_delete_branches(item)

        reset_handler.ticket_client.get_linked_prs.assert_called_once()
        reset_handler.ticket_client.close_pr.assert_not_called()
        reset_handler.ticket_client.delete_branch.assert_not_called()

    def test_pr_without_branch_name(self, reset_handler):
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

        reset_handler.ticket_client.get_linked_prs.return_value = linked_prs
        reset_handler.ticket_client.close_pr.return_value = True

        reset_handler._close_prs_and_delete_branches(item)

        reset_handler.ticket_client.close_pr.assert_called_once()
        reset_handler.ticket_client.delete_branch.assert_not_called()

    def test_get_linked_prs_failure(self, reset_handler):
        """Test handling when get_linked_prs raises an exception."""
        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            title="Test Issue",
            repo="github.com/owner/repo",
            status="Implement",
        )

        reset_handler.ticket_client.get_linked_prs.side_effect = Exception("API error")

        # Should not raise, just log warning and return
        reset_handler._close_prs_and_delete_branches(item)

        reset_handler.ticket_client.close_pr.assert_not_called()
        reset_handler.ticket_client.delete_branch.assert_not_called()

    def test_mixed_merged_and_open_prs(self, reset_handler):
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

        reset_handler.ticket_client.get_linked_prs.return_value = linked_prs
        reset_handler.ticket_client.close_pr.return_value = True
        reset_handler.ticket_client.delete_branch.return_value = True

        reset_handler._close_prs_and_delete_branches(item)

        # Only the open PR should be processed
        reset_handler.ticket_client.close_pr.assert_called_once_with("github.com/owner/repo", 101)
        reset_handler.ticket_client.delete_branch.assert_called_once_with(
            "github.com/owner/repo", "42-open-branch"
        )

    def test_pr_closure_validation_success(self, reset_handler):
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

        reset_handler.ticket_client.get_linked_prs.return_value = linked_prs
        reset_handler.ticket_client.close_pr.return_value = True
        reset_handler.ticket_client.get_pr_state.return_value = "CLOSED"
        reset_handler.ticket_client.delete_branch.return_value = True

        reset_handler._close_prs_and_delete_branches(item)

        # Verify get_pr_state was called to validate closure
        reset_handler.ticket_client.get_pr_state.assert_called_once_with("github.com/owner/repo", 100)

    def test_pr_closure_validation_state_mismatch(self, reset_handler, caplog):
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

        reset_handler.ticket_client.get_linked_prs.return_value = linked_prs
        reset_handler.ticket_client.close_pr.return_value = True
        # State check returns OPEN despite close returning True
        reset_handler.ticket_client.get_pr_state.return_value = "OPEN"
        reset_handler.ticket_client.delete_branch.return_value = True

        with caplog.at_level(logging.WARNING):
            reset_handler._close_prs_and_delete_branches(item)

        # Should continue to delete branch even if state mismatch
        reset_handler.ticket_client.delete_branch.assert_called_once()
        # Warning should be logged about state mismatch
        assert any("state is OPEN" in record.message for record in caplog.records)

    def test_pr_closure_validation_returns_none(self, reset_handler, caplog):
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

        reset_handler.ticket_client.get_linked_prs.return_value = linked_prs
        reset_handler.ticket_client.close_pr.return_value = True
        reset_handler.ticket_client.get_pr_state.return_value = None  # Failed to get state
        reset_handler.ticket_client.delete_branch.return_value = True

        with caplog.at_level(logging.WARNING):
            reset_handler._close_prs_and_delete_branches(item)

        # Should continue to delete branch
        reset_handler.ticket_client.delete_branch.assert_called_once()
        # Warning should be logged about not being able to verify state
        assert any("Could not verify" in record.message for record in caplog.records)

    def test_close_pr_failure_logged(self, reset_handler, caplog):
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

        reset_handler.ticket_client.get_linked_prs.return_value = linked_prs
        reset_handler.ticket_client.close_pr.return_value = False  # Close failed
        reset_handler.ticket_client.delete_branch.return_value = True

        with caplog.at_level(logging.WARNING):
            reset_handler._close_prs_and_delete_branches(item)

        # Should still try to delete branch
        reset_handler.ticket_client.delete_branch.assert_called_once()
        # Warning should be logged about close failure
        assert any("Failed to close PR" in record.message for record in caplog.records)

    def test_close_pr_failure_skips_validation(self, reset_handler):
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

        reset_handler.ticket_client.get_linked_prs.return_value = linked_prs
        reset_handler.ticket_client.close_pr.return_value = False  # Close failed
        reset_handler.ticket_client.delete_branch.return_value = True

        reset_handler._close_prs_and_delete_branches(item)

        # get_pr_state should NOT be called if close_pr failed
        reset_handler.ticket_client.get_pr_state.assert_not_called()
