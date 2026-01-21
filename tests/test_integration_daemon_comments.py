"""Integration tests for Daemon comment processing.

Tests for CommentProcessor methods including:
- _is_kiln_response() helper
- _generate_diff() helper
- Response comment posting
- _is_kiln_post() helper
- _initialize_comment_timestamp() method
- process() method
"""

from datetime import UTC
from unittest.mock import MagicMock, call, patch

import pytest

from src.daemon import Daemon
from src.interfaces import Comment, TicketItem


# ============================================================================
# Daemon Comment Processing Tests
# ============================================================================


@pytest.mark.integration
class TestDaemonIsKilnResponse:
    """Tests for CommentProcessor._is_kiln_response() helper method."""

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

    def test_is_kiln_response_with_response_marker(self, daemon):
        """Test detection of kiln response comment with marker."""
        body = "<!-- kiln:response -->\nApplied changes to **plan**:\n```diff\n+new line\n```"
        assert daemon.comment_processor._is_kiln_response(body) is True

    def test_is_kiln_response_with_whitespace_prefix(self, daemon):
        """Test that leading whitespace is stripped before checking."""
        body = "   \n\n<!-- kiln:response -->\nContent"
        assert daemon.comment_processor._is_kiln_response(body) is True

    def test_is_kiln_response_returns_false_for_user_comment(self, daemon):
        """Test that regular user comments are not detected as kiln responses."""
        body = "I think we should also consider option B"
        assert daemon.comment_processor._is_kiln_response(body) is False

    def test_is_kiln_response_returns_false_for_kiln_post(self, daemon):
        """Test that kiln posts (research/plan) are not detected as responses."""
        body = "<!-- kiln:research -->\n## Research Findings\nContent here"
        assert daemon.comment_processor._is_kiln_response(body) is False

    def test_is_kiln_response_returns_false_for_marker_in_middle(self, daemon):
        """Test that marker in middle of comment doesn't match (must be at start)."""
        body = "Some text\n<!-- kiln:response -->\nMore text"
        assert daemon.comment_processor._is_kiln_response(body) is False


@pytest.mark.integration
class TestDaemonGenerateDiff:
    """Tests for CommentProcessor._generate_diff() helper method."""

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

    def test_generate_diff_with_additions(self, daemon):
        """Test diff generation with added lines."""
        before = "Line 1\nLine 2"
        after = "Line 1\nLine 2\nLine 3"
        result = daemon.comment_processor._generate_diff(before, after, "plan")

        assert "+Line 3" in result
        assert "-Line 3" not in result

    def test_generate_diff_with_removals(self, daemon):
        """Test diff generation with removed lines."""
        before = "Line 1\nLine 2\nLine 3"
        after = "Line 1\nLine 3"
        result = daemon.comment_processor._generate_diff(before, after, "research")

        assert "-Line 2" in result

    def test_generate_diff_with_modifications(self, daemon):
        """Test diff generation with modified lines."""
        before = "Old content here"
        after = "New content here"
        result = daemon.comment_processor._generate_diff(before, after, "description")

        assert "-Old content here" in result
        assert "+New content here" in result

    def test_generate_diff_no_changes(self, daemon):
        """Test diff generation returns empty string when content is identical."""
        content = "Same content\nNo changes"
        result = daemon.comment_processor._generate_diff(content, content, "plan")

        assert result == ""

    def test_generate_diff_empty_before(self, daemon):
        """Test diff generation from empty content."""
        before = ""
        after = "New content"
        result = daemon.comment_processor._generate_diff(before, after, "research")

        assert "+New content" in result

    def test_generate_diff_empty_after(self, daemon):
        """Test diff generation to empty content."""
        before = "Old content"
        after = ""
        result = daemon.comment_processor._generate_diff(before, after, "plan")

        assert "-Old content" in result


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
        config.allowed_username = "real-user"
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

        with patch.object(daemon.runner, "run") as mock_run:
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
            patch.object(daemon.runner, "run"),
        ):
            mock_extract.side_effect = ["Same content", "Same content"]
            daemon.comment_processor.process(item)

            response_body = daemon.ticket_client.add_comment.call_args[0][2]
            assert "<!-- kiln:response -->" in response_body
            assert "No textual changes detected" in response_body


