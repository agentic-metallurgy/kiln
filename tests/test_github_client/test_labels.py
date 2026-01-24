"""Tests for GitHub client label-related functionality."""

import json
import subprocess
from unittest.mock import patch

import pytest


@pytest.mark.unit
class TestGetRepoLabels:
    """Tests for GitHubTicketClient.get_repo_labels()."""

    def test_get_repo_labels_returns_list(self, github_client):
        """Test fetching repository labels."""
        mock_response = json.dumps(
            [
                {"name": "bug"},
                {"name": "enhancement"},
                {"name": "researching"},
            ]
        )

        with patch.object(github_client, "_run_gh_command", return_value=mock_response):
            labels = github_client.get_repo_labels("owner/repo")

        assert labels == ["bug", "enhancement", "researching"]

    def test_get_repo_labels_empty_repo(self, github_client):
        """Test fetching labels from repo with no labels."""
        mock_response = json.dumps([])

        with patch.object(github_client, "_run_gh_command", return_value=mock_response):
            labels = github_client.get_repo_labels("owner/repo")

        assert labels == []

    def test_get_repo_labels_handles_error(self, github_client):
        """Test error handling when fetching labels fails."""
        with patch.object(
            github_client, "_run_gh_command", side_effect=subprocess.CalledProcessError(1, "gh")
        ):
            labels = github_client.get_repo_labels("owner/repo")

        assert labels == []


@pytest.mark.unit
class TestCreateRepoLabel:
    """Tests for GitHubTicketClient.create_repo_label()."""

    def test_create_repo_label_success(self, github_client):
        """Test creating a label successfully."""
        with patch.object(github_client, "_run_gh_command", return_value="") as mock_cmd:
            result = github_client.create_repo_label(
                "github.com/owner/repo", "researching", "Research in progress", "1D76DB"
            )

        assert result is True
        call_args = mock_cmd.call_args[0][0]
        assert "label" in call_args
        assert "create" in call_args
        assert "researching" in call_args
        assert "--repo" in call_args
        assert "https://github.com/owner/repo" in call_args
        assert "--description" in call_args
        assert "Research in progress" in call_args
        assert "--color" in call_args
        assert "1D76DB" in call_args

    def test_create_repo_label_no_description(self, github_client):
        """Test creating a label without description."""
        with patch.object(github_client, "_run_gh_command", return_value="") as mock_cmd:
            result = github_client.create_repo_label("owner/repo", "test-label")

        assert result is True
        call_args = mock_cmd.call_args[0][0]
        assert "--description" not in call_args
        assert "--color" not in call_args

    def test_create_repo_label_uses_force_flag(self, github_client):
        """Test that create uses --force to handle existing labels."""
        with patch.object(github_client, "_run_gh_command", return_value="") as mock_cmd:
            github_client.create_repo_label("owner/repo", "test-label")

        call_args = mock_cmd.call_args[0][0]
        assert "--force" in call_args

    def test_create_repo_label_handles_error(self, github_client):
        """Test error handling when label creation fails."""
        with patch.object(
            github_client, "_run_gh_command", side_effect=subprocess.CalledProcessError(1, "gh")
        ):
            result = github_client.create_repo_label("owner/repo", "test-label")

        assert result is False


