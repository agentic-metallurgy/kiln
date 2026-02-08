"""Integration tests for Daemon core behavior.

These tests verify daemon core functionality like exponential backoff,
while mocking external dependencies.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.daemon import Daemon


@pytest.mark.integration
class TestDaemonBackoff:
    """Tests for daemon exponential backoff behavior using tenacity."""

    @pytest.fixture
    def daemon(self, temp_workspace_dir):
        """Fixture providing Daemon with mocked dependencies."""
        config = MagicMock()
        config.poll_interval = 60
        config.watched_statuses = ["Research", "Plan", "Implement"]
        config.max_concurrent_workflows = 2
        config.database_path = f"{temp_workspace_dir}/test.db"
        config.workspace_dir = temp_workspace_dir
        config.project_urls = ["https://github.com/orgs/test/projects/1"]

        config.github_enterprise_version = None

        with patch("src.ticket_clients.github.GitHubTicketClient"):
            daemon = Daemon(config)
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


@pytest.mark.integration
class TestDaemonMultiActorRaceDetection:
    """Tests for multi-actor race detection in post-claim verification."""

    @pytest.fixture
    def daemon_with_username(self, temp_workspace_dir):
        """Fixture providing Daemon with mocked dependencies and username_self."""
        config = MagicMock()
        config.poll_interval = 60
        config.watched_statuses = ["Research", "Plan", "Implement"]
        config.max_concurrent_workflows = 2
        config.database_path = f"{temp_workspace_dir}/test.db"
        config.workspace_dir = temp_workspace_dir
        config.project_urls = ["https://github.com/orgs/test/projects/1"]

        config.github_enterprise_version = None
        config.username_self = "kiln-bot"  # Our bot username

        with patch("src.ticket_clients.github.GitHubTicketClient"):
            daemon = Daemon(config)
            daemon.ticket_client = MagicMock()
            daemon.comment_processor.ticket_client = daemon.ticket_client
            # Mock database methods
            daemon.database = MagicMock()
            daemon.database.get_issue_state.return_value = None
            yield daemon
            daemon.stop()

    def test_race_detected_different_actor_aborts_workflow(self, daemon_with_username):
        """Test that workflow aborts when a different actor claimed the label first."""
        from src.interfaces import TicketItem
        from src.labels import Labels

        daemon = daemon_with_username

        # Create a mock ticket item for Research workflow
        item = TicketItem(
            item_id="PVTI_test123",
            repo="test-org/test-repo",
            ticket_id=123,
            status="Research",
            title="Test Issue",
            board_url="https://github.com/orgs/test/projects/1",
        )

        # Mock _get_worktree_path to return an existing path (skip worktree creation)
        with patch.object(daemon, "_get_worktree_path") as mock_worktree_path:
            mock_worktree_path.return_value = daemon.config.workspace_dir + "/test"
            # Create the directory so it "exists"
            import os

            os.makedirs(mock_worktree_path.return_value, exist_ok=True)

            # Mock get_label_actor to return a DIFFERENT actor (race lost)
            daemon.ticket_client.get_label_actor.return_value = "other-bot"

            # Mock time.sleep to not actually sleep
            with patch("src.daemon.time.sleep"):
                # Run the workflow processing
                daemon._process_item_workflow(item)

        # Verify add_label was called (we tried to claim)
        daemon.ticket_client.add_label.assert_called_once_with(
            item.repo, item.ticket_id, Labels.RESEARCHING
        )

        # Verify get_label_actor was called to check who won
        daemon.ticket_client.get_label_actor.assert_called_once_with(
            item.repo, item.ticket_id, Labels.RESEARCHING
        )

        # Verify label was NOT removed (critical: let the winner keep it)
        daemon.ticket_client.remove_label.assert_not_called()

        # Verify _running_labels was updated (removed from tracking)
        key = f"{item.repo}#{item.ticket_id}"
        assert key not in daemon._running_labels

    def test_verification_failure_none_actor_aborts_workflow(self, daemon_with_username):
        """Test that workflow aborts when get_label_actor returns None."""
        from src.interfaces import TicketItem
        from src.labels import Labels

        daemon = daemon_with_username

        item = TicketItem(
            item_id="PVTI_test456",
            repo="test-org/test-repo",
            ticket_id=456,
            status="Plan",
            title="Test Issue Plan",
            board_url="https://github.com/orgs/test/projects/1",
        )

        with patch.object(daemon, "_get_worktree_path") as mock_worktree_path:
            mock_worktree_path.return_value = daemon.config.workspace_dir + "/test"
            import os

            os.makedirs(mock_worktree_path.return_value, exist_ok=True)

            # Mock get_label_actor to return None (verification failure)
            daemon.ticket_client.get_label_actor.return_value = None

            with patch("src.daemon.time.sleep"):
                daemon._process_item_workflow(item)

        # Verify add_label was called
        daemon.ticket_client.add_label.assert_called_once_with(
            item.repo, item.ticket_id, Labels.PLANNING
        )

        # Verify get_label_actor was called
        daemon.ticket_client.get_label_actor.assert_called_once_with(
            item.repo, item.ticket_id, Labels.PLANNING
        )

        # Verify label was NOT removed
        daemon.ticket_client.remove_label.assert_not_called()

        # Verify _running_labels was updated (removed from tracking)
        key = f"{item.repo}#{item.ticket_id}"
        assert key not in daemon._running_labels

    def test_successful_claim_proceeds_with_workflow(self, daemon_with_username):
        """Test that workflow proceeds when we successfully claimed the label."""
        from src.interfaces import TicketItem
        from src.labels import Labels

        daemon = daemon_with_username

        item = TicketItem(
            item_id="PVTI_test789",
            repo="test-org/test-repo",
            ticket_id=789,
            status="Implement",
            title="Test Issue Implement",
            board_url="https://github.com/orgs/test/projects/1",
        )

        with patch.object(daemon, "_get_worktree_path") as mock_worktree_path:
            mock_worktree_path.return_value = daemon.config.workspace_dir + "/test"
            import os

            os.makedirs(mock_worktree_path.return_value, exist_ok=True)

            # Mock get_label_actor to return OUR username (we won!)
            daemon.ticket_client.get_label_actor.return_value = "kiln-bot"

            # Mock the MCP config manager
            daemon.mcp_config_manager = MagicMock()
            daemon.mcp_config_manager.has_config.return_value = False

            # Mock _run_workflow to track that it was called
            workflow_called = [False]

            def mock_run_workflow(*args, **kwargs):
                workflow_called[0] = True
                return "session-123"

            with (
                patch("src.daemon.time.sleep"),
                patch.object(daemon, "_run_workflow", side_effect=mock_run_workflow),
            ):
                daemon._process_item_workflow(item)

        # Verify add_label was called
        daemon.ticket_client.add_label.assert_any_call(
            item.repo, item.ticket_id, Labels.IMPLEMENTING
        )

        # Verify get_label_actor was called
        daemon.ticket_client.get_label_actor.assert_called_once_with(
            item.repo, item.ticket_id, Labels.IMPLEMENTING
        )

        # Verify workflow was executed (we proceeded past verification)
        assert workflow_called[0], "Workflow should have been called after successful claim"

    def test_race_detection_for_all_workflow_labels(self, daemon_with_username):
        """Test race detection works for researching, planning, and implementing labels."""
        from src.interfaces import TicketItem
        from src.labels import Labels

        daemon = daemon_with_username

        test_cases = [
            ("Research", Labels.RESEARCHING),
            ("Plan", Labels.PLANNING),
            ("Implement", Labels.IMPLEMENTING),
        ]

        for status, expected_label in test_cases:
            # Reset mocks for each iteration
            daemon.ticket_client.reset_mock()
            daemon._running_labels.clear()

            item = TicketItem(
                item_id=f"PVTI_test{status}",
                repo="test-org/test-repo",
                ticket_id=100,
                status=status,
                title=f"Test Issue {status}",
                board_url="https://github.com/orgs/test/projects/1",
            )

            with patch.object(daemon, "_get_worktree_path") as mock_worktree_path:
                mock_worktree_path.return_value = daemon.config.workspace_dir + "/test"
                import os

                os.makedirs(mock_worktree_path.return_value, exist_ok=True)

                # Mock to return a different actor (race lost)
                daemon.ticket_client.get_label_actor.return_value = "competitor-bot"

                with patch("src.daemon.time.sleep"):
                    daemon._process_item_workflow(item)

            # Verify the correct running label was used
            daemon.ticket_client.add_label.assert_called_once_with(
                item.repo, item.ticket_id, expected_label
            )

            # Verify label was NOT removed on race loss
            daemon.ticket_client.remove_label.assert_not_called()

    def test_running_labels_tracking_on_race_abort(self, daemon_with_username):
        """Test that _running_labels is properly cleaned up when race is detected."""
        from src.interfaces import TicketItem

        daemon = daemon_with_username

        item = TicketItem(
            item_id="PVTI_test999",
            repo="test-org/test-repo",
            ticket_id=999,
            status="Research",
            title="Test Issue Tracking",
            board_url="https://github.com/orgs/test/projects/1",
        )
        key = f"{item.repo}#{item.ticket_id}"

        with patch.object(daemon, "_get_worktree_path") as mock_worktree_path:
            mock_worktree_path.return_value = daemon.config.workspace_dir + "/test"
            import os

            os.makedirs(mock_worktree_path.return_value, exist_ok=True)

            # Track when the label is added to _running_labels
            original_add_label = daemon.ticket_client.add_label

            def tracking_add_label(*args, **kwargs):
                # After add_label is called, verify _running_labels is updated
                # This happens inside _process_item_workflow
                return original_add_label(*args, **kwargs)

            daemon.ticket_client.add_label = tracking_add_label

            # Mock to return a different actor (race lost)
            daemon.ticket_client.get_label_actor.return_value = "winner-bot"

            with patch("src.daemon.time.sleep"):
                # Before processing, _running_labels should be empty
                assert key not in daemon._running_labels

                daemon._process_item_workflow(item)

                # After processing with race loss, key should be removed from _running_labels
                assert key not in daemon._running_labels, (
                    "_running_labels should not contain the key after race abort"
                )


@pytest.mark.integration
class TestDaemonStaleCommentCleanup:
    """Tests for stale eyes reaction cleanup on daemon startup."""

    @pytest.fixture
    def daemon(self, temp_workspace_dir):
        """Fixture providing Daemon with mocked dependencies."""
        config = MagicMock()
        config.poll_interval = 60
        config.watched_statuses = ["Research", "Plan", "Implement"]
        config.max_concurrent_workflows = 2
        config.database_path = f"{temp_workspace_dir}/test.db"
        config.workspace_dir = temp_workspace_dir
        config.project_urls = ["https://github.com/orgs/test/projects/1"]
        config.github_enterprise_version = None

        with patch("src.ticket_clients.github.GitHubTicketClient"):
            daemon = Daemon(config)
            daemon.ticket_client = MagicMock()
            daemon.comment_processor.ticket_client = daemon.ticket_client
            yield daemon
            daemon.stop()

    def test_cleanup_stale_processing_comments_no_stale(self, daemon):
        """Test cleanup when there are no stale processing comments."""
        # No stale comments
        stale_comments = daemon.database.get_stale_processing_comments()
        assert stale_comments == []

        # Should complete without error and not call remove_reaction
        daemon._cleanup_stale_processing_comments()
        daemon.ticket_client.remove_reaction.assert_not_called()

    def test_cleanup_stale_processing_comments_removes_eyes_reactions(self, daemon):
        """Test that stale eyes reactions are removed on startup."""
        from datetime import datetime, timedelta

        # Add a stale processing comment (started 2 hours ago)
        repo = "github.com/test-org/test-repo"
        issue_number = 123
        comment_id = "IC_kwDOtest123"

        # Manually insert a stale record
        conn = daemon.database._get_conn()
        stale_time = (datetime.now() - timedelta(hours=2)).isoformat()
        with conn:
            conn.execute(
                """
                INSERT INTO processing_comments (repo, issue_number, comment_id, started_at)
                VALUES (?, ?, ?, ?)
                """,
                (repo, issue_number, comment_id, stale_time),
            )

        # Verify we have stale comments
        stale_comments = daemon.database.get_stale_processing_comments()
        assert len(stale_comments) == 1
        assert stale_comments[0] == (repo, issue_number, comment_id)

        # Run cleanup
        daemon._cleanup_stale_processing_comments()

        # Verify remove_reaction was called with correct parameters
        daemon.ticket_client.remove_reaction.assert_called_once_with(comment_id, "EYES", repo=repo)

        # Verify the database record was removed
        stale_comments = daemon.database.get_stale_processing_comments()
        assert stale_comments == []

    def test_cleanup_stale_processing_comments_handles_api_errors(self, daemon):
        """Test that API errors during cleanup don't crash and still remove DB records."""
        from datetime import datetime, timedelta

        repo = "github.com/test-org/test-repo"
        issue_number = 456
        comment_id = "IC_kwDOtest456"

        # Add a stale processing comment
        conn = daemon.database._get_conn()
        stale_time = (datetime.now() - timedelta(hours=2)).isoformat()
        with conn:
            conn.execute(
                """
                INSERT INTO processing_comments (repo, issue_number, comment_id, started_at)
                VALUES (?, ?, ?, ?)
                """,
                (repo, issue_number, comment_id, stale_time),
            )

        # Mock remove_reaction to raise an exception
        daemon.ticket_client.remove_reaction.side_effect = Exception("API error")

        # Cleanup should not raise
        daemon._cleanup_stale_processing_comments()

        # Verify remove_reaction was attempted
        daemon.ticket_client.remove_reaction.assert_called_once()

        # Verify the database record was still removed (best effort cleanup)
        stale_comments = daemon.database.get_stale_processing_comments()
        assert stale_comments == []

    def test_cleanup_stale_processing_comments_multiple_comments(self, daemon):
        """Test cleanup of multiple stale processing comments."""
        from datetime import datetime, timedelta

        # Add multiple stale processing comments
        stale_time = (datetime.now() - timedelta(hours=2)).isoformat()
        comments = [
            ("github.com/org1/repo1", 100, "IC_kwDOtest100"),
            ("github.com/org1/repo1", 101, "IC_kwDOtest101"),
            ("github.com/org2/repo2", 200, "IC_kwDOtest200"),
        ]

        conn = daemon.database._get_conn()
        with conn:
            for repo, issue_number, comment_id in comments:
                conn.execute(
                    """
                    INSERT INTO processing_comments (repo, issue_number, comment_id, started_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (repo, issue_number, comment_id, stale_time),
                )

        # Verify we have 3 stale comments
        stale_comments = daemon.database.get_stale_processing_comments()
        assert len(stale_comments) == 3

        # Run cleanup
        daemon._cleanup_stale_processing_comments()

        # Verify remove_reaction was called for each comment
        assert daemon.ticket_client.remove_reaction.call_count == 3

        # Verify all database records were removed
        stale_comments = daemon.database.get_stale_processing_comments()
        assert stale_comments == []

    def test_cleanup_not_triggered_for_recent_comments(self, daemon):
        """Test that recent processing comments are not cleaned up."""
        from datetime import datetime, timedelta

        # Add a recent processing comment (started 5 minutes ago, not stale)
        repo = "github.com/test-org/test-repo"
        issue_number = 789
        comment_id = "IC_kwDOtest789"

        conn = daemon.database._get_conn()
        recent_time = (datetime.now() - timedelta(minutes=5)).isoformat()
        with conn:
            conn.execute(
                """
                INSERT INTO processing_comments (repo, issue_number, comment_id, started_at)
                VALUES (?, ?, ?, ?)
                """,
                (repo, issue_number, comment_id, recent_time),
            )

        # Run cleanup
        daemon._cleanup_stale_processing_comments()

        # Verify remove_reaction was NOT called (comment is not stale)
        daemon.ticket_client.remove_reaction.assert_not_called()

        # Verify the database record still exists
        conn = daemon.database._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT comment_id FROM processing_comments WHERE comment_id = ?",
            (comment_id,),
        )
        assert cursor.fetchone() is not None
