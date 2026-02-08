"""Unit tests for CommentProcessor class."""

from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from src.comment_processor import CommentProcessor
from src.interfaces import Comment, TicketItem


def _create_mock_config():
    """Create a mock Config object for testing."""
    config = Mock()
    config.slack_dm_on_comment = True
    return config


@pytest.mark.unit
class TestCommentProcessorGetWorktreePath:
    """Tests for _get_worktree_path method."""

    def test_get_worktree_path_with_owner_repo(self):
        """Test worktree path generation with owner/repo format."""
        processor = CommentProcessor(
            Mock(), Mock(), Mock(), "/worktrees", config=_create_mock_config()
        )
        path = processor._get_worktree_path("owner/repo", 42)
        assert path == "/worktrees/repo-issue-42"

    def test_get_worktree_path_without_owner(self):
        """Test worktree path generation with repo name only."""
        processor = CommentProcessor(
            Mock(), Mock(), Mock(), "/worktrees", config=_create_mock_config()
        )
        path = processor._get_worktree_path("repo", 123)
        assert path == "/worktrees/repo-issue-123"


@pytest.mark.unit
class TestCommentProcessorConstants:
    """Tests for CommentProcessor constants."""

    def test_kiln_post_markers_defined(self):
        """Test KILN_POST_MARKERS are defined."""
        assert "research" in CommentProcessor.KILN_POST_MARKERS
        assert "plan" in CommentProcessor.KILN_POST_MARKERS

    def test_kiln_response_marker_defined(self):
        """Test KILN_RESPONSE_MARKER is defined."""
        assert CommentProcessor.KILN_RESPONSE_MARKER == "<!-- kiln:response -->"


@pytest.mark.unit
class TestCommentProcessorIsKilnPost:
    """Tests for _is_kiln_post method."""

    @pytest.fixture
    def processor(self):
        """Create a CommentProcessor instance for testing."""
        return CommentProcessor(Mock(), Mock(), Mock(), "/worktrees", config=_create_mock_config())

    def test_is_kiln_post_with_research_marker(self, processor):
        """Test detection of research marker."""
        body = "<!-- kiln:research -->\n## Research content"
        markers = tuple(CommentProcessor.KILN_POST_MARKERS.values())
        assert processor._is_kiln_post(body, markers) is True

    def test_is_kiln_post_with_plan_marker(self, processor):
        """Test detection of plan marker."""
        body = "<!-- kiln:plan -->\n## Plan content"
        markers = tuple(CommentProcessor.KILN_POST_MARKERS.values())
        assert processor._is_kiln_post(body, markers) is True

    def test_is_kiln_post_with_legacy_marker(self, processor):
        """Test detection of legacy research marker."""
        body = "## Research Findings\n\nSome content"
        markers = tuple(CommentProcessor.KILN_POST_LEGACY_MARKERS.values())
        assert processor._is_kiln_post(body, markers) is True

    def test_is_kiln_post_with_whitespace_prefix(self, processor):
        """Test detection with leading whitespace."""
        body = "  <!-- kiln:research -->\n## Research content"
        markers = tuple(CommentProcessor.KILN_POST_MARKERS.values())
        assert processor._is_kiln_post(body, markers) is True

    def test_is_kiln_post_returns_false_for_user_comment(self, processor):
        """Test that normal user comments are not detected as kiln posts."""
        body = "This is a regular user comment"
        markers = tuple(CommentProcessor.KILN_POST_MARKERS.values())
        assert processor._is_kiln_post(body, markers) is False


@pytest.mark.unit
class TestCommentProcessorIsKilnResponse:
    """Tests for _is_kiln_response method."""

    @pytest.fixture
    def processor(self):
        """Create a CommentProcessor instance for testing."""
        return CommentProcessor(Mock(), Mock(), Mock(), "/worktrees", config=_create_mock_config())

    def test_is_kiln_response_with_marker(self, processor):
        """Test detection of kiln response marker."""
        body = "<!-- kiln:response -->\nApplied changes to **plan**"
        assert processor._is_kiln_response(body) is True

    def test_is_kiln_response_with_whitespace(self, processor):
        """Test detection with leading whitespace."""
        body = "  <!-- kiln:response -->\nApplied changes"
        assert processor._is_kiln_response(body) is True

    def test_is_kiln_response_returns_false_for_user_comment(self, processor):
        """Test that user comments are not detected as responses."""
        body = "This is a user comment"
        assert processor._is_kiln_response(body) is False


@pytest.mark.unit
class TestCommentProcessorGenerateDiff:
    """Tests for _generate_diff method."""

    @pytest.fixture
    def processor(self):
        """Create a CommentProcessor instance for testing."""
        return CommentProcessor(Mock(), Mock(), Mock(), "/worktrees", config=_create_mock_config())

    def test_generate_diff_with_additions(self, processor):
        """Test diff generation with added lines."""
        before = "Line 1\nLine 2"
        after = "Line 1\nLine 2\nLine 3"
        result = processor._generate_diff(before, after, "plan")
        assert "+Line 3" in result

    def test_generate_diff_with_removals(self, processor):
        """Test diff generation with removed lines."""
        before = "Line 1\nLine 2\nLine 3"
        after = "Line 1\nLine 2"
        result = processor._generate_diff(before, after, "research")
        assert "-Line 3" in result

    def test_generate_diff_no_changes(self, processor):
        """Test diff generation when content is identical."""
        content = "Same content"
        result = processor._generate_diff(content, content, "plan")
        assert result == ""


@pytest.mark.unit
class TestCommentProcessorGetTargetType:
    """Tests for _get_target_type method."""

    @pytest.fixture
    def processor(self):
        """Create a CommentProcessor instance for testing."""
        return CommentProcessor(Mock(), Mock(), Mock(), "/worktrees", config=_create_mock_config())

    def test_get_target_type_plan_status(self, processor):
        """Test target type for Plan status."""
        item = Mock(status="Plan")
        assert processor._get_target_type(item) == "plan"

    def test_get_target_type_research_status(self, processor):
        """Test target type for Research status."""
        item = Mock(status="Research")
        assert processor._get_target_type(item) == "research"

    def test_get_target_type_backlog_status(self, processor):
        """Test target type for Backlog status returns description."""
        item = Mock(status="Backlog")
        assert processor._get_target_type(item) == "description"


