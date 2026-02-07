"""Unit and integration tests for run logging functionality.

Tests for:
- RunRecord dataclass and database CRUD operations
- CLI logs command parsing and execution
- Integration of RunLogger with daemon workflow execution
"""

import argparse
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.database import Database, RunRecord


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
class TestRunRecord:
    """Tests for RunRecord dataclass."""

    def test_run_record_creation(self):
        """Test creating a RunRecord instance."""
        now = datetime.now()
        record = RunRecord(
            repo="github.com/owner/repo",
            issue_number=42,
            workflow="Research",
            started_at=now,
        )

        assert record.repo == "github.com/owner/repo"
        assert record.issue_number == 42
        assert record.workflow == "Research"
        assert record.started_at == now
        assert record.id is None
        assert record.completed_at is None
        assert record.outcome is None
        assert record.session_id is None
        assert record.log_path is None

    def test_run_record_with_all_fields(self):
        """Test creating a RunRecord with all optional fields."""
        started = datetime.now()
        completed = started + timedelta(minutes=5)
        record = RunRecord(
            repo="github.com/owner/repo",
            issue_number=123,
            workflow="Implement",
            started_at=started,
            id=1,
            completed_at=completed,
            outcome="success",
            session_id="abc-123-xyz",
            log_path=".kiln/logs/github.com/owner/repo/123/implement-20240115-1430.log",
        )

        assert record.id == 1
        assert record.completed_at == completed
        assert record.outcome == "success"
        assert record.session_id == "abc-123-xyz"
        assert record.log_path is not None

    def test_run_record_equality(self):
        """Test RunRecord equality comparison."""
        now = datetime.now()
        record1 = RunRecord(
            repo="github.com/owner/repo",
            issue_number=42,
            workflow="Research",
            started_at=now,
        )
        record2 = RunRecord(
            repo="github.com/owner/repo",
            issue_number=42,
            workflow="Research",
            started_at=now,
        )

        assert record1 == record2


