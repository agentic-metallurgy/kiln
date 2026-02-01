"""Integration tests for Daemon comment processing.

Tests for CommentProcessor methods including:
- _is_kiln_response() helper
- _generate_diff() helper
- Response comment posting
- _is_kiln_post() helper
- _initialize_comment_timestamp() method
- process() method
"""

import tempfile
from datetime import UTC
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from src.daemon import Daemon
from src.interfaces import Comment, TicketItem
from src.labels import Labels


# ============================================================================
# Daemon Comment Processing Tests
# ============================================================================


@pytest.mark.integration
class TestDaemonResponseComments:
    """Tests for response comment posting in CommentProcessor.process()."""

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
        config.username_self = "real-user"
        config.github_enterprise_version = None

        with patch("src.ticket_clients.github.GitHubTicketClient"):
            daemon = Daemon(config)
            daemon.ticket_client = MagicMock()
            daemon.comment_processor.ticket_client = daemon.ticket_client
            yield daemon
            daemon.stop()

    def test_process_comments_posts_response_with_diff(self, daemon):
        """Test that a response comment with diff is posted after processing."""
        from datetime import datetime

        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
        )

        daemon.database.update_issue_state(
            "owner/repo",
            42,
            "Research",
            last_processed_comment_timestamp="2024-01-15T10:00:00+00:00",
        )

        user_comment = Comment(
            id="IC_1",
            database_id=100,
            body="Please expand on option A",
            created_at=datetime(2024, 1, 15, 11, 0, 0, tzinfo=UTC),
            author="real-user",
            is_processed=False,
        )

        # Mock the response comment that will be created
        response_comment = Comment(
            id="IC_response",
            database_id=200,
            body="<!-- kiln:response -->\nApplied changes",
            created_at=datetime(2024, 1, 15, 11, 5, 0, tzinfo=UTC),
            author="kiln-bot",
            is_processed=False,
        )

        daemon.ticket_client.get_comments_since.return_value = [user_comment]
        daemon.ticket_client.add_comment.return_value = response_comment

        # Mock section extraction (before and after)
        with (
            patch.object(daemon.comment_processor, "_extract_section_content") as mock_extract,
            patch.object(daemon.comment_processor, "_ensure_worktree_exists", return_value="/tmp/worktree"),
            patch.object(daemon.runner, "run"),
        ):
            mock_extract.side_effect = ["Before content", "After content"]
            daemon.comment_processor.process(item)

            # Verify response comment was posted
            daemon.ticket_client.add_comment.assert_called_once()
            call_args = daemon.ticket_client.add_comment.call_args
            assert call_args[0][0] == "owner/repo"
            assert call_args[0][1] == 42
            # Check that response contains marker and diff
            response_body = call_args[0][2]
            assert "<!-- kiln:response -->" in response_body
            assert '<pre lang="diff">' in response_body

    def test_process_comments_response_contains_diff_marker(self, daemon):
        """Test that response comment body contains the kiln:response marker."""
        from datetime import datetime

        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Plan",
            title="Test Issue",
        )

        daemon.database.update_issue_state(
            "owner/repo", 42, "Plan", last_processed_comment_timestamp="2024-01-15T10:00:00+00:00"
        )

        user_comment = Comment(
            id="IC_1",
            database_id=100,
            body="Update the plan",
            created_at=datetime(2024, 1, 15, 11, 0, 0, tzinfo=UTC),
            author="real-user",
            is_processed=False,
        )

        response_comment = Comment(
            id="IC_response",
            database_id=200,
            body="<!-- kiln:response -->\nApplied changes",
            created_at=datetime(2024, 1, 15, 11, 5, 0, tzinfo=UTC),
            author="kiln-bot",
            is_processed=False,
        )

        daemon.ticket_client.get_comments_since.return_value = [user_comment]
        daemon.ticket_client.add_comment.return_value = response_comment

        with (
            patch.object(daemon.comment_processor, "_extract_section_content") as mock_extract,
            patch.object(daemon.comment_processor, "_ensure_worktree_exists", return_value="/tmp/worktree"),
            patch.object(daemon.runner, "run"),
        ):
            mock_extract.side_effect = ["Old plan", "Updated plan"]
            daemon.comment_processor.process(item)

            response_body = daemon.ticket_client.add_comment.call_args[0][2]
            assert response_body.lstrip().startswith("<!-- kiln:response -->")

    def test_process_comments_diff_escapes_html(self, daemon):
        """Test that HTML in diff content is escaped to prevent breaking the details block."""
        from datetime import datetime

        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Plan",
            title="Test Issue",
        )

        daemon.database.update_issue_state(
            "owner/repo", 42, "Plan", last_processed_comment_timestamp="2024-01-15T10:00:00+00:00"
        )

        user_comment = Comment(
            id="IC_1",
            database_id=100,
            body="Update the plan",
            created_at=datetime(2024, 1, 15, 11, 0, 0, tzinfo=UTC),
            author="real-user",
            is_processed=False,
        )

        response_comment = Comment(
            id="IC_response",
            database_id=200,
            body="<!-- kiln:response -->\nApplied changes",
            created_at=datetime(2024, 1, 15, 11, 5, 0, tzinfo=UTC),
            author="kiln-bot",
            is_processed=False,
        )

        daemon.ticket_client.get_comments_since.return_value = [user_comment]
        daemon.ticket_client.add_comment.return_value = response_comment

        with (
            patch.object(daemon.comment_processor, "_extract_section_content") as mock_extract,
            patch.object(daemon.comment_processor, "_ensure_worktree_exists", return_value="/tmp/worktree"),
            patch.object(daemon.runner, "run"),
        ):
            # Simulate a diff where the content contains HTML that could break the details block
            before_content = "Old content\n\n</details>\n\n---\n\n<details open>"
            after_content = "New content\n\n</details>\n\n---\n\n<details open>\nMore stuff"
            mock_extract.side_effect = [before_content, after_content]
            daemon.comment_processor.process(item)

            response_body = daemon.ticket_client.add_comment.call_args[0][2]
            # The HTML should be escaped so it doesn't break the outer <details> block
            assert "&lt;/details&gt;" in response_body
            assert "&lt;details open&gt;" in response_body
            # The raw HTML should NOT appear (would break formatting)
            assert "</details>\n\n---" not in response_body

    def test_process_comments_timestamp_updated_to_response(self, daemon):
        """Test that timestamp is updated to the response comment's timestamp."""
        from datetime import datetime

        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
        )

        daemon.database.update_issue_state(
            "owner/repo",
            42,
            "Research",
            last_processed_comment_timestamp="2024-01-15T10:00:00+00:00",
        )

        user_comment = Comment(
            id="IC_1",
            database_id=100,
            body="Feedback",
            created_at=datetime(2024, 1, 15, 11, 0, 0, tzinfo=UTC),
            author="real-user",
            is_processed=False,
        )

        # Response is created AFTER user comment
        response_comment = Comment(
            id="IC_response",
            database_id=300,
            body="<!-- kiln:response -->\nApplied changes",
            created_at=datetime(2024, 1, 15, 11, 30, 0, tzinfo=UTC),
            author="kiln-bot",
            is_processed=False,
        )

        daemon.ticket_client.get_comments_since.return_value = [user_comment]
        daemon.ticket_client.add_comment.return_value = response_comment

        with (
            patch.object(daemon.comment_processor, "_extract_section_content") as mock_extract,
            patch.object(daemon.comment_processor, "_ensure_worktree_exists", return_value="/tmp/worktree"),
            patch.object(daemon.runner, "run"),
        ):
            mock_extract.side_effect = ["Before", "After"]
            daemon.comment_processor.process(item)

        # Verify timestamp is set to response comment's timestamp (not user comment's)
        state = daemon.database.get_issue_state("owner/repo", 42)
        assert state.last_processed_comment_timestamp == "2024-01-15T11:30:00+00:00"

    def test_response_comments_are_filtered_out(self, daemon):
        """Test that kiln response comments are not processed as user feedback."""
        from datetime import datetime

        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
        )

        daemon.database.update_issue_state(
            "owner/repo",
            42,
            "Research",
            last_processed_comment_timestamp="2024-01-15T10:00:00+00:00",
        )

        # Only a kiln response comment - should be filtered out
        response_comment = Comment(
            id="IC_1",
            database_id=100,
            body="<!-- kiln:response -->\nApplied changes to **research**:\n```diff\n+new\n```",
            created_at=datetime(2024, 1, 15, 11, 0, 0, tzinfo=UTC),
            author="real-user",  # Even from a non-bot user
            is_processed=False,
        )

        daemon.ticket_client.get_comments_since.return_value = [response_comment]

        with (
            patch.object(daemon.comment_processor, "_ensure_worktree_exists", return_value="/tmp/worktree"),
            patch.object(daemon.runner, "run") as mock_run,
        ):
            daemon.comment_processor.process(item)

            # Workflow should NOT be run (response comment filtered out)
            mock_run.assert_not_called()

    def test_process_comments_no_diff_message(self, daemon):
        """Test that message is posted when no textual changes are detected."""
        from datetime import datetime

        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Plan",
            title="Test Issue",
        )

        daemon.database.update_issue_state(
            "owner/repo", 42, "Plan", last_processed_comment_timestamp="2024-01-15T10:00:00+00:00"
        )

        user_comment = Comment(
            id="IC_1",
            database_id=100,
            body="Make a small formatting change",
            created_at=datetime(2024, 1, 15, 11, 0, 0, tzinfo=UTC),
            author="real-user",
            is_processed=False,
        )

        response_comment = Comment(
            id="IC_response",
            database_id=200,
            body="<!-- kiln:response -->\nNo changes",
            created_at=datetime(2024, 1, 15, 11, 5, 0, tzinfo=UTC),
            author="kiln-bot",
            is_processed=False,
        )

        daemon.ticket_client.get_comments_since.return_value = [user_comment]
        daemon.ticket_client.add_comment.return_value = response_comment

        # Same content before and after (no diff)
        with (
            patch.object(daemon.comment_processor, "_extract_section_content") as mock_extract,
            patch.object(daemon.comment_processor, "_ensure_worktree_exists", return_value="/tmp/worktree"),
            patch.object(daemon.runner, "run"),
        ):
            mock_extract.side_effect = ["Same content", "Same content"]
            daemon.comment_processor.process(item)

            response_body = daemon.ticket_client.add_comment.call_args[0][2]
            assert "<!-- kiln:response -->" in response_body
            assert "No textual changes detected" in response_body