@pytest.mark.unit
class TestAddLabel:
    """Tests for GitHubTicketClient.add_label()."""

    def test_add_label_success(self, github_client):
        """Test adding a label successfully."""
        with patch.object(github_client, "_run_gh_command", return_value="") as mock_cmd:
            github_client.add_label("github.com/owner/repo", 123, "researching")

        call_args = mock_cmd.call_args[0][0]
        assert "issue" in call_args
        assert "edit" in call_args
        assert "123" in call_args
        assert "--add-label" in call_args
        assert "researching" in call_args

    def test_add_label_creates_missing_label(self, github_client):
        """Test that add_label creates the label if it doesn't exist."""
        # First call fails with "label not found", second call succeeds
        error = subprocess.CalledProcessError(1, "gh")
        error.stderr = "label 'researching' not found"
        error.stdout = ""

        call_count = 0

        def mock_run_gh(args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First add_label attempt fails
                raise error
            return ""

        with (
            patch.object(github_client, "_run_gh_command", side_effect=mock_run_gh),
            patch.object(github_client, "create_repo_label", return_value=True) as mock_create,
        ):
            github_client.add_label("github.com/owner/repo", 123, "researching")

        # Verify create_repo_label was called
        mock_create.assert_called_once_with("github.com/owner/repo", "researching")
        # Verify add_label was retried
        assert call_count == 2

    def test_add_label_raises_when_label_creation_fails(self, github_client):
        """Test that add_label raises when label creation fails."""
        error = subprocess.CalledProcessError(1, "gh")
        error.stderr = "label 'researching' not found"
        error.stdout = ""

        with (
            patch.object(github_client, "_run_gh_command", side_effect=error),
            patch.object(github_client, "create_repo_label", return_value=False),
        ):
            with pytest.raises(RuntimeError, match="Failed to create label"):
                github_client.add_label("github.com/owner/repo", 123, "researching")

    def test_add_label_raises_on_other_errors(self, github_client):
        """Test that add_label re-raises non-label errors."""
        error = subprocess.CalledProcessError(1, "gh")
        error.stderr = "permission denied"
        error.stdout = ""

        with patch.object(github_client, "_run_gh_command", side_effect=error):
            with pytest.raises(subprocess.CalledProcessError):
                github_client.add_label("github.com/owner/repo", 123, "researching")

    def test_add_label_handles_does_not_exist_error(self, github_client):
        """Test that add_label handles 'does not exist' error variant."""
        error = subprocess.CalledProcessError(1, "gh")
        error.stderr = "label does not exist"
        error.stdout = ""

        call_count = 0

        def mock_run_gh(args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise error
            return ""

        with (
            patch.object(github_client, "_run_gh_command", side_effect=mock_run_gh),
            patch.object(github_client, "create_repo_label", return_value=True) as mock_create,
        ):
            github_client.add_label("github.com/owner/repo", 123, "test-label")

        mock_create.assert_called_once()


@pytest.mark.unit
class TestRemoveLabel:
    """Tests for GitHubTicketClient.remove_label() method."""

    def test_remove_label_success(self, github_client):
        """Test successfully removing a label."""
        with patch.object(github_client, "_run_gh_command", return_value="") as mock_cmd:
            github_client.remove_label("github.com/owner/repo", 123, "bug")

        call_args = mock_cmd.call_args[0][0]
        assert "issue" in call_args
        assert "edit" in call_args
        assert "123" in call_args
        assert "--remove-label" in call_args
        assert "bug" in call_args

    def test_remove_label_handles_missing_label(self, github_client):
        """Test that removing a non-existent label doesn't raise."""
        error = subprocess.CalledProcessError(1, "gh")
        error.stderr = "label not found"
        error.stdout = ""

        with patch.object(github_client, "_run_gh_command", side_effect=error):
            # Should not raise
            github_client.remove_label("github.com/owner/repo", 123, "nonexistent")


@pytest.mark.unit
class TestGetTicketLabels:
    """Tests for GitHubTicketClient.get_ticket_labels()."""

    def test_get_ticket_labels_returns_multiple_labels(self, github_client):
        """Test fetching issue labels returns a set of label names."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "labels": {
                            "nodes": [
                                {"name": "bug"},
                                {"name": "priority:high"},
                                {"name": "yolo"},
                            ]
                        }
                    }
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            labels = github_client.get_ticket_labels("owner/repo", 42)

        assert labels == {"bug", "priority:high", "yolo"}

    def test_get_ticket_labels_returns_empty_set_for_no_labels(self, github_client):
        """Test that an empty set is returned when issue has no labels."""
        mock_response = {"data": {"repository": {"issue": {"labels": {"nodes": []}}}}}

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            labels = github_client.get_ticket_labels("owner/repo", 42)

        assert labels == set()

    def test_get_ticket_labels_returns_empty_set_for_nonexistent_issue(self, github_client):
        """Test that empty set is returned when issue doesn't exist."""
        mock_response = {"data": {"repository": {"issue": None}}}

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            labels = github_client.get_ticket_labels("owner/repo", 99999)

        assert labels == set()

    def test_get_ticket_labels_returns_empty_set_on_api_error(self, github_client):
        """Test that API errors return empty set."""
        with patch.object(
            github_client, "_execute_graphql_query", side_effect=Exception("API error")
        ):
            labels = github_client.get_ticket_labels("owner/repo", 42)

        assert labels == set()

    def test_get_ticket_labels_makes_correct_api_call(self, github_client):
        """Test that the correct GraphQL query is made with proper structure."""
        mock_response = {
            "data": {"repository": {"issue": {"labels": {"nodes": [{"name": "test"}]}}}}
        }

        with patch.object(
            github_client, "_execute_graphql_query", return_value=mock_response
        ) as mock_query:
            github_client.get_ticket_labels("test-owner/test-repo", 123)

            call_args = mock_query.call_args
            query = call_args[0][0]
            variables = call_args[0][1]

            assert "repository(owner: $owner, name: $repo)" in query
            assert "issue(number: $issueNumber)" in query
            assert "labels(first: 100)" in query
            assert "nodes" in query
            assert "name" in query
            assert variables["owner"] == "test-owner"
            assert variables["repo"] == "test-repo"
            assert variables["issueNumber"] == 123

    def test_get_ticket_labels_handles_null_label_nodes(self, github_client):
        """Test handling of null entries in label nodes."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "labels": {
                            "nodes": [{"name": "valid-label"}, None, {"name": "another-label"}]
                        }
                    }
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            labels = github_client.get_ticket_labels("owner/repo", 42)

        assert labels == {"valid-label", "another-label"}
