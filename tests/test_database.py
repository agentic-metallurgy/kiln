"""Unit tests for the database module."""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from src.database import Database, IssueState


@pytest.fixture
def temp_db():
    """Fixture providing a temporary database for tests."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".db", delete=False) as f:
        db_path = f.name

    # Create and yield the database
    db = Database(db_path)
    yield db

    # Cleanup
    db.close()
    Path(db_path).unlink(missing_ok=True)


@pytest.mark.unit
class TestDatabase:
    """Tests for Database class."""

    def test_database_creation_and_initialization(self, temp_db):
        """Test that Database creates and initializes correctly."""
        assert temp_db.conn is not None
        assert Path(temp_db.db_path).exists()

        # Verify table was created
        cursor = temp_db.conn.cursor()
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='issue_states'
        """)
        result = cursor.fetchone()
        assert result is not None
        assert result["name"] == "issue_states"

    def test_database_table_schema(self, temp_db):
        """Test that the issue_states table has the correct schema."""
        cursor = temp_db.conn.cursor()
        cursor.execute("PRAGMA table_info(issue_states)")
        columns = {row["name"]: row for row in cursor.fetchall()}

        assert "repo" in columns
        assert "issue_number" in columns
        assert "status" in columns
        assert "last_updated" in columns

        # Check primary key constraint
        cursor.execute("""
            SELECT sql FROM sqlite_master
            WHERE type='table' AND name='issue_states'
        """)
        schema = cursor.fetchone()["sql"]
        assert "PRIMARY KEY (repo, issue_number)" in schema

    def test_update_issue_state_new_issue(self, temp_db):
        """Test updating state for a new issue."""
        temp_db.update_issue_state("owner/repo", 123, "Research")

        # Verify the issue was inserted
        cursor = temp_db.conn.cursor()
        cursor.execute(
            "SELECT * FROM issue_states WHERE repo = ? AND issue_number = ?", ("owner/repo", 123)
        )
        row = cursor.fetchone()

        assert row is not None
        assert row["repo"] == "owner/repo"
        assert row["issue_number"] == 123
        assert row["status"] == "Research"
        assert row["last_updated"] is not None

    def test_update_issue_state_existing_issue(self, temp_db):
        """Test updating state for an existing issue."""
        # Insert initial state
        temp_db.update_issue_state("owner/repo", 456, "Research")

        # Update to new state
        temp_db.update_issue_state("owner/repo", 456, "Plan")

        # Verify the issue was updated (not duplicated)
        cursor = temp_db.conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) as count FROM issue_states WHERE repo = ? AND issue_number = ?",
            ("owner/repo", 456),
        )
        count = cursor.fetchone()["count"]
        assert count == 1

        # Verify status was updated
        cursor.execute(
            "SELECT status FROM issue_states WHERE repo = ? AND issue_number = ?",
            ("owner/repo", 456),
        )
        status = cursor.fetchone()["status"]
        assert status == "Plan"

    def test_get_issue_state_exists(self, temp_db):
        """Test retrieving state for an existing issue."""
        temp_db.update_issue_state("owner/repo", 789, "Implement")

        issue_state = temp_db.get_issue_state("owner/repo", 789)

        assert issue_state is not None
        assert isinstance(issue_state, IssueState)
        assert issue_state.repo == "owner/repo"
        assert issue_state.issue_number == 789
        assert issue_state.status == "Implement"
        assert isinstance(issue_state.last_updated, datetime)

    def test_get_issue_state_not_exists(self, temp_db):
        """Test retrieving state for a non-existent issue returns None."""
        issue_state = temp_db.get_issue_state("owner/repo", 999)
        assert issue_state is None

    def test_get_issue_state_different_repos(self, temp_db):
        """Test that issues from different repos are kept separate."""
        temp_db.update_issue_state("owner/repo1", 100, "Research")
        temp_db.update_issue_state("owner/repo2", 100, "Plan")

        state1 = temp_db.get_issue_state("owner/repo1", 100)
        state2 = temp_db.get_issue_state("owner/repo2", 100)

        assert state1 is not None
        assert state2 is not None
        assert state1.status == "Research"
        assert state2.status == "Plan"

    def test_context_manager_support(self):
        """Test Database can be used as a context manager."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            with Database(db_path) as db:
                assert db.conn is not None
                db.update_issue_state("owner/repo", 1, "Research")
            # Context manager closes connection, but per-thread design
            # creates new connection on next access (expected behavior)
        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_close_closes_connection(self, temp_db):
        """Test that close() closes the current thread's connection."""
        conn_before = temp_db.conn
        temp_db.close()
        # Per-thread design: accessing conn after close creates new connection
        conn_after = temp_db.conn
        assert conn_before is not conn_after

    def test_operations_work_after_close(self, temp_db):
        """Test that operations work after close (per-thread reconnection)."""
        temp_db.update_issue_state("owner/repo", 1, "Research")
        temp_db.close()

        # Operations should work - they get a new connection
        state = temp_db.get_issue_state("owner/repo", 1)
        assert state is not None
        assert state.status == "Research"

    def test_timestamp_format_is_iso(self, temp_db):
        """Test that timestamps are stored in ISO format."""
        temp_db.update_issue_state("owner/repo", 1, "Research")

        # Check raw database value
        cursor = temp_db.conn.cursor()
        cursor.execute(
            "SELECT last_updated FROM issue_states WHERE repo = ? AND issue_number = ?",
            ("owner/repo", 1),
        )
        raw_timestamp = cursor.fetchone()["last_updated"]

        # Should be able to parse as ISO format
        parsed = datetime.fromisoformat(raw_timestamp)
        assert isinstance(parsed, datetime)

    def test_update_issue_state_updates_timestamp(self, temp_db):
        """Test that updating an issue also updates the timestamp."""
        import time

        temp_db.update_issue_state("owner/repo", 1, "Research")
        first_state = temp_db.get_issue_state("owner/repo", 1)

        time.sleep(0.01)
        temp_db.update_issue_state("owner/repo", 1, "Plan")
        second_state = temp_db.get_issue_state("owner/repo", 1)

        assert second_state.last_updated > first_state.last_updated
        assert second_state.status == "Plan"

    def test_get_all_issue_states_returns_all(self, temp_db):
        """Test that get_all_issue_states returns all tracked issues."""
        temp_db.update_issue_state("github.com/owner/repo1", 1, "Research")
        temp_db.update_issue_state("github.com/owner/repo2", 2, "Plan")
        temp_db.update_issue_state("github.com/owner/repo1", 3, "Implement")

        states = temp_db.get_all_issue_states()
        assert len(states) == 3

    def test_get_all_issue_states_ordered_by_last_updated(self, temp_db):
        """Test that get_all_issue_states returns issues ordered by last_updated DESC."""
        import time

        temp_db.update_issue_state("github.com/owner/repo", 1, "Research")
        time.sleep(0.01)
        temp_db.update_issue_state("github.com/owner/repo", 2, "Plan")
        time.sleep(0.01)
        temp_db.update_issue_state("github.com/owner/repo", 3, "Implement")

        states = temp_db.get_all_issue_states()
        assert len(states) == 3
        # Most recently updated should be first
        assert states[0].issue_number == 3
        assert states[1].issue_number == 2
        assert states[2].issue_number == 1

    def test_get_all_issue_states_respects_limit(self, temp_db):
        """Test that get_all_issue_states respects the limit parameter."""
        for i in range(5):
            temp_db.update_issue_state("github.com/owner/repo", i, "Research")

        states = temp_db.get_all_issue_states(limit=2)
        assert len(states) == 2

    def test_get_all_issue_states_empty_database(self, temp_db):
        """Test that get_all_issue_states returns empty list for empty database."""
        states = temp_db.get_all_issue_states()
        assert states == []