@pytest.mark.unit
class TestCommentProcessorInitializeCommentTimestamp:
    """Tests for _initialize_comment_timestamp method."""

    @pytest.fixture
    def processor(self):
        """Create a CommentProcessor instance for testing."""
        return CommentProcessor(Mock(), Mock(), Mock(), "/worktrees", config=_create_mock_config())

    def test_initialize_comment_timestamp_finds_kiln_post(self, processor):
        """Test initialization finds latest kiln post."""
        item = Mock()
        timestamp = datetime(2024, 1, 15, 10, 30, 0)
        comments = [
            Mock(
                body="user comment", has_thumbs_up=False, created_at=datetime(2024, 1, 14, 10, 0, 0)
            ),
            Mock(
                body="<!-- kiln:research -->\n## Research",
                has_thumbs_up=False,
                created_at=timestamp,
            ),
        ]
        result = processor._initialize_comment_timestamp(item, comments)
        assert result == timestamp.isoformat()

    def test_initialize_comment_timestamp_finds_thumbs_up_comment(self, processor):
        """Test initialization finds already-processed comment."""
        item = Mock()
        timestamp = datetime(2024, 1, 15, 10, 30, 0)
        comments = [
            Mock(
                body="first comment",
                has_thumbs_up=False,
                created_at=datetime(2024, 1, 14, 10, 0, 0),
            ),
            Mock(body="processed comment", has_thumbs_up=True, created_at=timestamp),
        ]
        result = processor._initialize_comment_timestamp(item, comments)
        assert result == timestamp.isoformat()


@pytest.mark.unit
class TestCommentProcessorAllowlist:
    """Tests for CommentProcessor username_self filtering."""

    def test_username_self_filters_comments(self):
        """Test that comments from non-allowed users are filtered out."""
        ticket_client = Mock()
        database = Mock()
        runner = Mock()

        # Create processor with username_self
        processor = CommentProcessor(
            ticket_client,
            database,
            runner,
            "/worktrees",
            config=_create_mock_config(),
            username_self="allowed_user",
        )

        # Mock database to return stored state with a timestamp
        stored_state = Mock()
        stored_state.last_processed_comment_timestamp = "2024-01-14T10:00:00+00:00"
        stored_state.last_known_comment_count = 0
        database.get_issue_state.return_value = stored_state

        # Create comments using abstract Comment type - one from allowed user, one from blocked user
        allowed_comment = Comment(
            id="IC_1",
            database_id=1,
            body="This is from an allowed user",
            created_at=datetime(2024, 1, 15, 10, 0, 0),
            author="allowed_user",
            is_processed=False,
            is_processing=False,
        )
        blocked_comment = Comment(
            id="IC_2",
            database_id=2,
            body="This is from a blocked user",
            created_at=datetime(2024, 1, 15, 11, 0, 0),
            author="blocked_user",
            is_processed=False,
            is_processing=False,
        )

        ticket_client.get_comments_since.return_value = [allowed_comment, blocked_comment]

        # Create a ticket item using abstract TicketItem type
        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
            comment_count=2,
        )

        # Mock the methods that would be called after filtering
        with (
            patch.object(processor, "_get_target_type", return_value="research"),
            patch.object(processor, "_extract_section_content", return_value="content"),
            patch.object(
                processor, "_ensure_worktree_exists", return_value="/worktrees/repo-issue-42"
            ),
            patch.object(processor, "_apply_comment_to_kiln_post"),
            patch.object(processor, "_generate_diff", return_value="-old\n+new"),
            patch("src.comment_processor.set_issue_context"),
            patch("src.comment_processor.clear_issue_context"),
        ):
            ticket_client.add_comment.return_value = Comment(
                id="IC_3",
                database_id=3,
                body="response",
                created_at=datetime(2024, 1, 15, 12, 0, 0),
                author="test-user",
            )

            processor.process(item)

            # Verify only allowed_comment was processed (reaction was added only to it)
            # Check that add_reaction was called with allowed_comment's id
            reaction_calls = [
                c for c in ticket_client.add_reaction.call_args_list if c[0][1] == "THUMBS_UP"
            ]
            comment_ids = [c[0][0] for c in reaction_calls]
            assert "IC_1" in comment_ids  # allowed_comment was processed
            assert "IC_2" not in comment_ids  # blocked_comment was filtered out

    def test_team_member_comments_filtered_silently(self):
        """Test that comments from team members are filtered out without WARNING log."""
        ticket_client = Mock()
        database = Mock()
        runner = Mock()

        # Create processor with username_self and team_usernames
        processor = CommentProcessor(
            ticket_client,
            database,
            runner,
            "/worktrees",
            config=_create_mock_config(),
            username_self="allowed_user",
            team_usernames=["teammate1", "teammate2"],
        )

        # Mock database to return stored state with a timestamp
        stored_state = Mock()
        stored_state.last_processed_comment_timestamp = "2024-01-14T10:00:00+00:00"
        stored_state.last_known_comment_count = 0
        database.get_issue_state.return_value = stored_state

        # Create comments - one from allowed user, one from team member, one from blocked user
        allowed_comment = Comment(
            id="IC_1",
            database_id=1,
            body="This is from an allowed user",
            created_at=datetime(2024, 1, 15, 10, 0, 0),
            author="allowed_user",
            is_processed=False,
            is_processing=False,
        )
        team_comment = Comment(
            id="IC_2",
            database_id=2,
            body="This is from a team member",
            created_at=datetime(2024, 1, 15, 11, 0, 0),
            author="teammate1",
            is_processed=False,
            is_processing=False,
        )
        blocked_comment = Comment(
            id="IC_3",
            database_id=3,
            body="This is from a blocked user",
            created_at=datetime(2024, 1, 15, 12, 0, 0),
            author="blocked_user",
            is_processed=False,
            is_processing=False,
        )

        ticket_client.get_comments_since.return_value = [
            allowed_comment,
            team_comment,
            blocked_comment,
        ]

        # Create a ticket item using abstract TicketItem type
        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
            comment_count=3,
        )

        # Mock the methods that would be called after filtering
        with (
            patch.object(processor, "_get_target_type", return_value="research"),
            patch.object(processor, "_extract_section_content", return_value="content"),
            patch.object(
                processor, "_ensure_worktree_exists", return_value="/worktrees/repo-issue-42"
            ),
            patch.object(processor, "_apply_comment_to_kiln_post"),
            patch.object(processor, "_generate_diff", return_value="-old\n+new"),
            patch("src.comment_processor.set_issue_context"),
            patch("src.comment_processor.clear_issue_context"),
        ):
            ticket_client.add_comment.return_value = Comment(
                id="IC_4",
                database_id=4,
                body="response",
                created_at=datetime(2024, 1, 15, 13, 0, 0),
                author="test-user",
            )

            processor.process(item)

            # Verify only allowed_comment was processed
            reaction_calls = [
                c for c in ticket_client.add_reaction.call_args_list if c[0][1] == "THUMBS_UP"
            ]
            comment_ids = [c[0][0] for c in reaction_calls]
            assert "IC_1" in comment_ids  # allowed_comment was processed
            assert "IC_2" not in comment_ids  # team_comment was filtered out
            assert "IC_3" not in comment_ids  # blocked_comment was filtered out


