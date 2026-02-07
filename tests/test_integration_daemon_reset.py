"""Integration tests for Daemon reset/cleanup functionality.

Tests for clearing kiln content and closing PRs/deleting branches.
"""

import subprocess
from pathlib import Path
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

    def test_clear_kiln_content_research_with_details_wrapper(self, daemon):
        """Test clearing research block wrapped in <details> tags."""
        item = TicketItem(
            item_id="PVI_444",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=88,
            title="Test Issue with Details Wrapper",
            repo="github.com/owner/repo",
            status="Plan",
        )

        original_description = "Original issue description."
        research_with_details = """
---
<details>
<summary><h2>Research Findings</h2></summary>

<!-- kiln:research -->
## Research Findings

Some research content here.
<!-- /kiln:research -->

</details>"""
        body = original_description + research_with_details

        daemon.ticket_client.get_ticket_body.return_value = body

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            daemon._clear_kiln_content(item)

            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            body_index = call_args.index("--body") + 1
            cleaned_body = call_args[body_index]

            # Verify research content AND details wrapper were removed
            assert "kiln:research" not in cleaned_body
            assert "<details>" not in cleaned_body
            assert "</details>" not in cleaned_body
            assert "Research Findings" not in cleaned_body
            assert "<summary>" not in cleaned_body
            # Verify original description is preserved
            assert original_description in cleaned_body

    def test_clear_kiln_content_plan_with_details_wrapper(self, daemon):
        """Test clearing plan block wrapped in <details> tags."""
        item = TicketItem(
            item_id="PVI_555",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=99,
            title="Test Issue with Plan Details Wrapper",
            repo="github.com/owner/repo",
            status="Implement",
        )

        original_description = "My original description."
        plan_with_details = """
---
<details>
<summary><h2>Implementation Plan</h2></summary>

<!-- kiln:plan -->
# Implementation Plan

Step 1: Do this
Step 2: Do that
<!-- /kiln:plan -->

</details>"""
        body = original_description + plan_with_details

        daemon.ticket_client.get_ticket_body.return_value = body

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            daemon._clear_kiln_content(item)

            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            body_index = call_args.index("--body") + 1
            cleaned_body = call_args[body_index]

            # Verify plan content AND details wrapper were removed
            assert "kiln:plan" not in cleaned_body
            assert "<details>" not in cleaned_body
            assert "</details>" not in cleaned_body
            assert "Implementation Plan" not in cleaned_body
            assert "<summary>" not in cleaned_body
            # Verify original description is preserved
            assert original_description in cleaned_body

    def test_clear_kiln_content_both_with_details_wrappers(self, daemon):
        """Test clearing both research and plan blocks wrapped in <details> tags."""
        item = TicketItem(
            item_id="PVI_666",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=111,
            title="Test Issue with Both Details Wrappers",
            repo="github.com/owner/repo",
            status="Implement",
        )

        original_description = "The original user description."
        research_with_details = """
---
<details>
<summary><h2>Research Findings</h2></summary>

<!-- kiln:research -->
## Research Findings

Research content goes here.
<!-- /kiln:research -->

</details>"""
        plan_with_details = """
---
<details>
<summary><h2>Implementation Plan</h2></summary>

<!-- kiln:plan -->
# Implementation Plan

Plan content goes here.
<!-- /kiln:plan -->

</details>"""
        body = original_description + research_with_details + plan_with_details

        daemon.ticket_client.get_ticket_body.return_value = body

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            daemon._clear_kiln_content(item)

            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            body_index = call_args.index("--body") + 1
            cleaned_body = call_args[body_index]

            # Verify both sections AND their details wrappers were removed
            assert "kiln:research" not in cleaned_body
            assert "kiln:plan" not in cleaned_body
            assert "<details>" not in cleaned_body
            assert "</details>" not in cleaned_body
            assert "Research Findings" not in cleaned_body
            assert "Implementation Plan" not in cleaned_body
            assert "Research content" not in cleaned_body
            assert "Plan content" not in cleaned_body
            # Verify original description is preserved
            assert original_description in cleaned_body

    def test_clear_kiln_content_mixed_wrappers(self, daemon):
        """Test clearing mixed: research collapsed in details, plan without details."""
        item = TicketItem(
            item_id="PVI_777",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=222,
            title="Test Issue with Mixed Wrappers",
            repo="github.com/owner/repo",
            status="Implement",
        )

        original_description = "User's original issue description."
        # Research is collapsed in details (after plan workflow ran)
        research_with_details = """
---
<details>
<summary><h2>Research Findings</h2></summary>

<!-- kiln:research -->
## Research Findings

Research has been collapsed.
<!-- /kiln:research -->

</details>"""
        # Plan is NOT in details (before prepare_implementation)
        plan_without_details = """
---
<!-- kiln:plan -->
# Implementation Plan

Plan is not yet collapsed.
<!-- /kiln:plan -->"""
        body = original_description + research_with_details + plan_without_details

        daemon.ticket_client.get_ticket_body.return_value = body

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            daemon._clear_kiln_content(item)

            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            body_index = call_args.index("--body") + 1
            cleaned_body = call_args[body_index]

            # Verify research with details wrapper was removed
            assert "kiln:research" not in cleaned_body
            assert "Research Findings" not in cleaned_body
            assert "Research has been collapsed" not in cleaned_body
            # Verify plan without details wrapper was removed
            assert "kiln:plan" not in cleaned_body
            assert "Implementation Plan" not in cleaned_body
            assert "Plan is not yet collapsed" not in cleaned_body
            # Verify no leftover details tags
            assert "<details>" not in cleaned_body
            assert "</details>" not in cleaned_body
            # Verify original description is preserved
            assert original_description in cleaned_body

    def test_clear_kiln_content_research_details_with_legacy_marker(self, daemon):
        """Test clearing research in details with legacy <!-- /kiln --> end marker."""
        item = TicketItem(
            item_id="PVI_888",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=333,
            title="Test Issue with Legacy Marker in Details",
            repo="github.com/owner/repo",
            status="Plan",
        )

        original_description = "Original description text."
        research_details_legacy = """
---
<details>
<summary><h2>Research Findings</h2></summary>

<!-- kiln:research -->
## Research

Legacy marker research content.
<!-- /kiln -->

</details>"""
        body = original_description + research_details_legacy

        daemon.ticket_client.get_ticket_body.return_value = body

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            daemon._clear_kiln_content(item)

            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            body_index = call_args.index("--body") + 1
            cleaned_body = call_args[body_index]

            # Verify content AND details wrapper were removed
            assert "kiln:research" not in cleaned_body
            assert "<!-- /kiln -->" not in cleaned_body
            assert "<details>" not in cleaned_body
            assert "</details>" not in cleaned_body
            assert "Legacy marker research" not in cleaned_body
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