@pytest.mark.unit
class TestRunRecordDatabase:
    """Tests for RunRecord database operations."""

    def test_insert_run_record(self, temp_db):
        """Test inserting a new run record."""
        record = RunRecord(
            repo="github.com/owner/repo",
            issue_number=42,
            workflow="Research",
            started_at=datetime.now(),
        )

        run_id = temp_db.insert_run_record(record)

        assert run_id is not None
        assert run_id > 0

    def test_insert_run_record_auto_increments_id(self, temp_db):
        """Test that run record IDs auto-increment."""
        records = []
        for _ in range(3):
            record = RunRecord(
                repo="github.com/owner/repo",
                issue_number=42,
                workflow="Research",
                started_at=datetime.now(),
            )
            records.append(temp_db.insert_run_record(record))

        assert records == [1, 2, 3]

    def test_get_run_record(self, temp_db):
        """Test retrieving a single run record by ID."""
        now = datetime.now()
        record = RunRecord(
            repo="github.com/owner/repo",
            issue_number=42,
            workflow="Plan",
            started_at=now,
        )
        run_id = temp_db.insert_run_record(record)

        retrieved = temp_db.get_run_record(run_id)

        assert retrieved is not None
        assert retrieved.id == run_id
        assert retrieved.repo == "github.com/owner/repo"
        assert retrieved.issue_number == 42
        assert retrieved.workflow == "Plan"

    def test_get_run_record_not_found(self, temp_db):
        """Test retrieving a non-existent run record returns None."""
        result = temp_db.get_run_record(999)
        assert result is None

    def test_update_run_record_completed_at(self, temp_db):
        """Test updating a run record with completion timestamp."""
        record = RunRecord(
            repo="github.com/owner/repo",
            issue_number=42,
            workflow="Research",
            started_at=datetime.now(),
        )
        run_id = temp_db.insert_run_record(record)

        completed_at = datetime.now()
        temp_db.update_run_record(run_id, completed_at=completed_at)

        updated = temp_db.get_run_record(run_id)
        assert updated.completed_at is not None

    def test_update_run_record_outcome(self, temp_db):
        """Test updating a run record with outcome."""
        record = RunRecord(
            repo="github.com/owner/repo",
            issue_number=42,
            workflow="Research",
            started_at=datetime.now(),
        )
        run_id = temp_db.insert_run_record(record)

        temp_db.update_run_record(run_id, outcome="success")

        updated = temp_db.get_run_record(run_id)
        assert updated.outcome == "success"

    def test_update_run_record_session_id(self, temp_db):
        """Test updating a run record with session ID."""
        record = RunRecord(
            repo="github.com/owner/repo",
            issue_number=42,
            workflow="Research",
            started_at=datetime.now(),
        )
        run_id = temp_db.insert_run_record(record)

        temp_db.update_run_record(run_id, session_id="session-abc-123")

        updated = temp_db.get_run_record(run_id)
        assert updated.session_id == "session-abc-123"

    def test_update_run_record_log_path(self, temp_db):
        """Test updating a run record with log path."""
        record = RunRecord(
            repo="github.com/owner/repo",
            issue_number=42,
            workflow="Research",
            started_at=datetime.now(),
        )
        run_id = temp_db.insert_run_record(record)

        log_path = ".kiln/logs/github.com/owner/repo/42/research-20240115-1430.log"
        temp_db.update_run_record(run_id, log_path=log_path)

        updated = temp_db.get_run_record(run_id)
        assert updated.log_path == log_path

    def test_update_run_record_multiple_fields(self, temp_db):
        """Test updating multiple fields at once."""
        record = RunRecord(
            repo="github.com/owner/repo",
            issue_number=42,
            workflow="Research",
            started_at=datetime.now(),
        )
        run_id = temp_db.insert_run_record(record)

        completed_at = datetime.now()
        temp_db.update_run_record(
            run_id,
            completed_at=completed_at,
            outcome="failed",
            session_id="session-xyz",
        )

        updated = temp_db.get_run_record(run_id)
        assert updated.completed_at is not None
        assert updated.outcome == "failed"
        assert updated.session_id == "session-xyz"

    def test_update_run_record_no_changes(self, temp_db):
        """Test that update with no fields does nothing."""
        record = RunRecord(
            repo="github.com/owner/repo",
            issue_number=42,
            workflow="Research",
            started_at=datetime.now(),
        )
        run_id = temp_db.insert_run_record(record)

        # Update with no fields - should not error
        temp_db.update_run_record(run_id)

        updated = temp_db.get_run_record(run_id)
        assert updated.outcome is None

    def test_get_run_history(self, temp_db):
        """Test retrieving run history for an issue."""
        # Insert multiple runs for the same issue
        for workflow in ["Research", "Plan", "Implement"]:
            record = RunRecord(
                repo="github.com/owner/repo",
                issue_number=42,
                workflow=workflow,
                started_at=datetime.now(),
            )
            temp_db.insert_run_record(record)

        history = temp_db.get_run_history("github.com/owner/repo", 42)

        assert len(history) == 3
        # Should be ordered by started_at descending (newest first)
        assert history[0].workflow == "Implement"
        assert history[1].workflow == "Plan"
        assert history[2].workflow == "Research"

    def test_get_run_history_different_issues(self, temp_db):
        """Test that run history is filtered by issue."""
        # Insert runs for different issues
        for issue_num in [42, 43]:
            record = RunRecord(
                repo="github.com/owner/repo",
                issue_number=issue_num,
                workflow="Research",
                started_at=datetime.now(),
            )
            temp_db.insert_run_record(record)

        history_42 = temp_db.get_run_history("github.com/owner/repo", 42)
        history_43 = temp_db.get_run_history("github.com/owner/repo", 43)

        assert len(history_42) == 1
        assert len(history_43) == 1
        assert history_42[0].issue_number == 42
        assert history_43[0].issue_number == 43

    def test_get_run_history_different_repos(self, temp_db):
        """Test that run history is filtered by repo."""
        for repo in ["github.com/owner/repo1", "github.com/owner/repo2"]:
            record = RunRecord(
                repo=repo,
                issue_number=42,
                workflow="Research",
                started_at=datetime.now(),
            )
            temp_db.insert_run_record(record)

        history_1 = temp_db.get_run_history("github.com/owner/repo1", 42)
        history_2 = temp_db.get_run_history("github.com/owner/repo2", 42)

        assert len(history_1) == 1
        assert len(history_2) == 1

    def test_get_run_history_empty(self, temp_db):
        """Test that empty history returns empty list."""
        history = temp_db.get_run_history("github.com/owner/nonexistent", 999)
        assert history == []

    def test_get_run_history_with_limit(self, temp_db):
        """Test that limit parameter works."""
        # Insert 10 runs
        for _ in range(10):
            record = RunRecord(
                repo="github.com/owner/repo",
                issue_number=42,
                workflow="Research",
                started_at=datetime.now(),
            )
            temp_db.insert_run_record(record)

        history = temp_db.get_run_history("github.com/owner/repo", 42, limit=5)

        assert len(history) == 5

    def test_run_history_table_created(self, temp_db):
        """Test that run_history table is created during init."""
        cursor = temp_db.conn.cursor()
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='run_history'
        """)
        result = cursor.fetchone()
        assert result is not None
        assert result["name"] == "run_history"

    def test_run_history_index_created(self, temp_db):
        """Test that index on repo/issue is created."""
        cursor = temp_db.conn.cursor()
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='index' AND name='idx_run_history_repo_issue'
        """)
        result = cursor.fetchone()
        assert result is not None