@pytest.mark.unit
class TestCommentProcessorWrapDiffLine:
    """Tests for _wrap_diff_line method."""

    @pytest.fixture
    def processor(self):
        """Create a CommentProcessor instance for testing."""
        return CommentProcessor(Mock(), Mock(), Mock(), "/worktrees", config=_create_mock_config())

    def test_wrap_diff_line_short_line_unchanged(self, processor):
        """Test that short lines are returned unchanged."""
        line = "+short line"
        result = processor._wrap_diff_line(line, width=70)
        assert result == line

    def test_wrap_diff_line_empty_line(self, processor):
        """Test that empty lines are returned unchanged."""
        assert processor._wrap_diff_line("", width=70) == ""

    def test_wrap_diff_line_hunk_header_not_wrapped(self, processor):
        """Test that hunk headers are never wrapped."""
        header = "@@ -1,5 +1,6 @@ " + "x" * 100
        result = processor._wrap_diff_line(header, width=70)
        assert result == header

    def test_wrap_diff_line_preserves_plus_prefix(self, processor):
        """Test that + prefix is preserved on continuation lines."""
        line = "+" + "a" * 100
        result = processor._wrap_diff_line(line, width=50)
        lines = result.split("\n")
        assert len(lines) > 1
        for wrapped_line in lines:
            assert wrapped_line.startswith("+")

    def test_wrap_diff_line_preserves_minus_prefix(self, processor):
        """Test that - prefix is preserved on continuation lines."""
        line = "-" + "b" * 100
        result = processor._wrap_diff_line(line, width=50)
        lines = result.split("\n")
        assert len(lines) > 1
        for wrapped_line in lines:
            assert wrapped_line.startswith("-")

    def test_wrap_diff_line_preserves_space_prefix(self, processor):
        """Test that space prefix is preserved on continuation lines."""
        line = " " + "c" * 100
        result = processor._wrap_diff_line(line, width=50)
        lines = result.split("\n")
        assert len(lines) > 1
        for wrapped_line in lines:
            assert wrapped_line.startswith(" ")

    def test_wrap_diff_line_breaks_long_words(self, processor):
        """Test that unbreakable strings (URLs) are forcibly broken."""
        url = "+https://example.com/very/long/path/that/exceeds/width"
        result = processor._wrap_diff_line(url, width=40)
        lines = result.split("\n")
        for wrapped_line in lines:
            assert len(wrapped_line) <= 40


@pytest.mark.unit
class TestCommentProcessorWrapDiff:
    """Tests for _wrap_diff method."""

    @pytest.fixture
    def processor(self):
        """Create a CommentProcessor instance for testing."""
        return CommentProcessor(Mock(), Mock(), Mock(), "/worktrees", config=_create_mock_config())

    def test_wrap_diff_wraps_all_lines(self, processor):
        """Test that all lines in diff are wrapped."""
        diff = "+short\n+" + "a" * 100 + "\n-" + "b" * 100
        result = processor._wrap_diff(diff, width=50)
        for line in result.split("\n"):
            assert len(line) <= 50

    def test_wrap_diff_preserves_line_count_for_short_diff(self, processor):
        """Test that short diffs have same line count."""
        diff = "+line1\n-line2\n line3"
        result = processor._wrap_diff(diff, width=70)
        assert result == diff


