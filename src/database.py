"""
Database module for tracking GitHub issue states in SQLite.

This module provides functionality to persist and retrieve issue state information,
including the repository, issue number, current status/column, and last updated timestamp.
"""

import json
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ProjectMetadata:
    """
    Cached metadata for a GitHub project to avoid repeated API lookups.

    Attributes:
        project_url: URL of the GitHub project (primary key)
        repo: Repository in 'owner/repo' format (derived from project items)
        project_id: GraphQL node ID for the project
        status_field_id: ID of the Status field in the project
        status_options: Mapping of status name -> option ID
        last_updated: Timestamp of the last metadata refresh
    """

    project_url: str
    repo: str | None = None
    project_id: str | None = None
    status_field_id: str | None = None
    status_options: dict[str, str] = field(default_factory=dict)
    last_updated: datetime | None = None


@dataclass
class IssueState:
    """
    Represents the state of a GitHub issue in the project board.

    Attributes:
        repo: Repository name (e.g., "owner/repo")
        issue_number: GitHub issue number
        status: Current column/status in the project board
        last_updated: Timestamp of the last state update
        branch_name: Git branch name created for this issue (for idempotent Prepare)
        project_url: URL of the project this issue belongs to
        last_processed_comment_timestamp: ISO 8601 timestamp of last processed comment (for REST API)
        research_session_id: Claude session ID for Research workflow
        plan_session_id: Claude session ID for Plan workflow
        implement_session_id: Claude session ID for Implement workflow
    """

    repo: str
    issue_number: int
    status: str
    last_updated: datetime
    branch_name: str | None = None
    project_url: str | None = None
    last_processed_comment_timestamp: str | None = None
    last_known_comment_count: int | None = None
    research_session_id: str | None = None
    plan_session_id: str | None = None
    implement_session_id: str | None = None


