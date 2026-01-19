"""Unit tests for the setup validation module."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from src.setup.checks import SetupError, check_required_tools
from src.setup.project import (
    REQUIRED_COLUMN_NAMES,
    ValidationResult,
    validate_project_columns,
)


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