@pytest.mark.unit
class TestCommentProcessorSkipBacklog:
    """Tests for skipping comment processing on Backlog items."""

    def test_process_backlog_item_skips_entirely(self):
        """Test that Backlog items are skipped entirely - no processing at all."""
        ticket_client = Mock()
        database = Mock()
        runner = Mock()

        processor = CommentProcessor(
            ticket_client,
            database,
            runner,
            "/worktrees",
            config=_create_mock_config(),
            username_self="allowed_user",
        )

        # Create a ticket item with Backlog status
        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Backlog",
            title="Test Backlog Issue",
            comment_count=1,
        )

        with (
            patch("src.comment_processor.set_issue_context"),
            patch("src.comment_processor.clear_issue_context"),
        ):
            processor.process(item)

            # Verify nothing was called - processing skipped entirely
            ticket_client.add_reaction.assert_not_called()
            ticket_client.add_comment.assert_not_called()
            ticket_client.get_comments_since.assert_not_called()
            database.get_issue_state.assert_not_called()

    def test_process_research_item_adds_reactions(self):
        """Test that reactions are added when item.status == 'Research'."""
        ticket_client = Mock()
        database = Mock()
        runner = Mock()

        processor = CommentProcessor(
            ticket_client,
            database,
            runner,
            "/worktrees",
            config=_create_mock_config(),
            username_self="allowed_user",
        )

        # Mock database to return stored state with a timestamp
        stored_state = Mock()
        stored_state.last_processed_comment_timestamp = "2024-01-14T10:00:00+00:00"
        stored_state.last_known_comment_count = 0
        database.get_issue_state.return_value = stored_state

        # Create a comment from the allowed user
        user_comment = Comment(
            id="IC_1",
            database_id=1,
            body="This is feedback on research",
            created_at=datetime(2024, 1, 15, 10, 0, 0),
            author="allowed_user",
            is_processed=False,
            is_processing=False,
        )

        ticket_client.get_comments_since.return_value = [user_comment]

        # Create a ticket item with Research status
        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Research Issue",
            comment_count=1,
        )

        # Mock the methods that would be called after filtering
        with (
            patch.object(processor, "_get_target_type", return_value="research"),
            patch.object(processor, "_extract_section_content", return_value="content"),
            patch.object(
                processor, "_ensure_worktree_exists", return_value="/worktrees/repo-issue-42"
            ),
            patch.object(processor, "_apply_comment_to_kiln_post"),
            patch.object(processor, "_generate_diff", return_value="-old\n+new"),
            patch("src.comment_processor.set_issue_context"),
            patch("src.comment_processor.clear_issue_context"),
        ):
            ticket_client.add_comment.return_value = Comment(
                id="IC_2",
                database_id=2,
                body="response",
                created_at=datetime(2024, 1, 15, 12, 0, 0),
                author="test-user",
            )

            processor.process(item)

            # Verify add_reaction WAS called - should have both EYES and THUMBS_UP
            reaction_calls = ticket_client.add_reaction.call_args_list
            reaction_types = [call[0][1] for call in reaction_calls]
            assert "EYES" in reaction_types, "EYES reaction should be added for Research items"
            assert "THUMBS_UP" in reaction_types, (
                "THUMBS_UP reaction should be added for Research items"
            )

    def test_process_plan_item_adds_reactions(self):
        """Test that reactions are added when item.status == 'Plan'."""
        ticket_client = Mock()
        database = Mock()
        runner = Mock()

        processor = CommentProcessor(
            ticket_client,
            database,
            runner,
            "/worktrees",
            config=_create_mock_config(),
            username_self="allowed_user",
        )

        # Mock database to return stored state with a timestamp
        stored_state = Mock()
        stored_state.last_processed_comment_timestamp = "2024-01-14T10:00:00+00:00"
        stored_state.last_known_comment_count = 0
        database.get_issue_state.return_value = stored_state

        # Create a comment from the allowed user
        user_comment = Comment(
            id="IC_1",
            database_id=1,
            body="This is feedback on the plan",
            created_at=datetime(2024, 1, 15, 10, 0, 0),
            author="allowed_user",
            is_processed=False,
            is_processing=False,
        )

        ticket_client.get_comments_since.return_value = [user_comment]

        # Create a ticket item with Plan status
        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Plan",
            title="Test Plan Issue",
            comment_count=1,
        )

        # Mock the methods that would be called after filtering
        with (
            patch.object(processor, "_get_target_type", return_value="plan"),
            patch.object(processor, "_extract_section_content", return_value="content"),
            patch.object(
                processor, "_ensure_worktree_exists", return_value="/worktrees/repo-issue-42"
            ),
            patch.object(processor, "_apply_comment_to_kiln_post"),
            patch.object(processor, "_generate_diff", return_value="-old\n+new"),
            patch("src.comment_processor.set_issue_context"),
            patch("src.comment_processor.clear_issue_context"),
        ):
            ticket_client.add_comment.return_value = Comment(
                id="IC_2",
                database_id=2,
                body="response",
                created_at=datetime(2024, 1, 15, 12, 0, 0),
                author="test-user",
            )

            processor.process(item)

            # Verify add_reaction WAS called - should have both EYES and THUMBS_UP
            reaction_calls = ticket_client.add_reaction.call_args_list
            reaction_types = [call[0][1] for call in reaction_calls]
            assert "EYES" in reaction_types, "EYES reaction should be added for Plan items"
            assert "THUMBS_UP" in reaction_types, (
                "THUMBS_UP reaction should be added for Plan items"
            )