@pytest.mark.unit
class TestDetermineState:
    """Tests for _determine_state helper function."""

    def test_determine_state_running_label_first(self):
        """Test that running labels take priority."""
        from src.cli import _determine_state

        labels = {"implementing", "plan_ready"}
        state = _determine_state(labels, "Plan")
        assert state == "implementing"

    def test_determine_state_failure_label(self):
        """Test that failure labels are recognized."""
        from src.cli import _determine_state

        labels = {"implementation_failed"}
        state = _determine_state(labels, "Implement")
        assert state == "implementation_failed"

    def test_determine_state_complete_label(self):
        """Test that completion labels are recognized."""
        from src.cli import _determine_state

        labels = {"research_ready"}
        state = _determine_state(labels, "Research")
        assert state == "research_ready"

    def test_determine_state_fallback_to_board_status(self):
        """Test fallback to board status when no matching labels."""
        from src.cli import _determine_state

        labels = {"some_other_label"}
        state = _determine_state(labels, "Plan")
        assert state == "plan"

    def test_determine_state_empty_labels(self):
        """Test fallback when no labels."""
        from src.cli import _determine_state

        labels = set()
        state = _determine_state(labels, "Research")
        assert state == "research"

    def test_determine_state_priority_order(self):
        """Test that running labels take priority over failure labels."""
        from src.cli import _determine_state

        # 'researching' should take priority over 'implementation_failed'
        labels = {"researching", "implementation_failed", "research_ready"}
        state = _determine_state(labels, "Validate")
        assert state == "researching"