@pytest.mark.integration
class TestDaemonIsKilnPost:
    """Tests for CommentProcessor._is_kiln_post() helper method."""

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

    def test_is_kiln_post_with_research_marker(self, daemon):
        """Test detection of research post with HTML marker."""
        body = "<!-- kiln:research -->\n## Research Findings\nContent here"
        markers = tuple(daemon.comment_processor.KILN_POST_MARKERS.values())

        assert daemon.comment_processor._is_kiln_post(body, markers) is True

    def test_is_kiln_post_with_plan_marker(self, daemon):
        """Test detection of plan post with HTML marker."""
        body = "<!-- kiln:plan -->\n## Implementation Plan\nContent here"
        markers = tuple(daemon.comment_processor.KILN_POST_MARKERS.values())

        assert daemon.comment_processor._is_kiln_post(body, markers) is True

    def test_is_kiln_post_with_legacy_research_marker(self, daemon):
        """Test detection of legacy research post."""
        body = "## Research Findings\n\nSome research content"
        markers = tuple(daemon.comment_processor.KILN_POST_LEGACY_MARKERS.values())

        assert daemon.comment_processor._is_kiln_post(body, markers) is True

    def test_is_kiln_post_with_legacy_plan_marker(self, daemon):
        """Test detection of legacy plan post."""
        body = "## Implementation Plan:\n\nStep 1..."
        markers = tuple(daemon.comment_processor.KILN_POST_LEGACY_MARKERS.values())

        assert daemon.comment_processor._is_kiln_post(body, markers) is True

    def test_is_kiln_post_with_whitespace_prefix(self, daemon):
        """Test that leading whitespace is stripped before checking."""
        body = "   \n\n<!-- kiln:research -->\nContent"
        markers = tuple(daemon.comment_processor.KILN_POST_MARKERS.values())

        assert daemon.comment_processor._is_kiln_post(body, markers) is True

    def test_is_kiln_post_returns_false_for_user_comment(self, daemon):
        """Test that regular user comments are not detected as kiln posts."""
        body = "I think we should also consider option B"
        markers = tuple(daemon.comment_processor.KILN_POST_MARKERS.values()) + tuple(
            daemon.comment_processor.KILN_POST_LEGACY_MARKERS.values()
        )

        assert daemon.comment_processor._is_kiln_post(body, markers) is False

    def test_is_kiln_post_returns_false_for_marker_in_middle(self, daemon):
        """Test that marker in middle of comment doesn't match (must be at start)."""
        body = "Some text\n<!-- kiln:research -->\nMore text"
        markers = tuple(daemon.comment_processor.KILN_POST_MARKERS.values())

        assert daemon.comment_processor._is_kiln_post(body, markers) is False


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

    def test_initialize_returns_none_for_empty_comments(self, daemon):
        """Test that empty comment list returns None."""

        item = TicketItem(
            item_id="PVI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
        )

        result = daemon.comment_processor._initialize_comment_timestamp(item, [])
        assert result is None

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
        config.allowed_username = "real-user"
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

        with patch.object(daemon.runner, "run") as mock_run:
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
        # All comments must be from allowed_username ("real-user") to pass the filter
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

        with patch.object(daemon.runner, "run") as mock_run:
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

        with patch.object(daemon.runner, "run") as mock_run:
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
        # All comments must be from allowed_username ("real-user") to pass the filter
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

        with patch.object(daemon.runner, "run") as mock_run:
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

        with patch.object(daemon.runner, "run") as mock_run:
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
        # All comments must be from allowed_username ("real-user") to pass the filter
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

        with patch.object(daemon.runner, "run") as mock_run:
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
