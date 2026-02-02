"""Unit tests for the setup validation module."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from src.setup.checks import (
    SetupError,
    check_required_tools,
    configure_git_credential_helper,
    get_hostnames_from_project_urls,
    is_restricted_directory,
    validate_working_directory,
)
from src.setup.project import (
    GITHUB_DEFAULT_COLUMNS,
    REQUIRED_COLUMN_NAMES,
    ValidationResult,
    validate_project_columns,
)


@pytest.mark.unit
class TestIsRestrictedDirectory:
    """Tests for is_restricted_directory()."""

    def test_root_directory_is_restricted(self, tmp_path):
        """Test that root directory (/) is restricted."""
        from pathlib import Path

        assert is_restricted_directory(Path("/")) is True

    def test_users_directory_is_restricted(self):
        """Test that /Users/ is restricted."""
        from pathlib import Path

        assert is_restricted_directory(Path("/Users")) is True
        assert is_restricted_directory(Path("/Users/")) is True

    def test_home_directory_linux_is_restricted(self, tmp_path, monkeypatch):
        """Test that /home/<user> directory is restricted (Linux-style)."""
        from pathlib import Path

        # On macOS, /home resolves to /System/Volumes/Data/home which doesn't
        # match our pattern. We test the Linux-style home by mocking Path.home().
        # The key behavior is that the user's home directory is restricted,
        # regardless of whether it's /Users/<user> or /home/<user>.
        mock_home = tmp_path / "home" / "testuser"
        mock_home.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: mock_home)

        # User's home directory should be restricted
        assert is_restricted_directory(mock_home) is True

        # Subdirectory of home should be allowed
        subdir = mock_home / "projects"
        subdir.mkdir()
        assert is_restricted_directory(subdir) is False

    def test_user_home_directory_is_restricted(self, tmp_path, monkeypatch):
        """Test that user's home directory is restricted."""
        from pathlib import Path

        # Mock Path.home() to return a controlled path
        mock_home = tmp_path / "mockhome"
        mock_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: mock_home)

        assert is_restricted_directory(mock_home) is True

    def test_subdirectory_of_home_is_allowed(self, tmp_path, monkeypatch):
        """Test that subdirectories of home are allowed."""
        from pathlib import Path

        # Mock Path.home() to return a controlled path
        mock_home = tmp_path / "mockhome"
        mock_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: mock_home)

        subdir = mock_home / "projects"
        subdir.mkdir()

        assert is_restricted_directory(subdir) is False

    def test_deeply_nested_directory_is_allowed(self, tmp_path, monkeypatch):
        """Test that deeply nested directories are allowed."""
        from pathlib import Path

        mock_home = tmp_path / "mockhome"
        mock_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: mock_home)

        deep_dir = mock_home / "projects" / "kiln" / "workspace"
        deep_dir.mkdir(parents=True)

        assert is_restricted_directory(deep_dir) is False

    def test_uses_cwd_when_no_directory_provided(self, tmp_path, monkeypatch):
        """Test that current working directory is used when none provided."""
        monkeypatch.chdir(tmp_path)
        # tmp_path is not a restricted directory
        assert is_restricted_directory() is False

    def test_non_home_top_level_directory_is_allowed(self):
        """Test that non-restricted top-level directories are allowed."""
        from pathlib import Path

        # /tmp, /var, etc. should be allowed
        assert is_restricted_directory(Path("/tmp")) is False
        assert is_restricted_directory(Path("/var")) is False