@pytest.mark.unit
class TestCmdLogsSummary:
    """Tests for cmd_logs_summary function."""

    def test_cmd_logs_summary_no_issues(self, tmp_path, capsys):
        """Test summary view when no issues exist."""
        from src.cli import cmd_logs_summary

        # Create empty database
        db_path = tmp_path / "test.db"
        db = Database(str(db_path))

        with patch("src.config.load_config") as mock_config:
            mock_config.return_value = MagicMock(
                github_token="fake-token",
                github_enterprise_host=None,
                github_enterprise_token=None,
                github_enterprise_version=None,
            )
            cmd_logs_summary(db)

        db.close()
        captured = capsys.readouterr()
        assert "No tracked issues found." in captured.out

    def test_cmd_logs_summary_displays_table(self, tmp_path, capsys):
        """Test summary view displays table with correct columns."""
        from src.cli import cmd_logs_summary
        from src.interfaces.ticket import LinkedPullRequest

        # Create database with test data
        db_path = tmp_path / "test.db"
        db = Database(str(db_path))
        db.update_issue_state("github.com/owner/repo", 42, "Research")

        # Mock GitHub client
        mock_client = MagicMock()
        mock_client.get_ticket_labels.return_value = {"researching"}
        mock_client.get_linked_prs.return_value = [
            LinkedPullRequest(
                number=100,
                url="https://github.com/owner/repo/pull/100",
                body="PR body",
                state="OPEN",
                merged=False,
                branch_name="42-feature",
                title="Add feature",
            )
        ]

        with (
            patch("src.config.load_config") as mock_config,
            patch("src.ticket_clients.get_github_client", return_value=mock_client),
        ):
            mock_config.return_value = MagicMock(
                github_token="fake-token",
                github_enterprise_host=None,
                github_enterprise_token=None,
                github_enterprise_version=None,
            )
            cmd_logs_summary(db)

        db.close()
        captured = capsys.readouterr()

        # Check header
        assert "Identifier" in captured.out
        assert "Branch" in captured.out
        assert "PR" in captured.out
        assert "State" in captured.out

        # Check data row
        assert "owner/repo#42" in captured.out
        assert "42-feature" in captured.out
        assert "#100: Add feature" in captured.out
        assert "researching" in captured.out

    def test_cmd_logs_summary_yolo_indicator(self, tmp_path, capsys):
        """Test that yolo label is displayed with state."""
        from src.cli import cmd_logs_summary

        db_path = tmp_path / "test.db"
        db = Database(str(db_path))
        db.update_issue_state("github.com/owner/repo", 42, "Implement")

        mock_client = MagicMock()
        mock_client.get_ticket_labels.return_value = {"implementing", "yolo"}
        mock_client.get_linked_prs.return_value = []

        with (
            patch("src.config.load_config") as mock_config,
            patch("src.ticket_clients.get_github_client", return_value=mock_client),
        ):
            mock_config.return_value = MagicMock(
                github_token="fake-token",
                github_enterprise_host=None,
                github_enterprise_token=None,
                github_enterprise_version=None,
            )
            cmd_logs_summary(db)

        db.close()
        captured = capsys.readouterr()
        assert "implementing (yolo)" in captured.out

    def test_cmd_logs_summary_no_pr(self, tmp_path, capsys):
        """Test summary view when issue has no linked PR."""
        from src.cli import cmd_logs_summary

        db_path = tmp_path / "test.db"
        db = Database(str(db_path))
        db.update_issue_state("github.com/owner/repo", 42, "Research")

        mock_client = MagicMock()
        mock_client.get_ticket_labels.return_value = set()
        mock_client.get_linked_prs.return_value = []

        with (
            patch("src.config.load_config") as mock_config,
            patch("src.ticket_clients.get_github_client", return_value=mock_client),
        ):
            mock_config.return_value = MagicMock(
                github_token="fake-token",
                github_enterprise_host=None,
                github_enterprise_token=None,
                github_enterprise_version=None,
            )
            cmd_logs_summary(db)

        db.close()
        captured = capsys.readouterr()
        # Branch and PR should show "-" when not available
        lines = captured.out.split("\n")
        data_line = [line for line in lines if "owner/repo#42" in line][0]
        assert data_line.count("-") >= 2  # At least branch and PR are "-"

    def test_cmd_logs_summary_truncates_long_branch(self, tmp_path, capsys):
        """Test that long branch names are truncated."""
        from src.cli import cmd_logs_summary
        from src.interfaces.ticket import LinkedPullRequest

        db_path = tmp_path / "test.db"
        db = Database(str(db_path))
        db.update_issue_state("github.com/owner/repo", 42, "Research")

        long_branch = "a" * 40  # Longer than 30 chars
        mock_client = MagicMock()
        mock_client.get_ticket_labels.return_value = set()
        mock_client.get_linked_prs.return_value = [
            LinkedPullRequest(
                number=100,
                url="https://github.com/owner/repo/pull/100",
                body="",
                state="OPEN",
                merged=False,
                branch_name=long_branch,
                title="Test",
            )
        ]

        with (
            patch("src.config.load_config") as mock_config,
            patch("src.ticket_clients.get_github_client", return_value=mock_client),
        ):
            mock_config.return_value = MagicMock(
                github_token="fake-token",
                github_enterprise_host=None,
                github_enterprise_token=None,
                github_enterprise_version=None,
            )
            cmd_logs_summary(db)

        db.close()
        captured = capsys.readouterr()
        # Branch should be truncated with "..."
        assert "aaa..." in captured.out

    def test_cmd_logs_summary_truncates_long_title(self, tmp_path, capsys):
        """Test that long PR titles are truncated."""
        from src.cli import cmd_logs_summary
        from src.interfaces.ticket import LinkedPullRequest

        db_path = tmp_path / "test.db"
        db = Database(str(db_path))
        db.update_issue_state("github.com/owner/repo", 42, "Research")

        long_title = "This is a very long PR title that exceeds the limit"
        mock_client = MagicMock()
        mock_client.get_ticket_labels.return_value = set()
        mock_client.get_linked_prs.return_value = [
            LinkedPullRequest(
                number=100,
                url="https://github.com/owner/repo/pull/100",
                body="",
                state="OPEN",
                merged=False,
                branch_name="feature",
                title=long_title,
            )
        ]

        with (
            patch("src.config.load_config") as mock_config,
            patch("src.ticket_clients.get_github_client", return_value=mock_client),
        ):
            mock_config.return_value = MagicMock(
                github_token="fake-token",
                github_enterprise_host=None,
                github_enterprise_token=None,
                github_enterprise_version=None,
            )
            cmd_logs_summary(db)

        db.close()
        captured = capsys.readouterr()
        # Title should be truncated with "..."
        assert "#100: This is a very long ..." in captured.out

    def test_cmd_logs_summary_multiple_issues(self, tmp_path, capsys):
        """Test summary view with multiple issues."""
        from src.cli import cmd_logs_summary

        db_path = tmp_path / "test.db"
        db = Database(str(db_path))
        db.update_issue_state("github.com/owner/repo1", 1, "Research")
        db.update_issue_state("github.com/owner/repo2", 2, "Plan")
        db.update_issue_state("github.com/owner/repo1", 3, "Implement")

        mock_client = MagicMock()
        mock_client.get_ticket_labels.return_value = set()
        mock_client.get_linked_prs.return_value = []

        with (
            patch("src.config.load_config") as mock_config,
            patch("src.ticket_clients.get_github_client", return_value=mock_client),
        ):
            mock_config.return_value = MagicMock(
                github_token="fake-token",
                github_enterprise_host=None,
                github_enterprise_token=None,
                github_enterprise_version=None,
            )
            cmd_logs_summary(db)

        db.close()
        captured = capsys.readouterr()
        assert "owner/repo1#1" in captured.out
        assert "owner/repo2#2" in captured.out
        assert "owner/repo1#3" in captured.out