# ============================================================================
# Integration Tests for Reset with Running Workflow
# ============================================================================


@pytest.mark.integration
class TestResetWithRunningWorkflow:
    """Integration tests for reset behavior when workflow is running.

    These tests verify the end-to-end reset behavior:
    - Running subprocess is terminated when reset label is applied
    - Local branch is deleted after worktree cleanup
    - Other concurrent workflows remain unaffected
    """

    @pytest.fixture
    def daemon(self, temp_workspace_dir):
        """Create a daemon instance for testing with process tracking."""
        config = MagicMock()
        config.poll_interval = 60
        config.watched_statuses = ["Research", "Plan", "Implement"]
        config.max_concurrent_workflows = 2
        config.database_path = f"{temp_workspace_dir}/test.db"
        config.workspace_dir = temp_workspace_dir
        config.project_urls = ["https://github.com/orgs/test/projects/1"]

        config.github_enterprise_version = None
        config.team_usernames = []
        config.username_self = "kiln-bot"

        with patch("src.ticket_clients.github.GitHubTicketClient"):
            daemon = Daemon(config)
            daemon.ticket_client = MagicMock()
            daemon.workspace_manager = MagicMock()
            daemon.comment_processor.ticket_client = daemon.ticket_client
            yield daemon
            daemon.stop()

    @pytest.fixture
    def mock_running_process(self):
        """Create a mock subprocess that appears to be running."""
        process = MagicMock(spec=subprocess.Popen)
        process.pid = 12345
        process.poll.return_value = None  # Still running
        return process

    @pytest.fixture
    def mock_running_process_2(self):
        """Create a second mock subprocess for concurrent workflow testing."""
        process = MagicMock(spec=subprocess.Popen)
        process.pid = 54321
        process.poll.return_value = None  # Still running
        return process

    def test_reset_terminates_running_subprocess(self, daemon, mock_running_process):
        """Test that applying reset label terminates the running Claude subprocess."""
        item = TicketItem(
            item_id="PVI_100",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=100,
            title="Test Issue with Running Workflow",
            repo="github.com/owner/repo",
            status="Research",
            labels=["reset"],
        )

        key = f"{item.repo}#{item.ticket_id}"

        # Register a running process for this issue
        daemon.register_process(key, mock_running_process)

        # Verify process is registered
        assert key in daemon._running_processes
        assert daemon._running_processes[key] is mock_running_process

        # Setup mocks for reset handler
        daemon.ticket_client.get_label_actor.return_value = "kiln-bot"
        daemon.ticket_client.get_linked_prs.return_value = []
        daemon.ticket_client.get_ticket_body.return_value = "Issue body"

        # Ensure worktree doesn't exist
        worktree_path = Path(daemon.config.workspace_dir) / "repo-issue-100"
        assert not worktree_path.exists()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            daemon._maybe_handle_reset(item)

        # Verify process was killed
        mock_running_process.kill.assert_called_once()
        mock_running_process.wait.assert_called_once_with(timeout=5)

        # Verify process is no longer registered
        assert key not in daemon._running_processes

    def test_reset_deletes_local_branch_after_worktree_cleanup(self, daemon, temp_workspace_dir):
        """Test that reset cleans up worktree and deletes the local branch."""
        item = TicketItem(
            item_id="PVI_101",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=101,
            title="Test Issue for Branch Deletion",
            repo="github.com/owner/repo",
            status="Implement",
            labels=["reset"],
        )

        # Setup mocks
        daemon.ticket_client.get_label_actor.return_value = "kiln-bot"
        daemon.ticket_client.get_linked_prs.return_value = []
        daemon.ticket_client.get_ticket_body.return_value = "Issue body"

        # Create fake worktree directory
        worktree_path = Path(temp_workspace_dir) / "repo-issue-101"
        worktree_path.mkdir()
        (worktree_path / "test_file.txt").write_text("test content")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            daemon._maybe_handle_reset(item)

        # Verify cleanup_workspace was called
        daemon.workspace_manager.cleanup_workspace.assert_called_once_with("repo", 101)

    def test_reset_does_not_affect_other_concurrent_workflows(
        self, daemon, mock_running_process, mock_running_process_2
    ):
        """Test that resetting one issue does not affect other running workflows."""
        item_to_reset = TicketItem(
            item_id="PVI_102",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=102,
            title="Issue to Reset",
            repo="github.com/owner/repo",
            status="Research",
            labels=["reset"],
        )

        key_to_reset = f"{item_to_reset.repo}#{item_to_reset.ticket_id}"
        key_other = f"{item_to_reset.repo}#103"

        # Register processes for both issues
        daemon.register_process(key_to_reset, mock_running_process)
        daemon.register_process(key_other, mock_running_process_2)

        # Verify both processes are registered
        assert key_to_reset in daemon._running_processes
        assert key_other in daemon._running_processes

        # Setup mocks for reset handler
        daemon.ticket_client.get_label_actor.return_value = "kiln-bot"
        daemon.ticket_client.get_linked_prs.return_value = []
        daemon.ticket_client.get_ticket_body.return_value = "Issue body"

        # Ensure worktree doesn't exist
        worktree_path = Path(daemon.config.workspace_dir) / "repo-issue-102"
        assert not worktree_path.exists()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            daemon._maybe_handle_reset(item_to_reset)

        # Verify only the reset issue's process was killed
        mock_running_process.kill.assert_called_once()
        mock_running_process_2.kill.assert_not_called()

        # Verify the other process is still registered
        assert key_to_reset not in daemon._running_processes
        assert key_other in daemon._running_processes
        assert daemon._running_processes[key_other] is mock_running_process_2

    def test_reset_handles_already_dead_process_gracefully(self, daemon, mock_running_process):
        """Test that reset handles already-terminated processes gracefully."""
        item = TicketItem(
            item_id="PVI_104",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=104,
            title="Issue with Dead Process",
            repo="github.com/owner/repo",
            status="Research",
            labels=["reset"],
        )

        key = f"{item.repo}#{item.ticket_id}"

        # Process is already dead when kill is called
        mock_running_process.kill.side_effect = ProcessLookupError("No such process")

        # Register the dead process
        daemon.register_process(key, mock_running_process)

        # Setup mocks
        daemon.ticket_client.get_label_actor.return_value = "kiln-bot"
        daemon.ticket_client.get_linked_prs.return_value = []
        daemon.ticket_client.get_ticket_body.return_value = "Issue body"

        # Ensure worktree doesn't exist
        worktree_path = Path(daemon.config.workspace_dir) / "repo-issue-104"
        assert not worktree_path.exists()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            # Should not raise - handles dead process gracefully
            daemon._maybe_handle_reset(item)

        # Verify process was attempted to be killed
        mock_running_process.kill.assert_called_once()

        # Verify process is no longer registered
        assert key not in daemon._running_processes

    def test_reset_continues_when_no_running_process(self, daemon):
        """Test that reset completes successfully when no process is running."""
        item = TicketItem(
            item_id="PVI_105",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=105,
            title="Issue Without Running Process",
            repo="github.com/owner/repo",
            status="Research",
            labels=["reset"],
        )

        key = f"{item.repo}#{item.ticket_id}"

        # No process registered for this issue
        assert key not in daemon._running_processes

        # Setup mocks
        daemon.ticket_client.get_label_actor.return_value = "kiln-bot"
        daemon.ticket_client.get_linked_prs.return_value = []
        daemon.ticket_client.get_ticket_body.return_value = "Issue body"

        # Ensure worktree doesn't exist
        worktree_path = Path(daemon.config.workspace_dir) / "repo-issue-105"
        assert not worktree_path.exists()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            # Should complete without error
            daemon._maybe_handle_reset(item)

        # Verify reset label was removed (indicating reset proceeded)
        daemon.ticket_client.remove_label.assert_called()

    def test_reset_kills_process_before_worktree_cleanup(self, daemon, mock_running_process):
        """Test that process is killed BEFORE worktree cleanup to avoid race conditions."""
        item = TicketItem(
            item_id="PVI_106",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=106,
            title="Issue for Order Verification",
            repo="github.com/owner/repo",
            status="Research",
            labels=["reset"],
        )

        key = f"{item.repo}#{item.ticket_id}"

        # Register process
        daemon.register_process(key, mock_running_process)

        # Setup mocks
        daemon.ticket_client.get_label_actor.return_value = "kiln-bot"
        daemon.ticket_client.get_linked_prs.return_value = []
        daemon.ticket_client.get_ticket_body.return_value = "Issue body"

        # Create fake worktree so cleanup is called
        worktree_path = Path(daemon.config.workspace_dir) / "repo-issue-106"
        worktree_path.mkdir()

        # Track order of operations
        operation_order = []

        original_kill = daemon.kill_process

        def track_kill(k):
            operation_order.append(("kill_process", k))
            return original_kill(k)

        def track_cleanup(repo_name, issue_number):
            operation_order.append(("cleanup_workspace", repo_name, issue_number))

        with (
            patch.object(daemon, "kill_process", side_effect=track_kill),
            patch.object(daemon.workspace_manager, "cleanup_workspace", side_effect=track_cleanup),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0)
            daemon._maybe_handle_reset(item)

        # Verify kill_process was called before cleanup_workspace
        kill_indices = [i for i, op in enumerate(operation_order) if op[0] == "kill_process"]
        cleanup_indices = [i for i, op in enumerate(operation_order) if op[0] == "cleanup_workspace"]

        assert len(kill_indices) == 1, "kill_process should be called exactly once"
        assert len(cleanup_indices) == 1, "cleanup_workspace should be called exactly once"
        assert kill_indices[0] < cleanup_indices[0], "kill_process should be called before cleanup_workspace"

    def test_reset_with_multiple_concurrent_issues_isolation(
        self, daemon, mock_running_process, mock_running_process_2
    ):
        """Test complete isolation when multiple issues are running concurrently."""
        # Two different issues in different repos
        item1 = TicketItem(
            item_id="PVI_107",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=107,
            title="Issue 1 to Reset",
            repo="github.com/owner/repo1",
            status="Research",
            labels=["reset"],
        )

        item2 = TicketItem(
            item_id="PVI_108",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=108,
            title="Issue 2 Running",
            repo="github.com/owner/repo2",
            status="Plan",
            labels=[],  # No reset label
        )

        key1 = f"{item1.repo}#{item1.ticket_id}"
        key2 = f"{item2.repo}#{item2.ticket_id}"

        # Register processes for both issues
        daemon.register_process(key1, mock_running_process)
        daemon.register_process(key2, mock_running_process_2)

        # Setup mocks
        daemon.ticket_client.get_label_actor.return_value = "kiln-bot"
        daemon.ticket_client.get_linked_prs.return_value = []
        daemon.ticket_client.get_ticket_body.return_value = "Issue body"

        # Only reset item1
        worktree_path = Path(daemon.config.workspace_dir) / "repo1-issue-107"
        assert not worktree_path.exists()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            daemon._maybe_handle_reset(item1)

        # item1's process should be killed
        mock_running_process.kill.assert_called_once()
        assert key1 not in daemon._running_processes

        # item2's process should be completely untouched
        mock_running_process_2.kill.assert_not_called()
        mock_running_process_2.wait.assert_not_called()
        assert key2 in daemon._running_processes
        assert daemon._running_processes[key2] is mock_running_process_2