@pytest.mark.unit
class TestValidateWorkingDirectory:
    """Tests for validate_working_directory()."""

    def test_raises_for_root_directory(self):
        """Test that SetupError is raised for root directory."""
        from pathlib import Path

        with pytest.raises(SetupError) as exc_info:
            validate_working_directory(Path("/"))

        error = str(exc_info.value)
        assert "Cannot run kiln" in error
        assert "not allowed" in error
        assert "mkdir" in error

    def test_raises_for_home_directory(self, tmp_path, monkeypatch):
        """Test that SetupError is raised for home directory."""
        from pathlib import Path

        mock_home = tmp_path / "mockhome"
        mock_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: mock_home)

        with pytest.raises(SetupError) as exc_info:
            validate_working_directory(mock_home)

        error = str(exc_info.value)
        assert "Cannot run kiln" in error
        assert str(mock_home) in error

    def test_no_error_for_valid_directory(self, tmp_path, monkeypatch):
        """Test that no error is raised for valid directory."""
        from pathlib import Path

        mock_home = tmp_path / "mockhome"
        mock_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: mock_home)

        valid_dir = mock_home / "projects"
        valid_dir.mkdir()

        # Should not raise
        validate_working_directory(valid_dir)

    def test_error_includes_recommendation(self):
        """Test that error message includes recommendation to create directory."""
        from pathlib import Path

        with pytest.raises(SetupError) as exc_info:
            validate_working_directory(Path("/"))

        error = str(exc_info.value)
        assert "mkdir" in error
        assert "kiln-workspace" in error