@pytest.mark.unit
class TestIssueState:
    """Tests for IssueState dataclass."""

    def test_issue_state_creation(self):
        """Test creating an IssueState instance."""
        timestamp = datetime.now()
        issue_state = IssueState(
            repo="owner/repo", issue_number=123, status="Research", last_updated=timestamp
        )

        assert issue_state.repo == "owner/repo"
        assert issue_state.issue_number == 123
        assert issue_state.status == "Research"
        assert issue_state.last_updated == timestamp


@pytest.mark.unit
class TestCommentTimestampTracking:
    """Tests for last_processed_comment_timestamp tracking."""

    def test_update_issue_with_timestamp(self, temp_db):
        """Test storing a comment timestamp with issue state."""
        timestamp = "2024-01-15T10:30:00+00:00"
        temp_db.update_issue_state(
            "owner/repo", 42, "Research", last_processed_comment_timestamp=timestamp
        )

        state = temp_db.get_issue_state("owner/repo", 42)
        assert state is not None
        assert state.last_processed_comment_timestamp == timestamp

    def test_timestamp_preserved_on_status_update(self, temp_db):
        """Test that timestamp is preserved when status changes but timestamp not provided."""
        timestamp = "2024-01-15T10:30:00+00:00"
        temp_db.update_issue_state(
            "owner/repo", 42, "Research", last_processed_comment_timestamp=timestamp
        )

        # Update status without providing timestamp
        temp_db.update_issue_state("owner/repo", 42, "Plan")

        state = temp_db.get_issue_state("owner/repo", 42)
        assert state.status == "Plan"
        assert state.last_processed_comment_timestamp == timestamp

    def test_timestamp_updated_when_provided(self, temp_db):
        """Test that timestamp is updated when a new one is provided."""
        old_timestamp = "2024-01-15T10:30:00+00:00"
        new_timestamp = "2024-01-15T11:45:00+00:00"

        temp_db.update_issue_state(
            "owner/repo", 42, "Research", last_processed_comment_timestamp=old_timestamp
        )
        temp_db.update_issue_state(
            "owner/repo", 42, "Research", last_processed_comment_timestamp=new_timestamp
        )

        state = temp_db.get_issue_state("owner/repo", 42)
        assert state.last_processed_comment_timestamp == new_timestamp

    def test_timestamp_format_is_iso8601(self, temp_db):
        """Test that timestamps are stored in ISO 8601 format."""
        # Various valid ISO 8601 formats
        timestamps = [
            "2024-01-15T10:30:00Z",
            "2024-01-15T10:30:00+00:00",
            "2024-01-15T10:30:00.123456+00:00",
        ]

        for i, ts in enumerate(timestamps):
            temp_db.update_issue_state(
                "owner/repo", i, "Research", last_processed_comment_timestamp=ts
            )
            state = temp_db.get_issue_state("owner/repo", i)
            assert state.last_processed_comment_timestamp == ts

    def test_null_timestamp_for_new_issue(self, temp_db):
        """Test that new issues have null timestamp."""
        temp_db.update_issue_state("owner/repo", 42, "Research")

        state = temp_db.get_issue_state("owner/repo", 42)
        assert state.last_processed_comment_timestamp is None