@pytest.mark.unit
class TestCommentProcessorEyesReactionCleanup:
    """Tests for eyes reaction cleanup on processing failure."""

    def test_eyes_reaction_removed_on_failure(self):
        """Test that eyes reactions are removed when comment processing fails."""
        ticket_client = Mock()
        database = Mock()
        runner = Mock()

        processor = CommentProcessor(
            ticket_client,
            database,
            runner,
            "/worktrees",
            config=_create_mock_config(),
            username_self="allowed_user",
        )

        # Mock database to return stored state with a timestamp
        stored_state = Mock()
        stored_state.last_processed_comment_timestamp = "2024-01-14T10:00:00+00:00"
        stored_state.last_known_comment_count = 0
        database.get_issue_state.return_value = stored_state

        # Create a comment from the allowed user
        user_comment = Comment(
            id="IC_1",
            database_id=1,
            body="This is feedback",
            created_at=datetime(2024, 1, 15, 10, 0, 0),
            author="allowed_user",
            is_processed=False,
            is_processing=False,
        )

        ticket_client.get_comments_since.return_value = [user_comment]

        # Create a ticket item
        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
            comment_count=1,
        )

        with (
            patch.object(processor, "_get_target_type", return_value="research"),
            patch.object(processor, "_extract_section_content", return_value="content"),
            patch.object(
                processor, "_ensure_worktree_exists", return_value="/worktrees/repo-issue-42"
            ),
            patch.object(
                processor, "_apply_comment_to_kiln_post", side_effect=Exception("Processing failed")
            ),
            patch("src.comment_processor.set_issue_context"),
            patch("src.comment_processor.clear_issue_context"),
        ):
            processor.process(item)

            # Verify remove_reaction was called with EYES
            remove_reaction_calls = [
                c for c in ticket_client.remove_reaction.call_args_list if c[0][1] == "EYES"
            ]
            assert len(remove_reaction_calls) == 1
            assert remove_reaction_calls[0][0][0] == "IC_1"

    def test_database_cleanup_on_failure(self):
        """Test that database processing records are cleaned up on failure."""
        ticket_client = Mock()
        database = Mock()
        runner = Mock()

        processor = CommentProcessor(
            ticket_client,
            database,
            runner,
            "/worktrees",
            config=_create_mock_config(),
            username_self="allowed_user",
        )

        # Mock database to return stored state with a timestamp
        stored_state = Mock()
        stored_state.last_processed_comment_timestamp = "2024-01-14T10:00:00+00:00"
        stored_state.last_known_comment_count = 0
        database.get_issue_state.return_value = stored_state

        # Create a comment from the allowed user
        user_comment = Comment(
            id="IC_1",
            database_id=1,
            body="This is feedback",
            created_at=datetime(2024, 1, 15, 10, 0, 0),
            author="allowed_user",
            is_processed=False,
            is_processing=False,
        )

        ticket_client.get_comments_since.return_value = [user_comment]

        # Create a ticket item
        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
            comment_count=1,
        )

        with (
            patch.object(processor, "_get_target_type", return_value="research"),
            patch.object(processor, "_extract_section_content", return_value="content"),
            patch.object(
                processor, "_ensure_worktree_exists", return_value="/worktrees/repo-issue-42"
            ),
            patch.object(
                processor, "_apply_comment_to_kiln_post", side_effect=Exception("Processing failed")
            ),
            patch("src.comment_processor.set_issue_context"),
            patch("src.comment_processor.clear_issue_context"),
        ):
            processor.process(item)

            # Verify add_processing_comment was called when adding eyes
            database.add_processing_comment.assert_called_once_with("owner/repo", 42, "IC_1")

            # Verify remove_processing_comment was called in finally block
            database.remove_processing_comment.assert_called_once_with("owner/repo", 42, "IC_1")

    def test_database_cleanup_on_success(self):
        """Test that database processing records are cleaned up on success."""
        ticket_client = Mock()
        database = Mock()
        runner = Mock()

        processor = CommentProcessor(
            ticket_client,
            database,
            runner,
            "/worktrees",
            config=_create_mock_config(),
            username_self="allowed_user",
        )

        # Mock database to return stored state with a timestamp
        stored_state = Mock()
        stored_state.last_processed_comment_timestamp = "2024-01-14T10:00:00+00:00"
        stored_state.last_known_comment_count = 0
        database.get_issue_state.return_value = stored_state

        # Create a comment from the allowed user
        user_comment = Comment(
            id="IC_1",
            database_id=1,
            body="This is feedback",
            created_at=datetime(2024, 1, 15, 10, 0, 0),
            author="allowed_user",
            is_processed=False,
            is_processing=False,
        )

        ticket_client.get_comments_since.return_value = [user_comment]

        # Create a ticket item
        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
            comment_count=1,
        )

        response_comment = Comment(
            id="IC_2",
            database_id=456,
            body="response",
            created_at=datetime(2024, 1, 15, 12, 0, 0),
            author="test-user",
        )

        with (
            patch.object(processor, "_get_target_type", return_value="research"),
            patch.object(processor, "_extract_section_content", return_value="content"),
            patch.object(
                processor, "_ensure_worktree_exists", return_value="/worktrees/repo-issue-42"
            ),
            patch.object(processor, "_apply_comment_to_kiln_post"),
            patch.object(processor, "_generate_diff", return_value="-old\n+new"),
            patch("src.comment_processor.set_issue_context"),
            patch("src.comment_processor.clear_issue_context"),
        ):
            ticket_client.add_comment.return_value = response_comment

            processor.process(item)

            # Verify add_processing_comment was called when adding eyes
            database.add_processing_comment.assert_called_once_with("owner/repo", 42, "IC_1")

            # Verify remove_processing_comment was called in finally block (even on success)
            database.remove_processing_comment.assert_called_once_with("owner/repo", 42, "IC_1")

            # Verify remove_reaction for EYES was NOT called on success (only on failure)
            remove_reaction_calls = [
                c for c in ticket_client.remove_reaction.call_args_list if c[0][1] == "EYES"
            ]
            assert len(remove_reaction_calls) == 0

    def test_multiple_comments_cleanup_on_failure(self):
        """Test that all comments have eyes reactions removed on failure."""
        ticket_client = Mock()
        database = Mock()
        runner = Mock()

        processor = CommentProcessor(
            ticket_client,
            database,
            runner,
            "/worktrees",
            config=_create_mock_config(),
            username_self="allowed_user",
        )

        # Mock database to return stored state with a timestamp
        stored_state = Mock()
        stored_state.last_processed_comment_timestamp = "2024-01-14T10:00:00+00:00"
        stored_state.last_known_comment_count = 0
        database.get_issue_state.return_value = stored_state

        # Create multiple comments from the allowed user
        comments = [
            Comment(
                id=f"IC_{i}",
                database_id=i,
                body=f"Feedback {i}",
                created_at=datetime(2024, 1, 15, 10 + i, 0, 0),
                author="allowed_user",
                is_processed=False,
                is_processing=False,
            )
            for i in range(1, 4)
        ]

        ticket_client.get_comments_since.return_value = comments

        # Create a ticket item
        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
            comment_count=3,
        )

        with (
            patch.object(processor, "_get_target_type", return_value="research"),
            patch.object(processor, "_extract_section_content", return_value="content"),
            patch.object(
                processor, "_ensure_worktree_exists", return_value="/worktrees/repo-issue-42"
            ),
            patch.object(
                processor, "_apply_comment_to_kiln_post", side_effect=Exception("Processing failed")
            ),
            patch("src.comment_processor.set_issue_context"),
            patch("src.comment_processor.clear_issue_context"),
        ):
            processor.process(item)

            # Verify remove_reaction was called for all 3 comments
            remove_reaction_calls = [
                c for c in ticket_client.remove_reaction.call_args_list if c[0][1] == "EYES"
            ]
            assert len(remove_reaction_calls) == 3
            comment_ids = [c[0][0] for c in remove_reaction_calls]
            assert "IC_1" in comment_ids
            assert "IC_2" in comment_ids
            assert "IC_3" in comment_ids

            # Verify database cleanup for all 3 comments
            assert database.remove_processing_comment.call_count == 3


