"""Unit tests for Daemon process tracking functionality.

These tests verify the subprocess tracking behavior:
- register_process() adds process to dict
- unregister_process() removes process from dict
- kill_process() kills and removes process
- kill_process() handles edge cases (already dead, not found)
- Process isolation (killing one process doesn't affect others)
"""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from src.daemon import Daemon


@pytest.fixture
def daemon(temp_workspace_dir):
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


@pytest.fixture
def mock_process():
    """Fixture providing a mock subprocess.Popen object."""
    process = MagicMock(spec=subprocess.Popen)
    process.pid = 12345
    return process


@pytest.fixture
def mock_process_2():
    """Fixture providing a second mock subprocess.Popen object."""
    process = MagicMock(spec=subprocess.Popen)
    process.pid = 54321
    return process


@pytest.mark.integration
class TestRegisterProcess:
    """Tests for register_process method."""

    def test_register_process_adds_to_dict(self, daemon, mock_process):
        """Test that register_process adds the process to the tracking dict."""
        key = "test-repo#123"

        daemon.register_process(key, mock_process)

        assert key in daemon._running_processes
        assert daemon._running_processes[key] is mock_process

    def test_register_process_overwrites_existing(self, daemon, mock_process, mock_process_2):
        """Test that registering a new process overwrites the existing one."""
        key = "test-repo#123"

        daemon.register_process(key, mock_process)
        daemon.register_process(key, mock_process_2)

        assert daemon._running_processes[key] is mock_process_2

    def test_register_multiple_processes_different_keys(self, daemon, mock_process, mock_process_2):
        """Test that multiple processes can be registered with different keys."""
        key1 = "test-repo#123"
        key2 = "test-repo#456"

        daemon.register_process(key1, mock_process)
        daemon.register_process(key2, mock_process_2)

        assert key1 in daemon._running_processes
        assert key2 in daemon._running_processes
        assert daemon._running_processes[key1] is mock_process
        assert daemon._running_processes[key2] is mock_process_2


@pytest.mark.integration
class TestUnregisterProcess:
    """Tests for unregister_process method."""

    def test_unregister_process_removes_from_dict(self, daemon, mock_process):
        """Test that unregister_process removes the process from tracking dict."""
        key = "test-repo#123"
        daemon.register_process(key, mock_process)

        daemon.unregister_process(key)

        assert key not in daemon._running_processes

    def test_unregister_nonexistent_key_is_safe(self, daemon):
        """Test that unregistering a non-existent key doesn't raise an error."""
        # Should not raise any exception
        daemon.unregister_process("nonexistent-repo#999")

        assert "nonexistent-repo#999" not in daemon._running_processes

    def test_unregister_does_not_affect_other_processes(self, daemon, mock_process, mock_process_2):
        """Test that unregistering one process doesn't affect others."""
        key1 = "test-repo#123"
        key2 = "test-repo#456"
        daemon.register_process(key1, mock_process)
        daemon.register_process(key2, mock_process_2)

        daemon.unregister_process(key1)

        assert key1 not in daemon._running_processes
        assert key2 in daemon._running_processes
        assert daemon._running_processes[key2] is mock_process_2


@pytest.mark.integration
class TestKillProcess:
    """Tests for kill_process method."""

    def test_kill_process_kills_and_removes(self, daemon, mock_process):
        """Test that kill_process kills the process and removes it from dict."""
        key = "test-repo#123"
        daemon.register_process(key, mock_process)

        result = daemon.kill_process(key)

        assert result is True
        assert key not in daemon._running_processes
        mock_process.kill.assert_called_once()
        mock_process.wait.assert_called_once_with(timeout=5)

    def test_kill_process_returns_false_when_not_found(self, daemon):
        """Test that kill_process returns False when process key not found."""
        result = daemon.kill_process("nonexistent-repo#999")

        assert result is False

    def test_kill_process_handles_already_dead_process(self, daemon, mock_process):
        """Test that kill_process handles ProcessLookupError gracefully."""
        key = "test-repo#123"
        mock_process.kill.side_effect = ProcessLookupError("No such process")
        daemon.register_process(key, mock_process)

        result = daemon.kill_process(key)

        assert result is True  # Should still return True for already-dead process
        assert key not in daemon._running_processes

    def test_kill_process_handles_os_error(self, daemon, mock_process):
        """Test that kill_process handles OSError gracefully."""
        key = "test-repo#123"
        mock_process.kill.side_effect = OSError("Permission denied")
        daemon.register_process(key, mock_process)

        result = daemon.kill_process(key)

        assert result is False  # Should return False for other OS errors
        assert key not in daemon._running_processes

    def test_kill_process_does_not_affect_other_processes(self, daemon, mock_process, mock_process_2):
        """Test that killing one process doesn't affect others."""
        key1 = "test-repo#123"
        key2 = "test-repo#456"
        daemon.register_process(key1, mock_process)
        daemon.register_process(key2, mock_process_2)

        result = daemon.kill_process(key1)

        assert result is True
        assert key1 not in daemon._running_processes
        assert key2 in daemon._running_processes
        assert daemon._running_processes[key2] is mock_process_2
        # Only the first process should have been killed
        mock_process.kill.assert_called_once()
        mock_process_2.kill.assert_not_called()

    def test_kill_process_wrong_key_does_not_kill(self, daemon, mock_process):
        """Test that killing with wrong key doesn't kill any process."""
        daemon.register_process("correct-repo#123", mock_process)

        result = daemon.kill_process("wrong-repo#123")

        assert result is False
        assert "correct-repo#123" in daemon._running_processes
        mock_process.kill.assert_not_called()

    def test_kill_process_exact_key_matching(self, daemon, mock_process, mock_process_2):
        """Test that kill_process uses exact key matching."""
        # Register processes with similar but different keys
        daemon.register_process("repo#123", mock_process)
        daemon.register_process("repo#1234", mock_process_2)

        result = daemon.kill_process("repo#123")

        assert result is True
        # Only the exact key should be affected
        assert "repo#123" not in daemon._running_processes
        assert "repo#1234" in daemon._running_processes
        mock_process.kill.assert_called_once()
        mock_process_2.kill.assert_not_called()


@pytest.mark.integration
class TestProcessTrackingThreadSafety:
    """Tests for thread safety of process tracking methods."""

    def test_concurrent_register_unregister(self, daemon):
        """Test that concurrent register/unregister operations are safe."""
        import threading

        errors = []
        processes = [MagicMock(spec=subprocess.Popen) for _ in range(10)]

        def register_thread(idx):
            try:
                daemon.register_process(f"repo#{idx}", processes[idx])
            except Exception as e:
                errors.append(e)

        def unregister_thread(idx):
            try:
                daemon.unregister_process(f"repo#{idx}")
            except Exception as e:
                errors.append(e)

        threads = []
        for i in range(10):
            t1 = threading.Thread(target=register_thread, args=(i,))
            t2 = threading.Thread(target=unregister_thread, args=(i,))
            threads.extend([t1, t2])

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