@pytest.mark.integration
class TestDaemonInitializeCommentTimestamp:
    """Tests for CommentProcessor._initialize_comment_timestamp() method."""

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
            daemon.comment_processor.ticket_client = daemon.ticket_client
            yield daemon
            daemon.stop()

    def test_initialize_finds_kiln_post_timestamp(self, daemon):
        """Test that kiln post timestamp is returned."""
        from datetime import datetime

        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
        )

        comments = [
            Comment(
                id="IC_1",
                database_id=100,
                body="User question",
                created_at=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
                author="user1",
                is_processed=False,
            ),
            Comment(
                id="IC_2",
                database_id=200,
                body="<!-- kiln:research -->\n## Research\nFindings here<!-- /kiln -->",
                created_at=datetime(2024, 1, 15, 11, 0, 0, tzinfo=UTC),
                author="kiln-bot",
                is_processed=False,
            ),
        ]

        result = daemon.comment_processor._initialize_comment_timestamp(item, comments)
        assert result == "2024-01-15T11:00:00+00:00"

    def test_initialize_finds_thumbs_up_comment_timestamp(self, daemon):
        """Test that already-processed (thumbs up) comment timestamp is returned."""
        from datetime import datetime

        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
        )

        comments = [
            Comment(
                id="IC_1",
                database_id=100,
                body="Old feedback",
                created_at=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
                author="user1",
                is_processed=True,  # Already processed
            ),
            Comment(
                id="IC_2",
                database_id=200,
                body="New feedback",
                created_at=datetime(2024, 1, 15, 11, 0, 0, tzinfo=UTC),
                author="user2",
                is_processed=False,  # Not yet processed
            ),
        ]

        # Should return the thumbs-up comment (newest processed)
        result = daemon.comment_processor._initialize_comment_timestamp(item, comments)
        assert result == "2024-01-15T10:00:00+00:00"

    def test_initialize_prefers_newest_processed_comment(self, daemon):
        """Test that the newest kiln/thumbs-up comment is selected."""
        from datetime import datetime

        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Plan",
            title="Test Issue",
        )

        comments = [
            Comment(
                id="IC_1",
                database_id=100,
                body="<!-- kiln:research -->\nResearch<!-- /kiln -->",
                created_at=datetime(2024, 1, 15, 9, 0, 0, tzinfo=UTC),
                author="kiln-bot",
                is_processed=False,
            ),
            Comment(
                id="IC_2",
                database_id=200,
                body="Processed feedback",
                created_at=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
                author="user1",
                is_processed=True,
            ),
            Comment(
                id="IC_3",
                database_id=300,
                body="<!-- kiln:plan -->\nPlan<!-- /kiln -->",
                created_at=datetime(2024, 1, 15, 11, 0, 0, tzinfo=UTC),
                author="kiln-bot",
                is_processed=False,
            ),
        ]

        # Should return the newest kiln post (plan)
        result = daemon.comment_processor._initialize_comment_timestamp(item, comments)
        assert result == "2024-01-15T11:00:00+00:00"

    def test_initialize_returns_none_when_no_processed_comments(self, daemon):
        """Test that None is returned when no kiln posts or thumbs-up comments exist."""
        from datetime import datetime

        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
        )

        comments = [
            Comment(
                id="IC_1",
                database_id=100,
                body="Just a regular comment",
                created_at=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
                author="user1",
                is_processed=False,
            ),
        ]

        result = daemon.comment_processor._initialize_comment_timestamp(item, comments)
        assert result is None