@pytest.mark.unit
class TestCmdLogsSummaryDispatch:
    """Tests for cmd_logs dispatching to summary view."""

    def test_cmd_logs_no_issue_calls_summary(self, tmp_path, capsys):
        """Test that cmd_logs with no issue argument shows summary."""
        from src.cli import cmd_logs

        # Create database with test data
        kiln_dir = tmp_path / ".kiln"
        kiln_dir.mkdir()
        db_path = kiln_dir / "kiln.db"
        db = Database(str(db_path))
        db.update_issue_state("github.com/owner/repo", 42, "Research")
        db.close()

        args = argparse.Namespace(
            issue=None,
            list=True,
            view=None,
            session=None,
        )

        mock_client = MagicMock()
        mock_client.get_ticket_labels.return_value = set()
        mock_client.get_linked_prs.return_value = []

        with (
            patch("src.cli.get_kiln_dir", return_value=tmp_path / ".kiln"),
            patch("src.config.load_config") as mock_config,
            patch("src.ticket_clients.get_github_client", return_value=mock_client),
        ):
            mock_config.return_value = MagicMock(
                github_token="fake-token",
                github_enterprise_host=None,
                github_enterprise_token=None,
                github_enterprise_version=None,
            )
            cmd_logs(args)

        captured = capsys.readouterr()
        # Should show summary table headers
        assert "Identifier" in captured.out
        assert "Branch" in captured.out
        assert "State" in captured.out

    def test_cmd_logs_with_issue_shows_history(self, tmp_path, capsys):
        """Test that cmd_logs with issue argument shows run history."""
        from src.cli import cmd_logs

        # Create database with run record
        kiln_dir = tmp_path / ".kiln"
        kiln_dir.mkdir()
        db_path = kiln_dir / "kiln.db"
        db = Database(str(db_path))
        record = RunRecord(
            repo="github.com/owner/repo",
            issue_number=42,
            workflow="Research",
            started_at=datetime.now(),
        )
        run_id = db.insert_run_record(record)
        db.update_run_record(run_id, completed_at=datetime.now(), outcome="success")
        db.close()

        args = argparse.Namespace(
            issue="owner/repo#42",
            list=True,
            view=None,
            session=None,
        )

        with patch("src.cli.get_kiln_dir", return_value=tmp_path / ".kiln"):
            cmd_logs(args)

        captured = capsys.readouterr()
        # Should show run history
        assert "Run history for owner/repo#42" in captured.out
        assert "Research" in captured.out


@pytest.mark.unit
class TestCliLogsCommand:
    """Tests for CLI logs command parsing and helpers."""

    def test_parse_issue_arg_owner_repo_format(self):
        """Test parsing owner/repo#number format."""
        from src.cli import parse_issue_arg

        repo, issue_num = parse_issue_arg("owner/repo#42")
        assert repo == "github.com/owner/repo"
        assert issue_num == 42

    def test_parse_issue_arg_hostname_format(self):
        """Test parsing hostname/owner/repo#number format."""
        from src.cli import parse_issue_arg

        repo, issue_num = parse_issue_arg("github.corp.com/owner/repo#123")
        assert repo == "github.corp.com/owner/repo"
        assert issue_num == 123

    def test_parse_issue_arg_invalid_format(self):
        """Test that invalid format raises ValueError."""
        from src.cli import parse_issue_arg

        with pytest.raises(ValueError, match="Invalid issue format"):
            parse_issue_arg("invalid")

    def test_parse_issue_arg_missing_number(self):
        """Test that missing issue number raises ValueError."""
        from src.cli import parse_issue_arg

        with pytest.raises(ValueError, match="Invalid issue format"):
            parse_issue_arg("owner/repo")

    def test_format_duration_seconds(self):
        """Test duration formatting for seconds."""
        from src.cli import format_duration

        start = datetime.now()
        end = start + timedelta(seconds=45)
        assert format_duration(start, end) == "45s"

    def test_format_duration_minutes(self):
        """Test duration formatting for minutes."""
        from src.cli import format_duration

        start = datetime.now()
        end = start + timedelta(minutes=3, seconds=30)
        assert format_duration(start, end) == "3m 30s"

    def test_format_duration_hours(self):
        """Test duration formatting for hours."""
        from src.cli import format_duration

        start = datetime.now()
        end = start + timedelta(hours=2, minutes=15)
        assert format_duration(start, end) == "2h 15m"

    def test_format_duration_running(self):
        """Test duration formatting when end is None."""
        from src.cli import format_duration

        start = datetime.now()
        assert format_duration(start, None) == "running..."

    def test_format_outcome_success(self):
        """Test outcome formatting for success."""
        from src.cli import format_outcome

        assert format_outcome("success") == "✓ success"

    def test_format_outcome_failed(self):
        """Test outcome formatting for failed."""
        from src.cli import format_outcome

        assert format_outcome("failed") == "✗ failed"

    def test_format_outcome_stalled(self):
        """Test outcome formatting for stalled."""
        from src.cli import format_outcome

        assert format_outcome("stalled") == "⚠ stalled"

    def test_format_outcome_running(self):
        """Test outcome formatting for running (None)."""
        from src.cli import format_outcome

        assert format_outcome(None) == "⏳ running"

    def test_format_outcome_unknown(self):
        """Test outcome formatting for unknown value."""
        from src.cli import format_outcome

        assert format_outcome("unknown") == "? unknown"