class Database:
    """
    SQLite database manager for issue state tracking.

    This class handles all database operations including initialization,
    retrieving issue states, updating states, and listing all tracked issues.
    """

    def __init__(self, db_path: str) -> None:
        """
        Initialize the database manager.

        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path
        self._local = threading.local()
        self._init_lock = threading.Lock()
        self._initialized = False
        self.init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """Get the thread-local database connection, creating if needed."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    @property
    def conn(self) -> sqlite3.Connection:
        """Property for backwards compatibility - returns thread-local connection."""
        return self._get_conn()

    def init_db(self) -> None:
        """
        Create the issue_states table if it doesn't exist.

        Schema includes:
        - repo: Repository name
        - issue_number: GitHub issue number
        - status: Current status/column
        - last_updated: Automatic timestamp
        - branch_name: Git branch created for this issue
        - Primary key on (repo, issue_number) to ensure uniqueness
        """
        with self._init_lock:
            if self._initialized:
                return
            conn = self._get_conn()
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS issue_states (
                        repo TEXT NOT NULL,
                        issue_number INTEGER NOT NULL,
                        status TEXT NOT NULL,
                        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        branch_name TEXT,
                        project_url TEXT,
                        PRIMARY KEY (repo, issue_number)
                    )
                """)
                # Migration: add columns if they don't exist
                cursor = conn.execute("PRAGMA table_info(issue_states)")
                columns = [row[1] for row in cursor.fetchall()]
                if "branch_name" not in columns:
                    conn.execute("ALTER TABLE issue_states ADD COLUMN branch_name TEXT")
                if "project_url" not in columns:
                    conn.execute("ALTER TABLE issue_states ADD COLUMN project_url TEXT")
                if "last_processed_comment_timestamp" not in columns:
                    conn.execute(
                        "ALTER TABLE issue_states ADD COLUMN last_processed_comment_timestamp TEXT"
                    )
                if "last_known_comment_count" not in columns:
                    conn.execute(
                        "ALTER TABLE issue_states ADD COLUMN last_known_comment_count INTEGER"
                    )
                if "research_session_id" not in columns:
                    conn.execute("ALTER TABLE issue_states ADD COLUMN research_session_id TEXT")
                if "plan_session_id" not in columns:
                    conn.execute("ALTER TABLE issue_states ADD COLUMN plan_session_id TEXT")
                if "implement_session_id" not in columns:
                    conn.execute("ALTER TABLE issue_states ADD COLUMN implement_session_id TEXT")

                # Create project_metadata table for caching project status options
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS project_metadata (
                        project_url TEXT PRIMARY KEY,
                        repo TEXT,
                        project_id TEXT,
                        status_field_id TEXT,
                        status_options TEXT,
                        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Migration: update repo format from 'owner/repo' to 'github.com/owner/repo'
                # Idempotent: only updates records that don't have a hostname prefix (no dot before slash)
                conn.execute("""
                    UPDATE issue_states
                    SET repo = 'github.com/' || repo
                    WHERE repo NOT LIKE '%.%/%'
                """)
                conn.execute("""
                    UPDATE project_metadata
                    SET repo = 'github.com/' || repo
                    WHERE repo IS NOT NULL AND repo NOT LIKE '%.%/%'
                """)
            self._initialized = True

    def get_issue_state(self, repo: str, issue_number: int) -> IssueState | None:
        """
        Retrieve the state of a specific issue.

        Args:
            repo: Repository name
            issue_number: GitHub issue number

        Returns:
            IssueState object if found, None otherwise
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT repo, issue_number, status, last_updated, branch_name, project_url,
                   last_processed_comment_timestamp, last_known_comment_count,
                   research_session_id, plan_session_id, implement_session_id
            FROM issue_states
            WHERE repo = ? AND issue_number = ?
            """,
            (repo, issue_number),
        )

        row = cursor.fetchone()
        if row:
            return IssueState(
                repo=row["repo"],
                issue_number=row["issue_number"],
                status=row["status"],
                last_updated=datetime.fromisoformat(row["last_updated"]),
                branch_name=row["branch_name"],
                project_url=row["project_url"],
                last_processed_comment_timestamp=row["last_processed_comment_timestamp"],
                last_known_comment_count=row["last_known_comment_count"],
                research_session_id=row["research_session_id"],
                plan_session_id=row["plan_session_id"],
                implement_session_id=row["implement_session_id"],
            )
        return None

    def update_issue_state(
        self,
        repo: str,
        issue_number: int,
        status: str,
        branch_name: str | None = None,
        project_url: str | None = None,
        last_processed_comment_timestamp: str | None = None,
        last_known_comment_count: int | None = None,
        research_session_id: str | None = None,
        plan_session_id: str | None = None,
        implement_session_id: str | None = None,
    ) -> None:
        """
        Update or insert the state of an issue.

        Uses INSERT OR REPLACE to handle both new and existing issues.
        Automatically updates the last_updated timestamp.

        Args:
            repo: Repository name
            issue_number: GitHub issue number
            status: New status/column for the issue
            branch_name: Git branch name (optional, preserved if not provided)
            project_url: URL of the project this issue belongs to (optional, preserved if not provided)
            last_processed_comment_timestamp: ISO 8601 timestamp of last processed comment (optional, preserved if not provided)
            last_known_comment_count: Comment count from GraphQL query (optional, preserved if not provided)
            research_session_id: Claude session ID for Research workflow (optional, preserved if not provided)
            plan_session_id: Claude session ID for Plan workflow (optional, preserved if not provided)
            implement_session_id: Claude session ID for Implement workflow (optional, preserved if not provided)
        """
        conn = self._get_conn()

        # Preserve existing values if not provided
        existing = self.get_issue_state(repo, issue_number)
        if existing:
            if branch_name is None:
                branch_name = existing.branch_name
            if project_url is None:
                project_url = existing.project_url
            if last_processed_comment_timestamp is None:
                last_processed_comment_timestamp = existing.last_processed_comment_timestamp
            if last_known_comment_count is None:
                last_known_comment_count = existing.last_known_comment_count
            if research_session_id is None:
                research_session_id = existing.research_session_id
            if plan_session_id is None:
                plan_session_id = existing.plan_session_id
            if implement_session_id is None:
                implement_session_id = existing.implement_session_id

        with conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO issue_states
                (repo, issue_number, status, last_updated, branch_name, project_url,
                 last_processed_comment_timestamp, last_known_comment_count,
                 research_session_id, plan_session_id, implement_session_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    repo,
                    issue_number,
                    status,
                    datetime.now().isoformat(),
                    branch_name,
                    project_url,
                    last_processed_comment_timestamp,
                    last_known_comment_count,
                    research_session_id,
                    plan_session_id,
                    implement_session_id,
                ),
            )

    def get_project_metadata(self, project_url: str) -> ProjectMetadata | None:
        """
        Retrieve cached metadata for a project.

        Args:
            project_url: URL of the GitHub project

        Returns:
            ProjectMetadata object if found, None otherwise
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT project_url, repo, project_id, status_field_id, status_options, last_updated
            FROM project_metadata
            WHERE project_url = ?
            """,
            (project_url,),
        )

        row = cursor.fetchone()
        if row:
            return ProjectMetadata(
                project_url=row["project_url"],
                repo=row["repo"],
                project_id=row["project_id"],
                status_field_id=row["status_field_id"],
                status_options=json.loads(row["status_options"]) if row["status_options"] else {},
                last_updated=datetime.fromisoformat(row["last_updated"])
                if row["last_updated"]
                else None,
            )
        return None

    def upsert_project_metadata(self, metadata: ProjectMetadata) -> None:
        """
        Insert or update project metadata.

        Args:
            metadata: ProjectMetadata object to store
        """
        conn = self._get_conn()
        with conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO project_metadata
                (project_url, repo, project_id, status_field_id, status_options, last_updated)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    metadata.project_url,
                    metadata.repo,
                    metadata.project_id,
                    metadata.status_field_id,
                    json.dumps(metadata.status_options),
                    datetime.now().isoformat(),
                ),
            )

    def get_workflow_session_id(self, repo: str, issue_number: int, workflow: str) -> str | None:
        """
        Get the session ID for a specific workflow.

        Args:
            repo: Repository name
            issue_number: GitHub issue number
            workflow: Workflow name ("Research", "Plan", "Implement")

        Returns:
            Session ID if found, None otherwise
        """
        state = self.get_issue_state(repo, issue_number)
        if not state:
            return None

        session_field = f"{workflow.lower()}_session_id"
        return getattr(state, session_field, None)

    def set_workflow_session_id(
        self, repo: str, issue_number: int, workflow: str, session_id: str
    ) -> None:
        """
        Set the session ID for a specific workflow.

        Args:
            repo: Repository name
            issue_number: GitHub issue number
            workflow: Workflow name ("Research", "Plan", "Implement")
            session_id: The Claude session ID to store
        """
        state = self.get_issue_state(repo, issue_number)
        if not state:
            return

        kwargs = {f"{workflow.lower()}_session_id": session_id}
        self.update_issue_state(repo, issue_number, state.status, **kwargs)

    def close(self) -> None:
        """
        Close the current thread's database connection.

        Should be called when done with the database to free resources.
        Can also be used via context manager pattern.
        """
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None

    def __enter__(self) -> "Database":
        """Context manager entry point."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit point - ensures connection is closed."""
        self.close()