@pytest.mark.unit
class TestCommentProcessorSlackNotification:
    """Tests for Slack notification integration in CommentProcessor."""

    def test_slack_notification_called_when_enabled(self):
        """Test that Slack notification is sent when config.slack_dm_on_comment is True."""
        ticket_client = Mock()
        database = Mock()
        runner = Mock()

        config = Mock()
        config.slack_dm_on_comment = True

        processor = CommentProcessor(
            ticket_client,
            database,
            runner,
            "/worktrees",
            config=config,
            username_self="allowed_user",
        )

        # Mock database to return stored state with a timestamp
        stored_state = Mock()
        stored_state.last_processed_comment_timestamp = "2024-01-14T10:00:00+00:00"
        stored_state.last_known_comment_count = 0
        database.get_issue_state.return_value = stored_state

        # Create a comment from the allowed user
        user_comment = Comment(
            id="IC_1",
            database_id=1,
            body="This is feedback",
            created_at=datetime(2024, 1, 15, 10, 0, 0),
            author="allowed_user",
            is_processed=False,
            is_processing=False,
        )

        ticket_client.get_comments_since.return_value = [user_comment]

        # Create a ticket item
        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
            comment_count=1,
        )

        response_comment = Comment(
            id="IC_2",
            database_id=456,
            body="response",
            created_at=datetime(2024, 1, 15, 12, 0, 0),
            author="test-user",
        )

        with (
            patch.object(processor, "_get_target_type", return_value="research"),
            patch.object(processor, "_extract_section_content", return_value="content"),
            patch.object(
                processor, "_ensure_worktree_exists", return_value="/worktrees/repo-issue-42"
            ),
            patch.object(processor, "_apply_comment_to_kiln_post"),
            patch.object(processor, "_generate_diff", return_value="-old\n+new"),
            patch("src.comment_processor.set_issue_context"),
            patch("src.comment_processor.clear_issue_context"),
            patch("src.comment_processor.send_comment_processed_notification") as mock_notify,
        ):
            ticket_client.add_comment.return_value = response_comment

            processor.process(item)

            # Verify Slack notification was called with correct arguments
            mock_notify.assert_called_once_with(
                issue_number=42,
                issue_title="Test Issue",
                comment_url="https://owner/repo/issues/42#issuecomment-456",
            )

    def test_slack_notification_not_called_when_disabled(self):
        """Test that Slack notification is NOT sent when config.slack_dm_on_comment is False."""
        ticket_client = Mock()
        database = Mock()
        runner = Mock()

        config = Mock()
        config.slack_dm_on_comment = False

        processor = CommentProcessor(
            ticket_client,
            database,
            runner,
            "/worktrees",
            config=config,
            username_self="allowed_user",
        )

        # Mock database to return stored state with a timestamp
        stored_state = Mock()
        stored_state.last_processed_comment_timestamp = "2024-01-14T10:00:00+00:00"
        stored_state.last_known_comment_count = 0
        database.get_issue_state.return_value = stored_state

        # Create a comment from the allowed user
        user_comment = Comment(
            id="IC_1",
            database_id=1,
            body="This is feedback",
            created_at=datetime(2024, 1, 15, 10, 0, 0),
            author="allowed_user",
            is_processed=False,
            is_processing=False,
        )

        ticket_client.get_comments_since.return_value = [user_comment]

        # Create a ticket item
        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
            comment_count=1,
        )

        response_comment = Comment(
            id="IC_2",
            database_id=456,
            body="response",
            created_at=datetime(2024, 1, 15, 12, 0, 0),
            author="test-user",
        )

        with (
            patch.object(processor, "_get_target_type", return_value="research"),
            patch.object(processor, "_extract_section_content", return_value="content"),
            patch.object(
                processor, "_ensure_worktree_exists", return_value="/worktrees/repo-issue-42"
            ),
            patch.object(processor, "_apply_comment_to_kiln_post"),
            patch.object(processor, "_generate_diff", return_value="-old\n+new"),
            patch("src.comment_processor.set_issue_context"),
            patch("src.comment_processor.clear_issue_context"),
            patch("src.comment_processor.send_comment_processed_notification") as mock_notify,
        ):
            ticket_client.add_comment.return_value = response_comment

            processor.process(item)

            # Verify Slack notification was NOT called
            mock_notify.assert_not_called()