@pytest.mark.unit
class TestCmdLogs:
    """Tests for the cmd_logs function."""

    def test_cmd_logs_list_runs(self, tmp_path, capsys):
        """Test listing runs for an issue."""
        from src.cli import cmd_logs

        # Create database with run records
        kiln_dir = tmp_path / ".kiln"
        kiln_dir.mkdir()
        db_path = kiln_dir / "kiln.db"
        db = Database(str(db_path))

        # Insert test run
        record = RunRecord(
            repo="github.com/owner/repo",
            issue_number=42,
            workflow="Research",
            started_at=datetime.now(),
        )
        run_id = db.insert_run_record(record)
        db.update_run_record(run_id, completed_at=datetime.now(), outcome="success")
        db.close()

        # Create args
        args = argparse.Namespace(
            issue="owner/repo#42",
            list=True,
            view=None,
            session=None,
        )

        with patch("src.cli.get_kiln_dir", return_value=tmp_path / ".kiln"):
            cmd_logs(args)

        captured = capsys.readouterr()
        assert "Run history for owner/repo#42" in captured.out
        assert "Research" in captured.out
        assert "success" in captured.out

    def test_cmd_logs_no_runs_found(self, tmp_path, capsys):
        """Test listing runs when none exist."""
        from src.cli import cmd_logs

        # Create database without run records
        kiln_dir = tmp_path / ".kiln"
        kiln_dir.mkdir()
        db_path = kiln_dir / "kiln.db"
        db = Database(str(db_path))
        db.close()

        args = argparse.Namespace(
            issue="owner/repo#999",
            list=True,
            view=None,
            session=None,
        )

        with patch("src.cli.get_kiln_dir", return_value=tmp_path / ".kiln"):
            cmd_logs(args)

        captured = capsys.readouterr()
        assert "No run history found" in captured.out

    def test_cmd_logs_view_run(self, tmp_path, capsys):
        """Test viewing a specific run's log file."""
        from src.cli import cmd_logs

        # Create database and log file
        kiln_dir = tmp_path / ".kiln"
        kiln_dir.mkdir()
        logs_dir = kiln_dir / "logs" / "github.com" / "owner" / "repo" / "42"
        logs_dir.mkdir(parents=True)
        log_file = logs_dir / "research-20240115-1430.log"
        log_file.write_text("This is test log content\nWith multiple lines")

        db_path = kiln_dir / "kiln.db"
        db = Database(str(db_path))
        record = RunRecord(
            repo="github.com/owner/repo",
            issue_number=42,
            workflow="Research",
            started_at=datetime.now(),
            log_path=str(log_file),
        )
        run_id = db.insert_run_record(record)
        db.close()

        args = argparse.Namespace(
            issue="owner/repo#42",
            list=True,
            view=run_id,
            session=None,
        )

        with patch("src.cli.get_kiln_dir", return_value=tmp_path / ".kiln"):
            cmd_logs(args)

        captured = capsys.readouterr()
        assert "test log content" in captured.out
        assert "multiple lines" in captured.out

    def test_cmd_logs_view_run_not_found(self, tmp_path, capsys):
        """Test viewing a non-existent run."""
        from src.cli import cmd_logs

        # Create database without run records
        kiln_dir = tmp_path / ".kiln"
        kiln_dir.mkdir()
        db_path = kiln_dir / "kiln.db"
        db = Database(str(db_path))
        db.close()

        args = argparse.Namespace(
            issue="owner/repo#42",
            list=True,
            view=999,
            session=None,
        )

        with patch("src.cli.get_kiln_dir", return_value=tmp_path / ".kiln"):
            with pytest.raises(SystemExit) as exc_info:
                cmd_logs(args)
            assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "not found" in captured.err

    def test_cmd_logs_session_info(self, tmp_path, capsys):
        """Test getting session info for a run."""
        from src.cli import cmd_logs

        # Create database with session ID
        kiln_dir = tmp_path / ".kiln"
        kiln_dir.mkdir()
        logs_dir = kiln_dir / "logs" / "github.com" / "owner" / "repo" / "42"
        logs_dir.mkdir(parents=True)
        log_file = logs_dir / "research-20240115-1430.log"
        log_file.write_text("log content")
        session_file = logs_dir / "research-20240115-1430.session"
        session_file.write_text("session-abc-123")

        db_path = kiln_dir / "kiln.db"
        db = Database(str(db_path))
        record = RunRecord(
            repo="github.com/owner/repo",
            issue_number=42,
            workflow="Research",
            started_at=datetime.now(),
            session_id="session-abc-123",
            log_path=str(log_file),
        )
        run_id = db.insert_run_record(record)
        db.close()

        args = argparse.Namespace(
            issue="owner/repo#42",
            list=True,
            view=None,
            session=run_id,
        )

        with patch("src.cli.get_kiln_dir", return_value=tmp_path / ".kiln"):
            cmd_logs(args)

        captured = capsys.readouterr()
        assert "Session file:" in captured.out or "Session ID:" in captured.out

    def test_cmd_logs_session_no_session_id(self, tmp_path, capsys):
        """Test getting session info when no session ID exists."""
        from src.cli import cmd_logs

        # Create database without session ID
        kiln_dir = tmp_path / ".kiln"
        kiln_dir.mkdir()
        db_path = kiln_dir / "kiln.db"
        db = Database(str(db_path))
        record = RunRecord(
            repo="github.com/owner/repo",
            issue_number=42,
            workflow="Research",
            started_at=datetime.now(),
        )
        run_id = db.insert_run_record(record)
        db.close()

        args = argparse.Namespace(
            issue="owner/repo#42",
            list=True,
            view=None,
            session=run_id,
        )

        with patch("src.cli.get_kiln_dir", return_value=tmp_path / ".kiln"):
            with pytest.raises(SystemExit) as exc_info:
                cmd_logs(args)
            assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "No session ID" in captured.err

    def test_cmd_logs_no_database(self, tmp_path, capsys):
        """Test that error is shown when database doesn't exist."""
        from src.cli import cmd_logs

        # Don't create database
        kiln_dir = tmp_path / ".kiln"
        kiln_dir.mkdir()

        args = argparse.Namespace(
            issue="owner/repo#42",
            list=True,
            view=None,
            session=None,
        )

        with patch("src.cli.get_kiln_dir", return_value=tmp_path / ".kiln"):
            with pytest.raises(SystemExit) as exc_info:
                cmd_logs(args)
            assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "No database found" in captured.err

    def test_cmd_logs_run_belongs_to_different_issue(self, tmp_path, capsys):
        """Test viewing a run that belongs to a different issue."""
        from src.cli import cmd_logs

        kiln_dir = tmp_path / ".kiln"
        kiln_dir.mkdir()
        db_path = kiln_dir / "kiln.db"
        db = Database(str(db_path))

        # Create run for issue #42
        record = RunRecord(
            repo="github.com/owner/repo",
            issue_number=42,
            workflow="Research",
            started_at=datetime.now(),
        )
        run_id = db.insert_run_record(record)
        db.close()

        # Try to view it from issue #43
        args = argparse.Namespace(
            issue="owner/repo#43",
            list=True,
            view=run_id,
            session=None,
        )

        with patch("src.cli.get_kiln_dir", return_value=tmp_path / ".kiln"):
            with pytest.raises(SystemExit) as exc_info:
                cmd_logs(args)
            assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "does not belong to" in captured.err