@pytest.mark.integration
class TestDaemonProcessCommentsForItem:
    """Tests for CommentProcessor.process() method."""

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
        config.username_self = "real-user"
        config.github_enterprise_version = None

        with patch("src.ticket_clients.github.GitHubTicketClient"):
            daemon = Daemon(config)
            daemon.ticket_client = MagicMock()
            daemon.comment_processor.ticket_client = daemon.ticket_client
            yield daemon
            daemon.stop()

    def test_process_comments_skips_bot_comments(self, daemon):
        """Test that bot comments are filtered out."""
        from datetime import datetime

        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
        )

        # Set up stored state with a timestamp
        daemon.database.update_issue_state(
            "owner/repo",
            42,
            "Research",
            last_processed_comment_timestamp="2024-01-15T10:00:00+00:00",
        )

        # Bot comments should be filtered
        bot_comments = [
            Comment(
                id="IC_1",
                database_id=100,
                body="Automated message",
                created_at=datetime(2024, 1, 15, 11, 0, 0, tzinfo=UTC),
                author="github-actions[bot]",
                is_processed=False,
            ),
            Comment(
                id="IC_2",
                database_id=200,
                body="Kiln status update",
                created_at=datetime(2024, 1, 15, 11, 30, 0, tzinfo=UTC),
                author="kiln-bot",
                is_processed=False,
            ),
        ]

        daemon.ticket_client.get_comments_since.return_value = bot_comments
        daemon.ticket_client.find_kiln_comment.return_value = None

        # Should not call add_reaction (no user comments to process)
        daemon.comment_processor.process(item)
        daemon.ticket_client.add_reaction.assert_not_called()

    def test_process_comments_skips_kiln_posts(self, daemon):
        """Test that kiln-generated posts are filtered out."""
        from datetime import datetime

        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
        )

        daemon.database.update_issue_state(
            "owner/repo",
            42,
            "Research",
            last_processed_comment_timestamp="2024-01-15T10:00:00+00:00",
        )

        # Kiln posts should be filtered even if from a different author
        kiln_posts = [
            Comment(
                id="IC_1",
                database_id=100,
                body="<!-- kiln:research -->\n## Research\nFindings<!-- /kiln -->",
                created_at=datetime(2024, 1, 15, 11, 0, 0, tzinfo=UTC),
                author="some-user",  # Even non-bot author
                is_processed=False,
            ),
        ]

        daemon.ticket_client.get_comments_since.return_value = kiln_posts
        daemon.ticket_client.find_kiln_comment.return_value = None

        daemon.comment_processor.process(item)
        daemon.ticket_client.add_reaction.assert_not_called()

    def test_process_comments_processes_user_feedback(self, daemon):
        """Test that valid user comments trigger workflow and get thumbs up."""
        from datetime import datetime

        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
        )

        daemon.database.update_issue_state(
            "owner/repo",
            42,
            "Research",
            last_processed_comment_timestamp="2024-01-15T10:00:00+00:00",
        )

        user_comment = Comment(
            id="IC_1",
            database_id=100,
            body="Please add more detail about option A",
            created_at=datetime(2024, 1, 15, 11, 0, 0, tzinfo=UTC),
            author="real-user",
            is_processed=False,
        )

        daemon.ticket_client.get_comments_since.return_value = [user_comment]
        daemon.ticket_client.find_kiln_comment.return_value = None

        with (
            patch.object(daemon.comment_processor, "_ensure_worktree_exists", return_value="/tmp/worktree"),
            patch.object(daemon.runner, "run") as mock_run,
        ):
            daemon.comment_processor.process(item)

            # Should have run the workflow
            mock_run.assert_called_once()
            # Should have added eyes (processing) and thumbs up (done) reactions
            calls = daemon.ticket_client.add_reaction.call_args_list
            assert call("IC_1", "EYES", repo="owner/repo") in calls
            assert call("IC_1", "THUMBS_UP", repo="owner/repo") in calls

    def test_process_comments_updates_timestamp_after_processing(self, daemon):
        """Test that last_processed_comment_timestamp is updated to response comment's timestamp."""
        from datetime import datetime

        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
        )

        daemon.database.update_issue_state(
            "owner/repo",
            42,
            "Research",
            last_processed_comment_timestamp="2024-01-15T10:00:00+00:00",
        )

        user_comment = Comment(
            id="IC_1",
            database_id=100,
            body="User feedback",
            created_at=datetime(2024, 1, 15, 11, 30, 0, tzinfo=UTC),
            author="real-user",
            is_processed=False,
        )

        # Response comment is created after user comment
        response_comment = Comment(
            id="IC_response",
            database_id=200,
            body="<!-- kiln:response -->\nApplied changes",
            created_at=datetime(2024, 1, 15, 11, 35, 0, tzinfo=UTC),
            author="kiln-bot",
            is_processed=False,
        )

        daemon.ticket_client.get_comments_since.return_value = [user_comment]
        daemon.ticket_client.find_kiln_comment.return_value = None
        daemon.ticket_client.add_comment.return_value = response_comment

        with (
            patch.object(daemon.comment_processor, "_extract_section_content") as mock_extract,
            patch.object(daemon.comment_processor, "_ensure_worktree_exists", return_value="/tmp/worktree"),
            patch.object(daemon.runner, "run"),
        ):
            mock_extract.side_effect = ["Before", "After"]
            daemon.comment_processor.process(item)

        # Check that timestamp was updated to response comment's timestamp
        state = daemon.database.get_issue_state("owner/repo", 42)
        assert state.last_processed_comment_timestamp == "2024-01-15T11:35:00+00:00"

    def test_process_comments_skips_already_processed_thumbs_up(self, daemon):
        """Test that comments with thumbs-up reactions (already processed) are filtered out.

        This is critical: GitHub's 'since' API returns comments >= timestamp (inclusive),
        so we may get back comments we've already processed. The thumbs-up reaction
        serves as a marker that the comment was already handled.
        """
        from datetime import datetime

        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Plan",
            title="Test Issue",
        )

        daemon.database.update_issue_state(
            "owner/repo", 42, "Plan", last_processed_comment_timestamp="2024-01-15T10:00:00+00:00"
        )

        # Mix of already-processed (has thumbs up) and new comments
        # All comments must be from username_self ("real-user") to pass the filter
        comments = [
            Comment(
                id="IC_1",
                database_id=100,
                body="Old feedback already processed",
                created_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
                author="real-user",
                is_processed=True,  # Already processed!
            ),
            Comment(
                id="IC_2",
                database_id=200,
                body="Another old one",
                created_at=datetime(2024, 1, 15, 10, 45, 0, tzinfo=UTC),
                author="real-user",
                is_processed=True,  # Already processed!
            ),
            Comment(
                id="IC_3",
                database_id=300,
                body="New feedback to process",
                created_at=datetime(2024, 1, 15, 11, 0, 0, tzinfo=UTC),
                author="real-user",
                is_processed=False,  # NOT processed yet
            ),
        ]

        daemon.ticket_client.get_comments_since.return_value = comments
        daemon.ticket_client.find_kiln_comment.return_value = MagicMock(body="<!-- kiln:plan -->")

        with (
            patch.object(daemon.comment_processor, "_ensure_worktree_exists", return_value="/tmp/worktree"),
            patch.object(daemon.runner, "run") as mock_run,
        ):
            daemon.comment_processor.process(item)

            # Should only process the ONE comment without thumbs up
            mock_run.assert_called_once()
            # Should only react to the new comment (eyes then thumbs up)
            calls = daemon.ticket_client.add_reaction.call_args_list
            assert call("IC_3", "EYES", repo="owner/repo") in calls
            assert call("IC_3", "THUMBS_UP", repo="owner/repo") in calls
            # Should NOT have reacted to already-processed comments
            assert call("IC_1", "EYES") not in calls
            assert call("IC_2", "EYES") not in calls

    def test_process_comments_skips_all_when_all_have_thumbs_up(self, daemon):
        """Test that no processing happens when all comments already have thumbs-up."""
        from datetime import datetime

        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
        )

        daemon.database.update_issue_state(
            "owner/repo",
            42,
            "Research",
            last_processed_comment_timestamp="2024-01-15T10:00:00+00:00",
        )

        # All comments already processed
        comments = [
            Comment(
                id="IC_1",
                database_id=100,
                body="Old feedback",
                created_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
                author="user1",
                is_processed=True,
            ),
            Comment(
                id="IC_2",
                database_id=200,
                body="More old feedback",
                created_at=datetime(2024, 1, 15, 10, 45, 0, tzinfo=UTC),
                author="user2",
                is_processed=True,
            ),
        ]

        daemon.ticket_client.get_comments_since.return_value = comments

        with (
            patch.object(daemon.comment_processor, "_ensure_worktree_exists", return_value="/tmp/worktree"),
            patch.object(daemon.runner, "run") as mock_run,
        ):
            daemon.comment_processor.process(item)

            # Should NOT run any workflow
            mock_run.assert_not_called()
            # Should NOT add any reactions
            daemon.ticket_client.add_reaction.assert_not_called()

    def test_process_comments_skips_comments_with_eyes_reaction(self, daemon):
        """Test that comments with eyes reaction (being processed by another thread) are filtered out.

        The eyes reaction indicates another daemon thread has already picked up the comment
        and is currently processing it. This prevents duplicate processing.
        """
        from datetime import datetime

        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
        )

        daemon.database.update_issue_state(
            "owner/repo",
            42,
            "Research",
            last_processed_comment_timestamp="2024-01-15T10:00:00+00:00",
        )

        # Mix of comments being processed (has eyes) and new comments
        # All comments must be from username_self ("real-user") to pass the filter
        comments = [
            Comment(
                id="IC_1",
                database_id=100,
                body="Comment being processed by another thread",
                created_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
                author="real-user",
                is_processed=False,
                is_processing=True,  # Being processed by another thread!
            ),
            Comment(
                id="IC_2",
                database_id=200,
                body="New comment to process",
                created_at=datetime(2024, 1, 15, 11, 0, 0, tzinfo=UTC),
                author="real-user",
                is_processed=False,
                is_processing=False,  # Not yet picked up
            ),
        ]

        daemon.ticket_client.get_comments_since.return_value = comments
        daemon.ticket_client.find_kiln_comment.return_value = MagicMock(
            body="<!-- kiln:research -->"
        )

        with (
            patch.object(daemon.comment_processor, "_ensure_worktree_exists", return_value="/tmp/worktree"),
            patch.object(daemon.runner, "run") as mock_run,
        ):
            daemon.comment_processor.process(item)

            # Should run workflow once (only for the comment without eyes)
            mock_run.assert_called_once()
            # Should only react to the new comment (eyes then thumbs up)
            calls = daemon.ticket_client.add_reaction.call_args_list
            assert call("IC_2", "EYES", repo="owner/repo") in calls
            assert call("IC_2", "THUMBS_UP", repo="owner/repo") in calls
            # Should NOT have reacted to comment being processed by another thread
            assert call("IC_1", "EYES") not in calls
            assert call("IC_1", "THUMBS_UP") not in calls

    def test_process_comments_skips_all_when_all_have_eyes(self, daemon):
        """Test that no processing happens when all comments have eyes reaction."""
        from datetime import datetime

        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Plan",
            title="Test Issue",
        )

        daemon.database.update_issue_state(
            "owner/repo", 42, "Plan", last_processed_comment_timestamp="2024-01-15T10:00:00+00:00"
        )

        # All comments being processed by other threads
        comments = [
            Comment(
                id="IC_1",
                database_id=100,
                body="Being processed",
                created_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
                author="user1",
                is_processed=False,
                is_processing=True,
            ),
            Comment(
                id="IC_2",
                database_id=200,
                body="Also being processed",
                created_at=datetime(2024, 1, 15, 10, 45, 0, tzinfo=UTC),
                author="user2",
                is_processed=False,
                is_processing=True,
            ),
        ]

        daemon.ticket_client.get_comments_since.return_value = comments

        with (
            patch.object(daemon.comment_processor, "_ensure_worktree_exists", return_value="/tmp/worktree"),
            patch.object(daemon.runner, "run") as mock_run,
        ):
            daemon.comment_processor.process(item)

            # Should NOT run any workflow
            mock_run.assert_not_called()
            # Should NOT add any reactions
            daemon.ticket_client.add_reaction.assert_not_called()

    def test_process_comments_merges_multiple_comments(self, daemon):
        """Test that multiple comments are merged with later ones taking precedence."""
        from datetime import datetime

        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Plan",
            title="Test Issue",
        )

        daemon.database.update_issue_state(
            "owner/repo", 42, "Plan", last_processed_comment_timestamp="2024-01-15T10:00:00+00:00"
        )

        # Multiple comments to merge
        # All comments must be from username_self ("real-user") to pass the filter
        comments = [
            Comment(
                id="IC_1",
                database_id=100,
                body="Use approach A",
                created_at=datetime(2024, 1, 15, 11, 0, 0, tzinfo=UTC),
                author="real-user",
                is_processed=False,
            ),
            Comment(
                id="IC_2",
                database_id=200,
                body="Actually, use approach B instead",
                created_at=datetime(2024, 1, 15, 11, 30, 0, tzinfo=UTC),
                author="real-user",
                is_processed=False,
            ),
        ]

        daemon.ticket_client.get_comments_since.return_value = comments
        daemon.ticket_client.find_kiln_comment.return_value = MagicMock(body="<!-- kiln:plan -->")

        with (
            patch.object(daemon.comment_processor, "_ensure_worktree_exists", return_value="/tmp/worktree"),
            patch.object(daemon.runner, "run") as mock_run,
        ):
            daemon.comment_processor.process(item)

            # Should run workflow once with merged comments
            mock_run.assert_called_once()

            # Check the context passed to the workflow
            call_args = mock_run.call_args
            workflow = call_args[0][0]  # First positional arg
            context = call_args[0][1]  # Second positional arg

            # The merged body should contain both comments with guidance
            assert "Multiple user comments" in context.comment_body
            assert "prefer the LATER comments" in context.comment_body
            assert "Use approach A" in context.comment_body
            assert "Actually, use approach B instead" in context.comment_body
            assert "[Comment 1 of 2]" in context.comment_body
            assert "[Comment 2 of 2]" in context.comment_body

            # Should add eyes and thumbs up to ALL comments
            calls = daemon.ticket_client.add_reaction.call_args_list
            assert call("IC_1", "EYES", repo="owner/repo") in calls
            assert call("IC_2", "EYES", repo="owner/repo") in calls
            assert call("IC_1", "THUMBS_UP", repo="owner/repo") in calls
            assert call("IC_2", "THUMBS_UP", repo="owner/repo") in calls