@pytest.mark.unit
class TestCommentProcessorEditingLabelTracking:
    """Tests for EDITING label tracking in daemon's _running_labels."""

    def test_editing_label_tracked_when_daemon_provided(self):
        """Test that EDITING label is tracked in daemon's _running_labels when processing starts."""
        import threading

        ticket_client = Mock()
        database = Mock()
        runner = Mock()

        # Create a mock daemon with _running_labels infrastructure
        daemon = Mock()
        daemon._running_labels = {}
        daemon._running_labels_lock = threading.Lock()

        processor = CommentProcessor(
            ticket_client,
            database,
            runner,
            "/worktrees",
            config=_create_mock_config(),
            username_self="allowed_user",
            daemon=daemon,
        )

        # Mock database to return stored state with a timestamp
        stored_state = Mock()
        stored_state.last_processed_comment_timestamp = "2024-01-14T10:00:00+00:00"
        stored_state.last_known_comment_count = 0
        database.get_issue_state.return_value = stored_state

        # Create a comment from the allowed user
        user_comment = Comment(
            id="IC_1",
            database_id=1,
            body="This is feedback",
            created_at=datetime(2024, 1, 15, 10, 0, 0),
            author="allowed_user",
            is_processed=False,
            is_processing=False,
        )

        ticket_client.get_comments_since.return_value = [user_comment]

        # Create a ticket item
        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
            comment_count=1,
        )

        response_comment = Comment(
            id="IC_2",
            database_id=456,
            body="response",
            created_at=datetime(2024, 1, 15, 12, 0, 0),
            author="test-user",
        )

        # Track if EDITING label was in _running_labels during processing
        label_was_tracked = []

        def check_tracking(*args, **kwargs):
            key = f"{item.repo}#{item.ticket_id}"
            label_was_tracked.append(key in daemon._running_labels)

        with (
            patch.object(processor, "_get_target_type", return_value="research"),
            patch.object(processor, "_extract_section_content", return_value="content"),
            patch.object(
                processor, "_ensure_worktree_exists", return_value="/worktrees/repo-issue-42"
            ),
            patch.object(processor, "_apply_comment_to_kiln_post", side_effect=check_tracking),
            patch.object(processor, "_generate_diff", return_value="-old\n+new"),
            patch("src.comment_processor.set_issue_context"),
            patch("src.comment_processor.clear_issue_context"),
        ):
            ticket_client.add_comment.return_value = response_comment

            processor.process(item)

            # Verify EDITING label was tracked during processing
            assert len(label_was_tracked) == 1
            assert label_was_tracked[0] is True

            # Verify EDITING label is removed from tracking after processing
            key = f"{item.repo}#{item.ticket_id}"
            assert key not in daemon._running_labels

    def test_editing_label_removed_from_tracking_on_failure(self):
        """Test that EDITING label is removed from _running_labels even when processing fails."""
        import threading

        ticket_client = Mock()
        database = Mock()
        runner = Mock()

        # Create a mock daemon with _running_labels infrastructure
        daemon = Mock()
        daemon._running_labels = {}
        daemon._running_labels_lock = threading.Lock()

        processor = CommentProcessor(
            ticket_client,
            database,
            runner,
            "/worktrees",
            config=_create_mock_config(),
            username_self="allowed_user",
            daemon=daemon,
        )

        # Mock database to return stored state with a timestamp
        stored_state = Mock()
        stored_state.last_processed_comment_timestamp = "2024-01-14T10:00:00+00:00"
        stored_state.last_known_comment_count = 0
        database.get_issue_state.return_value = stored_state

        # Create a comment from the allowed user
        user_comment = Comment(
            id="IC_1",
            database_id=1,
            body="This is feedback",
            created_at=datetime(2024, 1, 15, 10, 0, 0),
            author="allowed_user",
            is_processed=False,
            is_processing=False,
        )

        ticket_client.get_comments_since.return_value = [user_comment]

        # Create a ticket item
        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
            comment_count=1,
        )

        with (
            patch.object(processor, "_get_target_type", return_value="research"),
            patch.object(processor, "_extract_section_content", return_value="content"),
            patch.object(
                processor, "_ensure_worktree_exists", return_value="/worktrees/repo-issue-42"
            ),
            patch.object(
                processor, "_apply_comment_to_kiln_post", side_effect=Exception("Processing failed")
            ),
            patch("src.comment_processor.set_issue_context"),
            patch("src.comment_processor.clear_issue_context"),
        ):
            processor.process(item)

            # Verify EDITING label is removed from tracking even after failure
            key = f"{item.repo}#{item.ticket_id}"
            assert key not in daemon._running_labels

    def test_no_error_when_daemon_not_provided(self):
        """Test that processing works normally when daemon is not provided."""
        ticket_client = Mock()
        database = Mock()
        runner = Mock()

        processor = CommentProcessor(
            ticket_client,
            database,
            runner,
            "/worktrees",
            config=_create_mock_config(),
            username_self="allowed_user",
            daemon=None,  # No daemon provided
        )

        # Mock database to return stored state with a timestamp
        stored_state = Mock()
        stored_state.last_processed_comment_timestamp = "2024-01-14T10:00:00+00:00"
        stored_state.last_known_comment_count = 0
        database.get_issue_state.return_value = stored_state

        # Create a comment from the allowed user
        user_comment = Comment(
            id="IC_1",
            database_id=1,
            body="This is feedback",
            created_at=datetime(2024, 1, 15, 10, 0, 0),
            author="allowed_user",
            is_processed=False,
            is_processing=False,
        )

        ticket_client.get_comments_since.return_value = [user_comment]

        # Create a ticket item
        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
            comment_count=1,
        )

        response_comment = Comment(
            id="IC_2",
            database_id=456,
            body="response",
            created_at=datetime(2024, 1, 15, 12, 0, 0),
            author="test-user",
        )

        with (
            patch.object(processor, "_get_target_type", return_value="research"),
            patch.object(processor, "_extract_section_content", return_value="content"),
            patch.object(
                processor, "_ensure_worktree_exists", return_value="/worktrees/repo-issue-42"
            ),
            patch.object(processor, "_apply_comment_to_kiln_post"),
            patch.object(processor, "_generate_diff", return_value="-old\n+new"),
            patch("src.comment_processor.set_issue_context"),
            patch("src.comment_processor.clear_issue_context"),
        ):
            ticket_client.add_comment.return_value = response_comment

            # Should not raise any exception
            processor.process(item)

            # Verify add_reaction was still called (normal processing happened)
            assert ticket_client.add_reaction.called

    def test_editing_label_value_in_running_labels(self):
        """Test that the EDITING label value is correctly stored in _running_labels."""
        import threading

        from src.labels import Labels

        ticket_client = Mock()
        database = Mock()
        runner = Mock()

        # Create a mock daemon with _running_labels infrastructure
        daemon = Mock()
        daemon._running_labels = {}
        daemon._running_labels_lock = threading.Lock()

        processor = CommentProcessor(
            ticket_client,
            database,
            runner,
            "/worktrees",
            config=_create_mock_config(),
            username_self="allowed_user",
            daemon=daemon,
        )

        # Mock database to return stored state with a timestamp
        stored_state = Mock()
        stored_state.last_processed_comment_timestamp = "2024-01-14T10:00:00+00:00"
        stored_state.last_known_comment_count = 0
        database.get_issue_state.return_value = stored_state

        # Create a comment from the allowed user
        user_comment = Comment(
            id="IC_1",
            database_id=1,
            body="This is feedback",
            created_at=datetime(2024, 1, 15, 10, 0, 0),
            author="allowed_user",
            is_processed=False,
            is_processing=False,
        )

        ticket_client.get_comments_since.return_value = [user_comment]

        # Create a ticket item
        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
            comment_count=1,
        )

        # Track the label value during processing
        label_value_captured = []

        def capture_label_value(*args, **kwargs):
            key = f"{item.repo}#{item.ticket_id}"
            if key in daemon._running_labels:
                label_value_captured.append(daemon._running_labels[key])

        with (
            patch.object(processor, "_get_target_type", return_value="research"),
            patch.object(processor, "_extract_section_content", return_value="content"),
            patch.object(
                processor, "_ensure_worktree_exists", return_value="/worktrees/repo-issue-42"
            ),
            patch.object(processor, "_apply_comment_to_kiln_post", side_effect=capture_label_value),
            patch("src.comment_processor.set_issue_context"),
            patch("src.comment_processor.clear_issue_context"),
        ):
            processor.process(item)

            # Verify the label value was Labels.EDITING
            assert len(label_value_captured) == 1
            assert label_value_captured[0] == Labels.EDITING