@pytest.mark.unit
class TestProcessingCommentsTracking:
    """Tests for processing_comments table and methods."""

    def test_processing_comments_table_created(self, temp_db):
        """Test that processing_comments table is created on init."""
        cursor = temp_db.conn.cursor()
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='processing_comments'
        """)
        result = cursor.fetchone()
        assert result is not None
        assert result["name"] == "processing_comments"

    def test_processing_comments_table_schema(self, temp_db):
        """Test that processing_comments table has correct schema."""
        cursor = temp_db.conn.cursor()
        cursor.execute("PRAGMA table_info(processing_comments)")
        columns = {row["name"]: row for row in cursor.fetchall()}

        assert "repo" in columns
        assert "issue_number" in columns
        assert "comment_id" in columns
        assert "started_at" in columns

        # Check primary key constraint
        cursor.execute("""
            SELECT sql FROM sqlite_master
            WHERE type='table' AND name='processing_comments'
        """)
        schema = cursor.fetchone()["sql"]
        assert "PRIMARY KEY (repo, issue_number, comment_id)" in schema

    def test_add_processing_comment(self, temp_db):
        """Test adding a comment to processing tracking."""
        temp_db.add_processing_comment("github.com/owner/repo", 42, "IC_abc123")

        cursor = temp_db.conn.cursor()
        cursor.execute(
            "SELECT * FROM processing_comments WHERE repo = ? AND issue_number = ? AND comment_id = ?",
            ("github.com/owner/repo", 42, "IC_abc123"),
        )
        row = cursor.fetchone()

        assert row is not None
        assert row["repo"] == "github.com/owner/repo"
        assert row["issue_number"] == 42
        assert row["comment_id"] == "IC_abc123"
        assert row["started_at"] is not None

    def test_add_processing_comment_replaces_existing(self, temp_db):
        """Test that adding same comment updates timestamp."""
        import time

        temp_db.add_processing_comment("github.com/owner/repo", 42, "IC_abc123")

        cursor = temp_db.conn.cursor()
        cursor.execute(
            "SELECT started_at FROM processing_comments WHERE comment_id = ?",
            ("IC_abc123",),
        )
        first_timestamp = cursor.fetchone()["started_at"]

        time.sleep(0.01)
        temp_db.add_processing_comment("github.com/owner/repo", 42, "IC_abc123")

        cursor.execute(
            "SELECT started_at FROM processing_comments WHERE comment_id = ?",
            ("IC_abc123",),
        )
        second_timestamp = cursor.fetchone()["started_at"]

        assert second_timestamp > first_timestamp

        # Should still be only one record
        cursor.execute(
            "SELECT COUNT(*) as count FROM processing_comments WHERE comment_id = ?",
            ("IC_abc123",),
        )
        assert cursor.fetchone()["count"] == 1

    def test_remove_processing_comment(self, temp_db):
        """Test removing a comment from processing tracking."""
        temp_db.add_processing_comment("github.com/owner/repo", 42, "IC_abc123")
        temp_db.remove_processing_comment("github.com/owner/repo", 42, "IC_abc123")

        cursor = temp_db.conn.cursor()
        cursor.execute(
            "SELECT * FROM processing_comments WHERE comment_id = ?",
            ("IC_abc123",),
        )
        assert cursor.fetchone() is None

    def test_remove_processing_comment_nonexistent(self, temp_db):
        """Test removing a non-existent comment doesn't error."""
        # Should not raise any exception
        temp_db.remove_processing_comment("github.com/owner/repo", 42, "IC_nonexistent")

    def test_get_stale_processing_comments_returns_stale(self, temp_db):
        """Test that stale comments are returned."""
        # Insert a comment with an old timestamp directly
        conn = temp_db.conn
        with conn:
            # 2 hours ago
            old_time = datetime.fromtimestamp(datetime.now().timestamp() - 7200)
            conn.execute(
                """
                INSERT INTO processing_comments (repo, issue_number, comment_id, started_at)
                VALUES (?, ?, ?, ?)
                """,
                ("github.com/owner/repo", 42, "IC_stale", old_time.isoformat()),
            )

        stale = temp_db.get_stale_processing_comments(stale_threshold_seconds=3600)
        assert len(stale) == 1
        assert stale[0] == ("github.com/owner/repo", 42, "IC_stale")

    def test_get_stale_processing_comments_excludes_fresh(self, temp_db):
        """Test that fresh comments are not returned."""
        temp_db.add_processing_comment("github.com/owner/repo", 42, "IC_fresh")

        stale = temp_db.get_stale_processing_comments(stale_threshold_seconds=3600)
        assert len(stale) == 0

    def test_get_stale_processing_comments_custom_threshold(self, temp_db):
        """Test custom threshold for staleness."""
        import time

        temp_db.add_processing_comment("github.com/owner/repo", 42, "IC_test")
        time.sleep(0.1)

        # With very short threshold, comment should be stale
        stale = temp_db.get_stale_processing_comments(stale_threshold_seconds=0)
        assert len(stale) == 1
        assert stale[0][2] == "IC_test"

    def test_get_stale_processing_comments_multiple(self, temp_db):
        """Test getting multiple stale comments."""
        conn = temp_db.conn
        with conn:
            old_time = datetime.fromtimestamp(datetime.now().timestamp() - 7200)
            for i in range(3):
                conn.execute(
                    """
                    INSERT INTO processing_comments (repo, issue_number, comment_id, started_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    ("github.com/owner/repo", i, f"IC_stale_{i}", old_time.isoformat()),
                )

        stale = temp_db.get_stale_processing_comments(stale_threshold_seconds=3600)
        assert len(stale) == 3

    def test_processing_comments_different_issues(self, temp_db):
        """Test that processing comments are tracked per issue."""
        temp_db.add_processing_comment("github.com/owner/repo", 42, "IC_abc123")
        temp_db.add_processing_comment("github.com/owner/repo", 43, "IC_def456")

        cursor = temp_db.conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM processing_comments")
        assert cursor.fetchone()["count"] == 2

        # Remove one, other should remain
        temp_db.remove_processing_comment("github.com/owner/repo", 42, "IC_abc123")

        cursor.execute("SELECT * FROM processing_comments")
        row = cursor.fetchone()
        assert row["comment_id"] == "IC_def456"


@pytest.mark.unit
class TestClearWorkflowSessionId:
    """Tests for clearing workflow session IDs."""

    def test_clear_workflow_session_id(self, temp_db):
        """Test that clear_workflow_session_id clears a stored session ID."""
        # Set up issue with a session ID
        temp_db.update_issue_state("owner/repo", 42, "Research", research_session_id="abc123")
        state = temp_db.get_issue_state("owner/repo", 42)
        assert state.research_session_id == "abc123"

        # Clear the session ID
        temp_db.clear_workflow_session_id("owner/repo", 42, "Research")

        # Verify it's cleared (empty string is stored, but get returns it as is)
        state = temp_db.get_issue_state("owner/repo", 42)
        assert state.research_session_id == ""

    def test_clear_workflow_session_id_preserves_other_fields(self, temp_db):
        """Test that clearing session ID doesn't affect other fields."""
        temp_db.update_issue_state(
            "owner/repo",
            42,
            "Plan",
            branch_name="issue-42",
            research_session_id="research-123",
            plan_session_id="plan-456",
        )

        # Clear only the plan session
        temp_db.clear_workflow_session_id("owner/repo", 42, "Plan")

        state = temp_db.get_issue_state("owner/repo", 42)
        assert state.status == "Plan"
        assert state.branch_name == "issue-42"
        assert state.research_session_id == "research-123"
        assert state.plan_session_id == ""

    def test_clear_workflow_session_id_for_implement(self, temp_db):
        """Test clearing implement workflow session ID."""
        temp_db.update_issue_state("owner/repo", 42, "Implement", implement_session_id="impl-789")

        temp_db.clear_workflow_session_id("owner/repo", 42, "Implement")

        state = temp_db.get_issue_state("owner/repo", 42)
        assert state.implement_session_id == ""

    def test_clear_workflow_session_id_nonexistent_issue(self, temp_db):
        """Test that clearing session ID for non-existent issue is a no-op."""
        # Should not raise an error
        temp_db.clear_workflow_session_id("owner/repo", 999, "Research")