@pytest.mark.integration
class TestDaemonBackoff:
    """Tests for daemon exponential backoff behavior using tenacity."""

    @pytest.fixture
    def mock_config(self, temp_workspace_dir):
        """Fixture providing mock Config object."""
        from src.config import Config

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        config = Config(
            github_token="test_token",
            project_urls=["https://github.com/orgs/test/projects/1"],
            workspace_dir=temp_workspace_dir,
            database_path=db_path,
            poll_interval=60,
            watched_statuses=["Research", "Plan", "Implement"],
        )

        yield config

        Path(db_path).unlink(missing_ok=True)

    @pytest.fixture
    def daemon(self, mock_config):
        """Fixture providing Daemon with mocked dependencies."""
        daemon = Daemon(mock_config)
        daemon.ticket_client = MagicMock()
        # Also update the ticket_client reference in comment_processor
        daemon.comment_processor.ticket_client = daemon.ticket_client
        yield daemon
        daemon.stop()

    def test_backoff_increases_on_consecutive_failures(self, daemon):
        """Test that backoff increases exponentially on failures using tenacity."""
        wait_timeouts = []

        # Mock Event.wait to track timeout values and return False (not interrupted)
        def mock_wait(timeout=None):
            wait_timeouts.append(timeout)
            return False  # Not interrupted

        # Fail twice then request shutdown on the second failure
        call_count = [0]

        def mock_poll():
            call_count[0] += 1
            if call_count[0] >= 2:
                daemon._shutdown_requested = True
            raise Exception("Simulated failure")

        with (
            patch.object(daemon, "_poll", side_effect=mock_poll),
            patch.object(daemon, "_initialize_project_metadata"),
            patch.object(daemon._shutdown_event, "wait", mock_wait),
        ):
            daemon.run()

        # First failure: 2^1 = 2 seconds backoff
        # Second failure: 2^2 = 4 seconds backoff (then shutdown detected on loop check)
        # Uses Event.wait with the full timeout (not 1-second loops)
        assert wait_timeouts == [2.0, 4.0]

    def test_backoff_resets_on_success(self, daemon):
        """Test that consecutive failure count resets after successful poll."""
        wait_timeouts = []

        def mock_wait(timeout=None):
            wait_timeouts.append(timeout)
            return False  # Not interrupted

        # Fail once, succeed, fail once, then shutdown on the third failure
        call_count = [0]

        def mock_poll():
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("First failure")
            elif call_count[0] == 2:
                pass  # Success
            elif call_count[0] == 3:
                daemon._shutdown_requested = True
                raise Exception("Third call failure triggers shutdown")

        with (
            patch.object(daemon, "_poll", side_effect=mock_poll),
            patch.object(daemon, "_initialize_project_metadata"),
            patch.object(daemon._shutdown_event, "wait", mock_wait),
        ):
            daemon.run()

        # First failure: 2s backoff (consecutive_failures=1)
        # Success: 60s poll interval wait (consecutive_failures reset to 0)
        # Third failure: 2s backoff (consecutive_failures=1, reset after success)
        assert wait_timeouts == [2.0, 60, 2.0]

    def test_backoff_caps_at_maximum(self, daemon):
        """Test that backoff caps at 300 seconds using tenacity."""
        wait_timeouts = []

        call_count = [0]

        def mock_poll():
            call_count[0] += 1
            # Shutdown on the 10th call to get exactly 10 backoffs
            if call_count[0] >= 10:
                daemon._shutdown_requested = True
            raise Exception("Simulated failure")

        def mock_wait(timeout=None):
            wait_timeouts.append(timeout)
            return False  # Not interrupted

        with (
            patch.object(daemon, "_poll", side_effect=mock_poll),
            patch.object(daemon, "_initialize_project_metadata"),
            patch.object(daemon._shutdown_event, "wait", mock_wait),
        ):
            daemon.run()

        # Expected backoffs: 2, 4, 8, 16, 32, 64, 128, 256, 300, 300
        # (2^1 through 2^8=256, then capped at 300 by tenacity for 2^9=512 and beyond)
        expected = [2.0, 4.0, 8.0, 16.0, 32.0, 64.0, 128.0, 256.0, 300.0, 300.0]
        assert wait_timeouts == expected

    def test_backoff_interruptible_for_shutdown(self, daemon):
        """Test that backoff sleep is interruptible during shutdown via Event."""
        wait_count = [0]

        def mock_poll():
            raise Exception("Always fail")

        def mock_wait(timeout=None):
            wait_count[0] += 1
            # Return True on first wait to indicate shutdown was signaled
            return True

        with (
            patch.object(daemon, "_poll", side_effect=mock_poll),
            patch.object(daemon, "_initialize_project_metadata"),
            patch.object(daemon._shutdown_event, "wait", mock_wait),
        ):
            daemon.run()

        # Should have only 1 wait call before shutdown was detected
        assert wait_count[0] == 1