@pytest.mark.integration
class TestRunLoggingIntegration:
    """Integration tests for run logging with daemon workflow execution."""

    @pytest.fixture
    def mock_daemon(self, tmp_path):
        """Fixture providing a mock daemon with database and logging configured."""
        from src.daemon import Daemon

        config = MagicMock()
        config.poll_interval = 60
        config.watched_statuses = ["Research", "Plan", "Implement"]
        config.max_concurrent_workflows = 2
        config.database_path = str(tmp_path / "test.db")
        config.workspace_dir = str(tmp_path / "worktrees")
        config.project_urls = ["https://github.com/orgs/test/projects/1"]

        config.github_enterprise_version = None
        config.ghes_logs_mask = False
        config.github_enterprise_host = None
        config.log_file = str(tmp_path / ".kiln/logs/kiln.log")
        config.username_self = "test-user"

        # Create directories
        (tmp_path / "worktrees").mkdir()
        (tmp_path / ".kiln" / "logs").mkdir(parents=True)

        with (
            patch("src.ticket_clients.get_github_client") as mock_get_client,
            patch(
                "src.ticket_clients.github.GitHubTicketClient.validate_scopes",
                return_value=True,
            ),
        ):
            # Mock the client instance that will be created
            mock_client = MagicMock()
            mock_client.validate_connection.return_value = True
            mock_client.validate_scopes.return_value = True
            mock_client.client_description = "MockGitHubClient"
            # Mock get_label_actor to return our username for post-claim verification
            mock_client.get_label_actor.return_value = "test-user"
            mock_get_client.return_value = mock_client

            daemon = Daemon(config)
            daemon.ticket_client = mock_client
            daemon.comment_processor.ticket_client = mock_client
            yield daemon
            daemon.stop()

    def test_workflow_creates_run_record(self, mock_daemon, tmp_path):
        """Test that running a workflow creates a run record in the database."""
        from src.interfaces.ticket import TicketItem

        # Create a mock ticket item
        item = TicketItem(
            item_id="item1",
            ticket_id=42,
            repo="github.com/owner/repo",
            status="Research",
            title="Test Issue",
            labels=set(),
            board_url="https://github.com/orgs/test/projects/1",
        )

        # Create worktree to avoid auto-prepare (path format: {repo_name}-issue-{issue_number})
        worktree_path = tmp_path / "worktrees" / "repo-issue-42"
        worktree_path.mkdir(parents=True)

        # Mock the workflow runner to succeed
        mock_daemon._run_workflow = MagicMock(return_value="session-123")
        mock_daemon.ticket_client.get_comments.return_value = []
        mock_daemon.ticket_client.get_ticket_body.return_value = "<!-- kiln:research -->Research content"

        # Run the workflow
        mock_daemon._process_item_workflow(item)

        # Check that a run record was created
        history = mock_daemon.database.get_run_history("github.com/owner/repo", 42)
        assert len(history) == 1
        assert history[0].workflow == "Research"
        assert history[0].outcome == "success"
        assert history[0].session_id == "session-123"

    def test_workflow_failure_records_failed_outcome(self, mock_daemon, tmp_path):
        """Test that a failed workflow records a failed outcome."""
        from src.interfaces.ticket import TicketItem

        item = TicketItem(
            item_id="item1",
            ticket_id=42,
            repo="github.com/owner/repo",
            status="Research",
            title="Test Issue",
            labels=set(),
            board_url="https://github.com/orgs/test/projects/1",
        )

        # Create worktree (path format: {repo_name}-issue-{issue_number})
        worktree_path = tmp_path / "worktrees" / "repo-issue-42"
        worktree_path.mkdir(parents=True)

        # Mock the workflow runner to fail
        mock_daemon._run_workflow = MagicMock(side_effect=Exception("Workflow failed"))

        # Run the workflow (should raise)
        with pytest.raises(Exception, match="Workflow failed"):
            mock_daemon._process_item_workflow(item)

        # Check that a run record was created with failed outcome
        history = mock_daemon.database.get_run_history("github.com/owner/repo", 42)
        assert len(history) == 1
        assert history[0].workflow == "Research"
        assert history[0].outcome == "failed"

    def test_workflow_creates_log_file(self, mock_daemon, tmp_path):
        """Test that running a workflow creates a log file."""
        from src.interfaces.ticket import TicketItem

        item = TicketItem(
            item_id="item1",
            ticket_id=42,
            repo="github.com/owner/repo",
            status="Research",
            title="Test Issue",
            labels=set(),
            board_url="https://github.com/orgs/test/projects/1",
        )

        # Create worktree
        worktree_path = tmp_path / "worktrees" / "repo-issue-42"
        worktree_path.mkdir(parents=True)

        # Mock the workflow runner to succeed
        mock_daemon._run_workflow = MagicMock(return_value="session-123")
        mock_daemon.ticket_client.get_comments.return_value = []
        mock_daemon.ticket_client.get_ticket_body.return_value = "<!-- kiln:research -->Research content"

        # Run the workflow
        mock_daemon._process_item_workflow(item)

        # Check that a log file was created
        history = mock_daemon.database.get_run_history("github.com/owner/repo", 42)
        assert len(history) == 1
        assert history[0].log_path is not None
        assert Path(history[0].log_path).exists()

    def test_workflow_writes_session_file(self, mock_daemon, tmp_path):
        """Test that successful workflow writes a .session file."""
        from src.interfaces.ticket import TicketItem

        item = TicketItem(
            item_id="item1",
            ticket_id=42,
            repo="github.com/owner/repo",
            status="Research",
            title="Test Issue",
            labels=set(),
            board_url="https://github.com/orgs/test/projects/1",
        )

        # Create worktree
        worktree_path = tmp_path / "worktrees" / "repo-issue-42"
        worktree_path.mkdir(parents=True)

        # Mock the workflow runner to succeed with session ID
        mock_daemon._run_workflow = MagicMock(return_value="session-abc-xyz")
        mock_daemon.ticket_client.get_comments.return_value = []
        mock_daemon.ticket_client.get_ticket_body.return_value = "<!-- kiln:research -->Research content"

        # Run the workflow
        mock_daemon._process_item_workflow(item)

        # Check that a session file was created
        history = mock_daemon.database.get_run_history("github.com/owner/repo", 42)
        assert len(history) == 1
        log_path = history[0].log_path
        session_path = log_path.replace(".log", ".session")
        assert Path(session_path).exists()
        assert Path(session_path).read_text() == "session-abc-xyz"

    def test_multiple_runs_create_multiple_records(self, mock_daemon, tmp_path):
        """Test that multiple workflow runs create multiple records."""
        from src.interfaces.ticket import TicketItem

        item = TicketItem(
            item_id="item1",
            ticket_id=42,
            repo="github.com/owner/repo",
            status="Research",
            title="Test Issue",
            labels=set(),
            board_url="https://github.com/orgs/test/projects/1",
        )

        # Create worktree
        worktree_path = tmp_path / "worktrees" / "repo-issue-42"
        worktree_path.mkdir(parents=True)

        # Run workflow 3 times
        for i in range(3):
            mock_daemon._run_workflow = MagicMock(return_value=f"session-{i}")
            mock_daemon.ticket_client.get_comments.return_value = []
            mock_daemon.ticket_client.get_ticket_body.return_value = "<!-- kiln:research -->Research content"
            mock_daemon._process_item_workflow(item)

        # Check that 3 run records were created
        history = mock_daemon.database.get_run_history("github.com/owner/repo", 42)
        assert len(history) == 3