@pytest.mark.unit
class TestCommentProcessorStaleSessionHandling:
    """Tests for stale session handling when repo is relocated."""

    def test_stale_session_cleared_when_not_found(self):
        """Test that stale session IDs are cleared when session file doesn't exist."""
        ticket_client = Mock()
        database = Mock()
        runner = Mock()

        processor = CommentProcessor(
            ticket_client,
            database,
            runner,
            "/worktrees",
            config=_create_mock_config(),
            username_self="allowed_user",
        )

        # Mock database to return stored state with a session ID
        stored_state = Mock()
        stored_state.last_processed_comment_timestamp = "2024-01-14T10:00:00+00:00"
        stored_state.last_known_comment_count = 0
        database.get_issue_state.return_value = stored_state

        # Mock get_workflow_session_id to return a stale session ID
        stale_session_id = "stale-session-abc123"
        database.get_workflow_session_id.return_value = stale_session_id

        # Create a comment from the allowed user
        user_comment = Comment(
            id="IC_1",
            database_id=1,
            body="Apply this feedback",
            created_at=datetime(2024, 1, 15, 10, 0, 0),
            author="allowed_user",
            is_processed=False,
            is_processing=False,
        )

        ticket_client.get_comments_since.return_value = [user_comment]

        # Create a ticket item with Research status
        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
            comment_count=1,
        )

        response_comment = Comment(
            id="IC_2",
            database_id=456,
            body="response",
            created_at=datetime(2024, 1, 15, 12, 0, 0),
            author="test-user",
        )

        # Mock runner.run to return a new session ID
        runner.run.return_value = "new-session-after-stale"

        # Mock validate_session_exists to return False (session file not found)
        with (
            patch.object(processor, "_get_target_type", return_value="research"),
            patch.object(processor, "_extract_section_content", return_value="content"),
            patch.object(
                processor, "_ensure_worktree_exists", return_value="/worktrees/repo-issue-42"
            ),
            patch.object(processor, "_generate_diff", return_value="-old\n+new"),
            patch("src.comment_processor.set_issue_context"),
            patch("src.comment_processor.clear_issue_context"),
            patch("src.comment_processor.validate_session_exists", return_value=False),
        ):
            ticket_client.add_comment.return_value = response_comment

            processor.process(item)

            # Verify clear_workflow_session_id was called to clear the stale session
            database.clear_workflow_session_id.assert_called_once_with("owner/repo", 42, "Research")

    def test_valid_session_not_cleared(self):
        """Test that valid session IDs are NOT cleared when session file exists."""
        ticket_client = Mock()
        database = Mock()
        runner = Mock()

        processor = CommentProcessor(
            ticket_client,
            database,
            runner,
            "/worktrees",
            config=_create_mock_config(),
            username_self="allowed_user",
        )

        # Mock database to return stored state with a session ID
        stored_state = Mock()
        stored_state.last_processed_comment_timestamp = "2024-01-14T10:00:00+00:00"
        stored_state.last_known_comment_count = 0
        database.get_issue_state.return_value = stored_state

        # Mock get_workflow_session_id to return a valid session ID
        valid_session_id = "valid-session-xyz789"
        database.get_workflow_session_id.return_value = valid_session_id

        # Create a comment from the allowed user
        user_comment = Comment(
            id="IC_1",
            database_id=1,
            body="Apply this feedback",
            created_at=datetime(2024, 1, 15, 10, 0, 0),
            author="allowed_user",
            is_processed=False,
            is_processing=False,
        )

        ticket_client.get_comments_since.return_value = [user_comment]

        # Create a ticket item with Research status
        item = TicketItem(
            item_id="PVTI_123",
            board_url="https://github.com/orgs/test/projects/1",
            ticket_id=42,
            repo="owner/repo",
            status="Research",
            title="Test Issue",
            comment_count=1,
        )

        response_comment = Comment(
            id="IC_2",
            database_id=456,
            body="response",
            created_at=datetime(2024, 1, 15, 12, 0, 0),
            author="test-user",
        )

        # Mock runner.run to return a session ID
        runner.run.return_value = "returned-session-id"

        # Mock validate_session_exists to return True (session file exists)
        with (
            patch.object(processor, "_get_target_type", return_value="research"),
            patch.object(processor, "_extract_section_content", return_value="content"),
            patch.object(
                processor, "_ensure_worktree_exists", return_value="/worktrees/repo-issue-42"
            ),
            patch.object(processor, "_generate_diff", return_value="-old\n+new"),
            patch("src.comment_processor.set_issue_context"),
            patch("src.comment_processor.clear_issue_context"),
            patch("src.comment_processor.validate_session_exists", return_value=True),
        ):
            ticket_client.add_comment.return_value = response_comment

            processor.process(item)

            # Verify clear_workflow_session_id was NOT called
            database.clear_workflow_session_id.assert_not_called()