# ============================================================================
# YOLO Label Removal During Workflow Tests
# ============================================================================


@pytest.mark.integration
class TestYoloLabelRemovalDuringWorkflow:
    """Tests for YOLO label removal detection during workflow execution.

    These tests verify that removing the YOLO label during a workflow
    prevents automatic progression (auto-advance and failure handling).
    """

    @pytest.fixture
    def daemon(self, temp_workspace_dir):
        """Create a daemon instance for testing."""
        import os

        config = MagicMock()
        config.poll_interval = 60
        config.watched_statuses = ["Research", "Plan", "Implement"]
        config.max_concurrent_workflows = 2
        config.database_path = f"{temp_workspace_dir}/test.db"
        config.workspace_dir = temp_workspace_dir
        config.project_urls = ["https://github.com/orgs/test/projects/1"]
        config.stage_models = {}
        config.github_enterprise_version = None
        config.ghes_logs_mask = False
        config.github_enterprise_host = None
        config.log_file = f"{temp_workspace_dir}/.kiln/logs/kiln.log"
        config.username_self = "test-user"

        # Create required directories
        os.makedirs(f"{temp_workspace_dir}/.kiln/logs", exist_ok=True)

        with patch("src.ticket_clients.github.GitHubTicketClient"):
            daemon = Daemon(config)
            daemon.ticket_client = MagicMock()
            yield daemon
            daemon.stop()

    def test_yolo_auto_advance_cancelled_when_label_removed(self, daemon):
        """Test that YOLO auto-advance is cancelled when label is removed during workflow.

        Scenario:
        1. Issue has YOLO label at poll time (in item.labels)
        2. Workflow runs successfully
        3. Before checking YOLO auto-advance, fresh labels are fetched
        4. YOLO label was removed during workflow (not in fresh_labels)
        5. Auto-advance should NOT happen
        6. Log message should indicate cancellation
        """
        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="github.com/owner/repo",
            status="Research",
            title="Test YOLO Issue",
            labels={Labels.YOLO},  # YOLO present at poll time
        )

        # Mock successful workflow completion (return a session ID string)
        daemon._run_workflow = MagicMock(return_value="session-123")

        # Mock worktree path exists
        with patch("pathlib.Path.exists", return_value=True):
            # Mock get_ticket_body to return valid research block
            daemon.ticket_client.get_ticket_body.return_value = (
                "Issue body\n<!-- kiln:research -->\nResearch content\n<!-- /kiln:research -->"
            )

            # Fresh labels do NOT contain YOLO (removed during workflow)
            daemon.ticket_client.get_ticket_labels.return_value = {"bug", "enhancement"}

            # Mock comments for timestamp update
            daemon.ticket_client.get_comments.return_value = []

            with patch("src.daemon.logger") as mock_logger:
                daemon._process_item_workflow(item)

                # Verify auto-advance was NOT called
                daemon.ticket_client.update_item_status.assert_not_called()

                # Verify cancellation was logged
                mock_logger.info.assert_any_call(
                    "YOLO: Cancelled auto-advance for github.com/owner/repo#42, "
                    "label removed during workflow"
                )

    def test_yolo_auto_advance_works_when_label_present(self, daemon):
        """Test that YOLO auto-advance works when label is still present.

        Scenario:
        1. Issue has YOLO label at poll time
        2. Workflow runs successfully
        3. Fresh labels still contain YOLO
        4. Auto-advance SHOULD happen
        """
        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="github.com/owner/repo",
            status="Research",
            title="Test YOLO Issue",
            labels={Labels.YOLO},  # YOLO present at poll time
        )

        # Mock successful workflow completion (return a session ID string)
        daemon._run_workflow = MagicMock(return_value="session-123")

        # Mock worktree path exists
        with patch("pathlib.Path.exists", return_value=True):
            # Mock get_ticket_body to return valid research block
            daemon.ticket_client.get_ticket_body.return_value = (
                "Issue body\n<!-- kiln:research -->\nResearch content\n<!-- /kiln:research -->"
            )

            # Fresh labels still contain YOLO
            daemon.ticket_client.get_ticket_labels.return_value = {Labels.YOLO, "bug"}

            # Mock comments for timestamp update
            daemon.ticket_client.get_comments.return_value = []

            daemon._process_item_workflow(item)

            # Verify auto-advance WAS called (Research -> Plan)
            daemon.ticket_client.update_item_status.assert_called_once_with(
                "PVI_123", "Plan", hostname="github.com"
            )

    def test_yolo_failure_handling_skipped_when_label_removed(self, daemon):
        """Test that YOLO failure handling is skipped when label is removed.

        Scenario:
        1. Issue has YOLO label at poll time
        2. Workflow fails
        3. Before handling YOLO failure, fresh labels are fetched
        4. YOLO label was removed during workflow
        5. yolo_failed label should NOT be added
        6. Log message should indicate skipped handling
        """
        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="github.com/owner/repo",
            status="Research",
            title="Test YOLO Issue",
            labels={Labels.YOLO},  # YOLO present at poll time
        )

        # Mock workflow failure
        daemon._run_workflow = MagicMock(side_effect=Exception("Workflow failed"))

        # Mock worktree path exists
        with patch("pathlib.Path.exists", return_value=True):
            # Fresh labels do NOT contain YOLO (removed during workflow)
            daemon.ticket_client.get_ticket_labels.return_value = {"bug"}

            with patch("src.daemon.logger") as mock_logger:
                # Expect the exception to be re-raised
                with pytest.raises(Exception, match="Workflow failed"):
                    daemon._process_item_workflow(item)

                # Verify yolo_failed was NOT added
                add_label_calls = daemon.ticket_client.add_label.call_args_list
                yolo_failed_calls = [
                    c for c in add_label_calls if Labels.YOLO_FAILED in c[0]
                ]
                assert len(yolo_failed_calls) == 0

                # Verify YOLO label was NOT removed (since it's already gone)
                remove_label_calls = daemon.ticket_client.remove_label.call_args_list
                yolo_remove_calls = [
                    c for c in remove_label_calls if Labels.YOLO in c[0]
                ]
                # The only remove_label call should be for the running label, not YOLO
                for call_args in yolo_remove_calls:
                    assert call_args[0][2] != Labels.YOLO

                # Verify skipped handling was logged
                mock_logger.info.assert_any_call(
                    "YOLO: Skipped failure handling for github.com/owner/repo#42, "
                    "label removed during workflow"
                )

    def test_yolo_failure_handling_works_when_label_present(self, daemon):
        """Test that YOLO failure handling works when label is still present.

        Scenario:
        1. Issue has YOLO label at poll time
        2. Workflow fails
        3. Fresh labels still contain YOLO
        4. yolo label should be removed and yolo_failed should be added
        """
        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="github.com/owner/repo",
            status="Research",
            title="Test YOLO Issue",
            labels={Labels.YOLO},  # YOLO present at poll time
        )

        # Mock workflow failure
        daemon._run_workflow = MagicMock(side_effect=Exception("Workflow failed"))

        # Mock worktree path exists
        with patch("pathlib.Path.exists", return_value=True):
            # Fresh labels still contain YOLO
            daemon.ticket_client.get_ticket_labels.return_value = {Labels.YOLO, "bug"}

            # Expect the exception to be re-raised
            with pytest.raises(Exception, match="Workflow failed"):
                daemon._process_item_workflow(item)

            # Verify YOLO label was removed
            daemon.ticket_client.remove_label.assert_any_call(
                "github.com/owner/repo", 42, Labels.YOLO
            )

            # Verify yolo_failed label was added
            daemon.ticket_client.add_label.assert_any_call(
                "github.com/owner/repo", 42, Labels.YOLO_FAILED
            )


