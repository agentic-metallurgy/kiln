"""Tests for GitHub client issue-related functionality."""

from unittest.mock import patch

import pytest


@pytest.mark.unit
class TestGetIssueBody:
    """Tests for GitHubTicketClient.get_ticket_body()."""

    def test_get_ticket_body_returns_body_text(self, github_client):
        """Test fetching issue body returns the body text."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {"body": "This is the issue description.\n\nWith multiple lines."}
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            body = github_client.get_ticket_body("owner/repo", 42)

        assert body == "This is the issue description.\n\nWith multiple lines."

    def test_get_ticket_body_returns_none_for_nonexistent_issue(self, github_client):
        """Test that None is returned when issue doesn't exist."""
        mock_response = {"data": {"repository": {"issue": None}}}

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            body = github_client.get_ticket_body("owner/repo", 99999)

        assert body is None

    def test_get_ticket_body_returns_none_on_empty_body(self, github_client):
        """Test handling of issue with no body."""
        mock_response = {"data": {"repository": {"issue": {"body": None}}}}

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            body = github_client.get_ticket_body("owner/repo", 42)

        assert body is None

    def test_get_ticket_body_returns_empty_string(self, github_client):
        """Test handling of issue with empty string body."""
        mock_response = {"data": {"repository": {"issue": {"body": ""}}}}

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            body = github_client.get_ticket_body("owner/repo", 42)

        assert body == ""

    def test_get_ticket_body_handles_api_error(self, github_client):
        """Test that API errors return None."""
        with patch.object(
            github_client, "_execute_graphql_query", side_effect=Exception("API error")
        ):
            body = github_client.get_ticket_body("owner/repo", 42)

        assert body is None

    def test_get_ticket_body_makes_correct_api_call(self, github_client):
        """Test that the correct GraphQL query is made."""
        mock_response = {"data": {"repository": {"issue": {"body": "Test body"}}}}

        with patch.object(
            github_client, "_execute_graphql_query", return_value=mock_response
        ) as mock_query:
            github_client.get_ticket_body("test-owner/test-repo", 123)

            call_args = mock_query.call_args
            query = call_args[0][0]
            variables = call_args[0][1]

            assert "repository(owner: $owner, name: $repo)" in query
            assert "issue(number: $issueNumber)" in query
            assert "body" in query
            assert variables["owner"] == "test-owner"
            assert variables["repo"] == "test-repo"
            assert variables["issueNumber"] == 123


@pytest.mark.unit
class TestGetLastProjectStatusActor:
    """Tests for GitHubTicketClient.get_last_status_actor()."""

    def test_get_last_status_actor_returns_actor(self, github_client):
        """Test that the actor from the most recent timeline event is returned."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "timelineItems": {
                            "nodes": [
                                {
                                    "__typename": "AddedToProjectV2Event",
                                    "actor": {"login": "user1"},
                                    "createdAt": "2024-01-10T10:00:00Z",
                                },
                                {
                                    "__typename": "ProjectV2ItemStatusChangedEvent",
                                    "actor": {"login": "user2"},
                                    "createdAt": "2024-01-15T10:00:00Z",
                                },
                            ]
                        }
                    }
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            actor = github_client.get_last_status_actor("owner/repo", 42)

        # Should return the last actor (most recent is last in list since we used 'last: 10')
        assert actor == "user2"

    def test_get_last_status_actor_returns_none_when_no_events(self, github_client):
        """Test that None is returned when there are no timeline events."""
        mock_response = {"data": {"repository": {"issue": {"timelineItems": {"nodes": []}}}}}

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            actor = github_client.get_last_status_actor("owner/repo", 42)

        assert actor is None

    def test_get_last_status_actor_returns_none_on_api_error(self, github_client):
        """Test that None is returned and error is logged on API failure."""
        with patch.object(
            github_client, "_execute_graphql_query", side_effect=Exception("API error")
        ):
            actor = github_client.get_last_status_actor("owner/repo", 42)

        assert actor is None

    def test_get_last_status_actor_returns_none_for_nonexistent_issue(self, github_client):
        """Test that None is returned when issue doesn't exist."""
        mock_response = {"data": {"repository": {"issue": None}}}

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            actor = github_client.get_last_status_actor("owner/repo", 99999)

        assert actor is None

    def test_get_last_status_actor_skips_events_without_actor(self, github_client):
        """Test that events without actor field are skipped."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "timelineItems": {
                            "nodes": [
                                {
                                    "__typename": "ProjectV2ItemStatusChangedEvent",
                                    "actor": {"login": "valid_user"},
                                    "createdAt": "2024-01-10T10:00:00Z",
                                },
                                {
                                    "__typename": "ProjectV2ItemStatusChangedEvent",
                                    "actor": None,  # No actor (e.g., deleted user)
                                    "createdAt": "2024-01-15T10:00:00Z",
                                },
                            ]
                        }
                    }
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            actor = github_client.get_last_status_actor("owner/repo", 42)

        # Should return the previous valid actor since the most recent has None
        assert actor == "valid_user"

    def test_get_last_status_actor_makes_correct_api_call(self, github_client):
        """Test that the correct GraphQL query is made."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "timelineItems": {
                            "nodes": [
                                {
                                    "__typename": "AddedToProjectV2Event",
                                    "actor": {"login": "testuser"},
                                    "createdAt": "2024-01-15T10:00:00Z",
                                }
                            ]
                        }
                    }
                }
            }
        }

        with patch.object(
            github_client, "_execute_graphql_query", return_value=mock_response
        ) as mock_query:
            github_client.get_last_status_actor("test-owner/test-repo", 123)

            call_args = mock_query.call_args
            query = call_args[0][0]
            variables = call_args[0][1]

            # Verify query structure
            assert "repository(owner: $owner, name: $repo)" in query
            assert "issue(number: $issueNumber)" in query
            assert "timelineItems" in query
            assert "ADDED_TO_PROJECT_V2_EVENT" in query
            assert "PROJECT_V2_ITEM_STATUS_CHANGED_EVENT" in query
            assert "actor" in query
            assert "login" in query

            # Verify variables
            assert variables["owner"] == "test-owner"
            assert variables["repo"] == "test-repo"
            assert variables["issueNumber"] == 123