@pytest.mark.unit
class TestCheckRequiredTools:
    """Tests for check_required_tools()."""

    def test_all_tools_present(self):
        """Test that no error is raised when all tools are present."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            # Should not raise
            check_required_tools()
            assert mock_run.call_count == 2

    def test_gh_cli_missing(self):
        """Test error when gh CLI is missing."""

        def side_effect(args, **kwargs):
            if args[0] == "gh":
                raise FileNotFoundError()
            return MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=side_effect):
            with pytest.raises(SetupError) as exc_info:
                check_required_tools()

            assert "gh CLI not found" in str(exc_info.value)
            assert "https://cli.github.com/" in str(exc_info.value)

    def test_claude_cli_missing(self):
        """Test error when claude CLI is missing."""

        def side_effect(args, **kwargs):
            if args[0] == "claude":
                raise FileNotFoundError()
            return MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=side_effect):
            with pytest.raises(SetupError) as exc_info:
                check_required_tools()

            assert "claude CLI not found" in str(exc_info.value)
            assert "anthropic.com" in str(exc_info.value)

    def test_both_tools_missing(self):
        """Test error includes both tools when both are missing."""
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            with pytest.raises(SetupError) as exc_info:
                check_required_tools()

            error = str(exc_info.value)
            assert "gh CLI not found" in error
            assert "claude CLI not found" in error

    def test_gh_cli_error(self):
        """Test error when gh CLI returns an error."""

        def side_effect(args, **kwargs):
            if args[0] == "gh":
                raise subprocess.CalledProcessError(1, "gh", stderr=b"gh: command failed")
            return MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=side_effect):
            with pytest.raises(SetupError) as exc_info:
                check_required_tools()

            assert "gh CLI error" in str(exc_info.value)


@pytest.mark.unit
class TestConfigureGitCredentialHelper:
    """Tests for configure_git_credential_helper()."""

    def test_configures_github_com_by_default(self):
        """Test that github.com is configured by default."""
        with patch("src.setup.checks.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            configure_git_credential_helper()

            # Should be called twice: once to clear, once to add
            assert mock_run.call_count == 2

            # First call clears existing helper
            first_call = mock_run.call_args_list[0]
            assert first_call[0][0] == [
                "git",
                "config",
                "--global",
                "credential.https://github.com.helper",
                "",
            ]

            # Second call adds gh as helper
            second_call = mock_run.call_args_list[1]
            assert second_call[0][0] == [
                "git",
                "config",
                "--global",
                "--add",
                "credential.https://github.com.helper",
                "!gh auth git-credential",
            ]

    def test_configures_custom_hostname(self):
        """Test that custom hostnames are configured correctly."""
        with patch("src.setup.checks.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            configure_git_credential_helper("ghes.company.com")

            # Should use the custom hostname
            first_call = mock_run.call_args_list[0]
            assert "credential.https://ghes.company.com.helper" in first_call[0][0]

            second_call = mock_run.call_args_list[1]
            assert "credential.https://ghes.company.com.helper" in second_call[0][0]

    def test_handles_subprocess_error_gracefully(self):
        """Test that subprocess errors are logged but don't raise."""
        with patch("src.setup.checks.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, "git")

            with patch("src.setup.checks.logger") as mock_logger:
                # Should not raise
                configure_git_credential_helper("github.com")
                mock_logger.warning.assert_called_once()
                assert "Could not configure" in mock_logger.warning.call_args[0][0]

    def test_clear_does_not_fail_on_missing_config(self):
        """Test that clearing missing config doesn't fail startup."""
        def side_effect(args, **kwargs):
            # First call (clear) fails - no existing config
            if args[-1] == "":
                raise subprocess.CalledProcessError(1, "git")
            # Second call (add) succeeds
            return MagicMock(returncode=0)

        with patch("src.setup.checks.subprocess.run", side_effect=side_effect):
            with patch("src.setup.checks.logger") as mock_logger:
                # Should log warning but handle gracefully
                configure_git_credential_helper()
                # First call with check=False shouldn't raise even on error
                # but the side_effect still raises, so warning should be logged
                mock_logger.warning.assert_called()


@pytest.mark.unit
class TestGetHostnamesFromProjectUrls:
    """Tests for get_hostnames_from_project_urls()."""

    def test_extracts_github_com(self):
        """Test extracting github.com from standard URL."""
        urls = ["https://github.com/orgs/test/projects/1"]
        result = get_hostnames_from_project_urls(urls)
        assert result == {"github.com"}

    def test_extracts_ghes_hostname(self):
        """Test extracting GHES hostname."""
        urls = ["https://ghes.company.com/orgs/test/projects/1"]
        result = get_hostnames_from_project_urls(urls)
        assert result == {"ghes.company.com"}

    def test_extracts_multiple_unique_hostnames(self):
        """Test extracting multiple unique hostnames."""
        urls = [
            "https://github.com/orgs/test/projects/1",
            "https://ghes.company.com/orgs/test/projects/2",
            "https://github.example.org/orgs/test/projects/3",
        ]
        result = get_hostnames_from_project_urls(urls)
        assert result == {"github.com", "ghes.company.com", "github.example.org"}

    def test_deduplicates_hostnames(self):
        """Test that duplicate hostnames are deduplicated."""
        urls = [
            "https://github.com/orgs/test/projects/1",
            "https://github.com/orgs/other/projects/2",
            "https://github.com/orgs/third/projects/3",
        ]
        result = get_hostnames_from_project_urls(urls)
        assert result == {"github.com"}

    def test_empty_list_returns_github_com(self):
        """Test that empty list defaults to github.com."""
        result = get_hostnames_from_project_urls([])
        assert result == {"github.com"}

    def test_malformed_url_defaults_to_github_com(self):
        """Test that malformed URLs default to github.com."""
        urls = ["not-a-url", "just-some-text"]
        result = get_hostnames_from_project_urls(urls)
        assert result == {"github.com"}

    def test_mixed_valid_and_invalid_urls(self):
        """Test mixed valid and invalid URLs."""
        urls = [
            "https://ghes.company.com/orgs/test/projects/1",
            "not-a-url",
            "https://github.com/orgs/test/projects/2",
        ]
        result = get_hostnames_from_project_urls(urls)
        assert result == {"ghes.company.com", "github.com"}

    def test_http_url_also_works(self):
        """Test that http (non-https) URLs are also parsed."""
        urls = ["http://github.internal.com/orgs/test/projects/1"]
        result = get_hostnames_from_project_urls(urls)
        assert result == {"github.internal.com"}

    def test_url_with_port(self):
        """Test URL with port number."""
        urls = ["https://github.local:8443/orgs/test/projects/1"]
        result = get_hostnames_from_project_urls(urls)
        assert result == {"github.local:8443"}


@pytest.mark.unit
class TestValidateProjectColumns:
    """Tests for validate_project_columns()."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock GitHubTicketClient."""
        client = MagicMock()
        return client

    def test_only_backlog_creates_columns(self, mock_client):
        """Test that columns are created when only Backlog exists."""
        mock_client.get_board_metadata.return_value = {
            "status_field_id": "field_123",
            "status_options": {"Backlog": "opt_backlog"},
        }

        result = validate_project_columns(mock_client, "https://github.com/orgs/test/projects/1")

        assert result.action == "created"
        assert "Research" in result.message
        mock_client.update_status_field_options.assert_called_once()

        # Verify the options passed
        call_args = mock_client.update_status_field_options.call_args
        options = call_args[0][1]
        option_names = [opt["name"] for opt in options]
        assert option_names == REQUIRED_COLUMN_NAMES

    def test_all_columns_correct_order(self, mock_client):
        """Test no action when all columns present in correct order."""
        # The status_options dict preserves insertion order in Python 3.7+
        # We need to simulate the order matching REQUIRED_COLUMN_NAMES
        ordered_options = {}
        for name in REQUIRED_COLUMN_NAMES:
            ordered_options[name] = f"opt_{name}"

        mock_client.get_board_metadata.return_value = {
            "status_field_id": "field_123",
            "status_options": ordered_options,
        }

        result = validate_project_columns(mock_client, "https://github.com/orgs/test/projects/1")

        assert result.action == "ok"
        mock_client.update_status_field_options.assert_not_called()

    def test_all_columns_wrong_order_reorders(self, mock_client):
        """Test reordering when all columns present but wrong order."""
        # Reverse order
        reversed_options = {}
        for name in reversed(REQUIRED_COLUMN_NAMES):
            reversed_options[name] = f"opt_{name}"

        mock_client.get_board_metadata.return_value = {
            "status_field_id": "field_123",
            "status_options": reversed_options,
        }

        result = validate_project_columns(mock_client, "https://github.com/orgs/test/projects/1")

        assert result.action == "reordered"
        assert "reordered" in result.message.lower()
        mock_client.update_status_field_options.assert_called_once()

        # Verify the options are in correct order with IDs
        call_args = mock_client.update_status_field_options.call_args
        options = call_args[0][1]
        option_names = [opt["name"] for opt in options]
        assert option_names == REQUIRED_COLUMN_NAMES
        # Each should have an ID
        for opt in options:
            assert "id" in opt

    def test_extra_columns_raises_error(self, mock_client):
        """Test error when extra columns exist."""
        options = {name: f"opt_{name}" for name in REQUIRED_COLUMN_NAMES}
        options["CustomColumn"] = "opt_custom"

        mock_client.get_board_metadata.return_value = {
            "status_field_id": "field_123",
            "status_options": options,
        }

        with pytest.raises(SetupError) as exc_info:
            validate_project_columns(mock_client, "https://github.com/orgs/test/projects/1")

        error = str(exc_info.value)
        assert "not compatible" in error
        assert "CustomColumn" in error

    def test_missing_columns_with_extras_raises_error(self, mock_client):
        """Test error when missing required columns but has extras."""
        mock_client.get_board_metadata.return_value = {
            "status_field_id": "field_123",
            "status_options": {
                "Backlog": "opt_backlog",
                "Prepare": "opt_prepare",  # Deprecated
            },
        }

        with pytest.raises(SetupError) as exc_info:
            validate_project_columns(mock_client, "https://github.com/orgs/test/projects/1")

        error = str(exc_info.value)
        assert "not compatible" in error
        # Should mention the extra column
        assert "Prepare" in error or "Extra columns" in error

    def test_missing_status_field_raises_error(self, mock_client):
        """Test error when Status field not found."""
        mock_client.get_board_metadata.return_value = {
            "status_field_id": None,
            "status_options": {},
        }

        with pytest.raises(SetupError) as exc_info:
            validate_project_columns(mock_client, "https://github.com/orgs/test/projects/1")

        assert "Could not find Status field" in str(exc_info.value)

    def test_error_message_includes_instructions(self, mock_client):
        """Test that error message includes instructions for fixing."""
        mock_client.get_board_metadata.return_value = {
            "status_field_id": "field_123",
            "status_options": {"Backlog": "opt_backlog", "Custom": "opt_custom"},
        }

        with pytest.raises(SetupError) as exc_info:
            validate_project_columns(mock_client, "https://github.com/orgs/test/projects/1")

        error = str(exc_info.value)
        # Should include the project URL
        assert "https://github.com/orgs/test/projects/1" in error
        # Should include instruction options
        assert "Option 1" in error
        assert "Option 2" in error
        # Should list required columns
        assert "Backlog" in error
        assert "Research" in error
        assert "Done" in error

    def test_validation_result_dataclass(self):
        """Test ValidationResult dataclass."""
        result = ValidationResult(
            project_url="https://github.com/orgs/test/projects/1",
            action="ok",
            message="Test message",
        )
        assert result.project_url == "https://github.com/orgs/test/projects/1"
        assert result.action == "ok"
        assert result.message == "Test message"

    def test_github_defaults_replaces_columns(self, mock_client):
        """Test that GitHub default columns are replaced with Kiln columns."""
        # Simulate GitHub defaults - order preserved by dict in Python 3.7+
        mock_client.get_board_metadata.return_value = {
            "status_field_id": "field_123",
            "status_options": {
                "Backlog": "opt_1",
                "Ready": "opt_2",
                "In progress": "opt_3",
                "In review": "opt_4",
                "Done": "opt_5",
            },
        }
        mock_client.get_board_items.return_value = []  # No items to migrate

        result = validate_project_columns(
            mock_client, "https://github.com/orgs/test/projects/1"
        )

        assert result.action == "replaced"
        assert "Replaced GitHub default columns" in result.message
        mock_client.update_status_field_options.assert_called_once()

        # Verify the options passed include all 6 Kiln columns
        call_args = mock_client.update_status_field_options.call_args
        options = call_args[0][1]
        option_names = [opt["name"] for opt in options]
        assert option_names == REQUIRED_COLUMN_NAMES

    def test_github_defaults_migrates_items_to_backlog(self, mock_client):
        """Test that items in deprecated statuses are migrated to Backlog."""
        mock_client.get_board_metadata.return_value = {
            "status_field_id": "field_123",
            "status_options": {
                "Backlog": "opt_1",
                "Ready": "opt_2",
                "In progress": "opt_3",
                "In review": "opt_4",
                "Done": "opt_5",
            },
        }

        # Mock items in deprecated statuses
        from src.interfaces import TicketItem

        mock_items = [
            TicketItem(
                item_id="item1",
                board_url="https://github.com/orgs/test/projects/1",
                ticket_id=1,
                repo="github.com/test/repo",
                status="Ready",
                title="Test 1",
                labels=set(),
                state="OPEN",
            ),
            TicketItem(
                item_id="item2",
                board_url="https://github.com/orgs/test/projects/1",
                ticket_id=2,
                repo="github.com/test/repo",
                status="In progress",
                title="Test 2",
                labels=set(),
                state="OPEN",
            ),
            TicketItem(
                item_id="item3",
                board_url="https://github.com/orgs/test/projects/1",
                ticket_id=3,
                repo="github.com/test/repo",
                status="Backlog",
                title="Test 3",
                labels=set(),
                state="OPEN",
            ),
        ]
        mock_client.get_board_items.return_value = mock_items

        result = validate_project_columns(
            mock_client, "https://github.com/orgs/test/projects/1"
        )

        assert result.action == "replaced"
        assert "2 item(s) moved to Backlog" in result.message
        # Verify update_item_status called for items in deprecated statuses
        assert mock_client.update_item_status.call_count == 2

    def test_partial_github_defaults_raises_error(self, mock_client):
        """Test that partial GitHub defaults (e.g., missing one column) still errors."""
        # Only 4 of the 5 GitHub defaults - missing "In Review"
        mock_client.get_board_metadata.return_value = {
            "status_field_id": "field_123",
            "status_options": {
                "Backlog": "opt_1",
                "Ready": "opt_2",
                "In progress": "opt_3",
                "Done": "opt_5",
            },
        }

        with pytest.raises(SetupError):
            validate_project_columns(
                mock_client, "https://github.com/orgs/test/projects/1"
            )

    def test_github_defaults_empty_project_no_items(self, mock_client):
        """Test GitHub defaults with no items to migrate (fresh project)."""
        mock_client.get_board_metadata.return_value = {
            "status_field_id": "field_123",
            "status_options": {
                "Backlog": "opt_1",
                "Ready": "opt_2",
                "In progress": "opt_3",
                "In review": "opt_4",
                "Done": "opt_5",
            },
        }
        mock_client.get_board_items.return_value = []  # Empty project

        result = validate_project_columns(
            mock_client, "https://github.com/orgs/test/projects/1"
        )

        assert result.action == "replaced"
        # Message should NOT contain migration count if no items migrated
        assert "item(s) moved to Backlog" not in result.message
        # update_item_status should not have been called
        mock_client.update_item_status.assert_not_called()

    def test_github_default_columns_constant(self):
        """Test that GITHUB_DEFAULT_COLUMNS has the correct values."""
        expected = frozenset(
            {"Backlog", "Ready", "In progress", "In review", "Done"}
        )
        assert expected == GITHUB_DEFAULT_COLUMNS
        assert isinstance(GITHUB_DEFAULT_COLUMNS, frozenset)


@pytest.mark.unit
class TestUpdateStatusFieldOptions:
    """Tests for GitHubTicketClient.update_status_field_options()."""

    def test_update_status_field_options_calls_graphql(self):
        """Test that update_status_field_options executes GraphQL mutation."""
        from src.ticket_clients.github import GitHubTicketClient

        client = GitHubTicketClient(tokens={"github.com": "test-token"})

        with patch.object(client, "_execute_graphql_query") as mock_query:
            options = [
                {"name": "Backlog", "color": "GRAY", "description": "Test"},
                {"name": "Done", "color": "GREEN", "description": "Complete"},
            ]
            client.update_status_field_options("field_123", options)

            mock_query.assert_called_once()
            call_args = mock_query.call_args
            # Check mutation was called with correct field ID
            assert call_args[0][1]["fieldId"] == "field_123"
            # Check options were passed correctly
            passed_options = call_args[0][1]["options"]
            assert len(passed_options) == 2
            # ProjectV2SingleSelectFieldOptionInput only accepts name, color, description
            assert "id" not in passed_options[0]
            assert "id" not in passed_options[1]
            assert passed_options[1]["name"] == "Done"

    def test_update_status_field_options_with_hostname(self):
        """Test that hostname is passed correctly."""
        from src.ticket_clients.github import GitHubTicketClient

        client = GitHubTicketClient(tokens={"github.mycompany.com": "test-token"})

        with patch.object(client, "_execute_graphql_query") as mock_query:
            options = [{"name": "Test", "color": "GRAY", "description": ""}]
            client.update_status_field_options(
                "field_123", options, hostname="github.mycompany.com"
            )

            mock_query.assert_called_once()
            call_args = mock_query.call_args
            assert call_args[1]["hostname"] == "github.mycompany.com"