# ============================================================================
# Implementation Complete Comment Tests
# ============================================================================


@pytest.mark.integration
class TestImplementationCompleteComment:
    """Tests for posting a comment to the issue when implementation completes.

    These tests verify that a comment with the PR link is posted to the issue
    when the Implement workflow completes and moves to Validate.
    """

    @pytest.fixture
    def daemon(self, temp_workspace_dir):
        """Create a daemon instance for testing."""
        import os

        config = MagicMock()
        config.poll_interval = 60
        config.watched_statuses = ["Research", "Plan", "Implement"]
        config.max_concurrent_workflows = 2
        config.database_path = f"{temp_workspace_dir}/test.db"
        config.workspace_dir = temp_workspace_dir
        config.project_urls = ["https://github.com/orgs/test/projects/1"]
        config.stage_models = {}
        config.github_enterprise_version = None
        config.ghes_logs_mask = False
        config.github_enterprise_host = None
        config.log_file = f"{temp_workspace_dir}/.kiln/logs/kiln.log"
        config.username_self = "test-user"

        # Create required directories
        os.makedirs(f"{temp_workspace_dir}/.kiln/logs", exist_ok=True)

        with patch("src.ticket_clients.github.GitHubTicketClient"):
            daemon = Daemon(config)
            daemon.ticket_client = MagicMock()
            yield daemon
            daemon.stop()

    def test_completion_comment_posted_when_implement_finishes(self, daemon):
        """Test that a comment with PR link is posted when Implement moves to Validate.

        Scenario:
        1. Issue is in Implement status with a linked PR
        2. Workflow completes successfully and moves to Validate
        3. A completion comment should be posted to the issue with the PR link
        """
        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="github.com/owner/repo",
            status="Implement",
            title="Test Implementation Issue",
            labels=set(),
        )

        # Mock successful workflow completion
        daemon._run_workflow = MagicMock(return_value="session-123")

        # Mock get_pr_for_issue to return PR info with number
        daemon._get_pr_for_issue = MagicMock(return_value={"number": 100, "body": "PR body"})

        # Mock worktree path exists
        with patch("pathlib.Path.exists", return_value=True):
            # Mock get_ticket_body (not strictly needed but good for completeness)
            daemon.ticket_client.get_ticket_body.return_value = "Issue body"

            # Mock comments for timestamp update
            daemon.ticket_client.get_comments.return_value = []

            # Mock _should_notify_completion to return True (triggers the code path)
            daemon._should_notify_completion = MagicMock(return_value=True)

            # Mock send_phase_completion_notification
            with patch("src.daemon.send_phase_completion_notification"):
                daemon._process_item_workflow(item)

        # Verify completion comment was posted
        daemon.ticket_client.add_comment.assert_called_once()
        call_args = daemon.ticket_client.add_comment.call_args
        assert call_args[0][0] == "github.com/owner/repo"
        assert call_args[0][1] == 42
        assert "Implementation complete!" in call_args[0][2]
        assert "https://github.com/owner/repo/pull/100" in call_args[0][2]

    def test_completion_comment_not_posted_when_no_pr(self, daemon):
        """Test that no comment is posted when there's no linked PR.

        Scenario:
        1. Issue is in Implement status but no PR is linked
        2. Workflow completes and moves to Validate
        3. No completion comment should be posted (can't link to PR)
        """
        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="github.com/owner/repo",
            status="Implement",
            title="Test Implementation Issue",
            labels=set(),
        )

        # Mock successful workflow completion
        daemon._run_workflow = MagicMock(return_value="session-123")

        # Mock get_pr_for_issue to return None (no PR found)
        daemon._get_pr_for_issue = MagicMock(return_value=None)

        # Mock worktree path exists
        with patch("pathlib.Path.exists", return_value=True):
            daemon.ticket_client.get_ticket_body.return_value = "Issue body"
            daemon.ticket_client.get_comments.return_value = []
            daemon._should_notify_completion = MagicMock(return_value=True)

            with patch("src.daemon.send_phase_completion_notification"):
                daemon._process_item_workflow(item)

        # Verify no comment was posted
        daemon.ticket_client.add_comment.assert_not_called()

    def test_completion_comment_not_posted_for_non_implement_status(self, daemon):
        """Test that completion comment is only posted for Implement -> Validate.

        Scenario:
        1. Issue is in Research status
        2. Workflow completes and moves to Plan
        3. No completion comment should be posted (wrong status)
        """
        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="github.com/owner/repo",
            status="Research",
            title="Test Research Issue",
            labels=set(),
        )

        # Mock successful workflow completion
        daemon._run_workflow = MagicMock(return_value="session-123")

        # Mock get_pr_for_issue
        daemon._get_pr_for_issue = MagicMock(return_value={"number": 100, "body": "PR body"})

        # Mock worktree path exists
        with patch("pathlib.Path.exists", return_value=True):
            # Mock get_ticket_body to return valid research block
            daemon.ticket_client.get_ticket_body.return_value = (
                "Issue body\n<!-- kiln:research -->\nResearch content\n<!-- /kiln:research -->"
            )
            daemon.ticket_client.get_comments.return_value = []
            daemon._should_notify_completion = MagicMock(return_value=False)

            with patch("src.daemon.send_phase_completion_notification"):
                daemon._process_item_workflow(item)

        # Verify no completion comment was posted (Research doesn't trigger it)
        daemon.ticket_client.add_comment.assert_not_called()

    def test_completion_comment_failure_does_not_break_workflow(self, daemon):
        """Test that failing to post a comment does not break the workflow.

        Scenario:
        1. Issue is in Implement status with a linked PR
        2. Workflow completes and moves to Validate
        3. Comment posting fails with an exception
        4. Workflow should complete normally (error is logged but not raised)
        """
        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="github.com/owner/repo",
            status="Implement",
            title="Test Implementation Issue",
            labels=set(),
        )

        # Mock successful workflow completion
        daemon._run_workflow = MagicMock(return_value="session-123")

        # Mock get_pr_for_issue to return PR info
        daemon._get_pr_for_issue = MagicMock(return_value={"number": 100, "body": "PR body"})

        # Mock add_comment to raise an exception
        daemon.ticket_client.add_comment.side_effect = Exception("GitHub API error")

        # Mock worktree path exists
        with patch("pathlib.Path.exists", return_value=True):
            daemon.ticket_client.get_ticket_body.return_value = "Issue body"
            daemon.ticket_client.get_comments.return_value = []
            daemon._should_notify_completion = MagicMock(return_value=True)

            with (
                patch("src.daemon.send_phase_completion_notification"),
                patch("src.daemon.logger") as mock_logger,
            ):
                # Should not raise an exception
                daemon._process_item_workflow(item)

                # Verify warning was logged
                mock_logger.warning.assert_any_call(
                    "Failed to post completion comment: GitHub API error"
                )