@pytest.mark.unit
class TestGetLabelActor:
    """Tests for GitHubTicketClient.get_label_actor() method."""

    def test_get_label_actor_returns_actor(self, github_client):
        """Test that the actor who added a specific label is returned."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "timelineItems": {
                            "nodes": [
                                {
                                    "actor": {"login": "user1"},
                                    "label": {"name": "bug"},
                                    "createdAt": "2024-01-15T09:00:00Z",
                                },
                                {
                                    "actor": {"login": "user2"},
                                    "label": {"name": "yolo"},
                                    "createdAt": "2024-01-15T10:00:00Z",
                                },
                            ]
                        }
                    }
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            actor = github_client.get_label_actor("owner/repo", 42, "yolo")

        assert actor == "user2"

    def test_get_label_actor_returns_none_when_label_not_found(self, github_client):
        """Test that None is returned when the label was never added."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "timelineItems": {
                            "nodes": [
                                {
                                    "actor": {"login": "user1"},
                                    "label": {"name": "bug"},
                                    "createdAt": "2024-01-15T09:00:00Z",
                                },
                            ]
                        }
                    }
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            actor = github_client.get_label_actor("owner/repo", 42, "yolo")

        assert actor is None

    def test_get_label_actor_returns_none_when_no_events(self, github_client):
        """Test that None is returned when there are no label events."""
        mock_response = {"data": {"repository": {"issue": {"timelineItems": {"nodes": []}}}}}

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            actor = github_client.get_label_actor("owner/repo", 42, "yolo")

        assert actor is None

    def test_get_label_actor_returns_none_on_api_error(self, github_client):
        """Test that None is returned on API error."""
        with patch.object(
            github_client, "_execute_graphql_query", side_effect=Exception("API error")
        ):
            actor = github_client.get_label_actor("owner/repo", 42, "yolo")

        assert actor is None

    def test_get_label_actor_returns_most_recent(self, github_client):
        """Test that the most recent addition of the label is returned."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "timelineItems": {
                            "nodes": [
                                {
                                    "actor": {"login": "user1"},
                                    "label": {"name": "yolo"},
                                    "createdAt": "2024-01-15T09:00:00Z",
                                },
                                {
                                    "actor": {"login": "user2"},
                                    "label": {"name": "yolo"},
                                    "createdAt": "2024-01-15T10:00:00Z",
                                },
                            ]
                        }
                    }
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            actor = github_client.get_label_actor("owner/repo", 42, "yolo")

        # Should return the most recent (last in list)
        assert actor == "user2"
