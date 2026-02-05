"""Tests for GitHub client actor detection functionality.

Tests for get_last_status_actor() which detects who last changed an issue's
project status. This is critical for the authorization flow to determine
if the kiln owner should act on an issue.
"""

from unittest.mock import patch

import pytest


@pytest.mark.unit
class TestGetLastStatusActor:
    """Tests for GitHubTicketClient.get_last_status_actor() method."""

    def test_prioritizes_status_change_over_add_event(self, github_client):
        """When both event types exist, status change actor should be returned.

        Scenario: User A adds issue to project, User B changes status.
        Expected: Should return User B (the status changer).
        """
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "timelineItems": {
                            "nodes": [
                                # User A added issue to project (older)
                                {
                                    "__typename": "AddedToProjectV2Event",
                                    "actor": {"login": "user-a"},
                                    "createdAt": "2024-01-01T10:00:00Z",
                                },
                                # User B changed status (newer)
                                {
                                    "__typename": "ProjectV2ItemStatusChangedEvent",
                                    "actor": {"login": "user-b"},
                                    "createdAt": "2024-01-02T10:00:00Z",
                                },
                            ]
                        }
                    }
                }
            }
        }

        with patch.object(
            github_client, "_execute_graphql_query", return_value=mock_response
        ):
            result = github_client.get_last_status_actor("github.com/owner/repo", 123)

        assert result == "user-b"

    def test_prioritizes_status_change_over_newer_add_event(self, github_client):
        """Status change should be prioritized over add event even if add is more recent.

        Scenario: User A changes status, then User B adds same issue to another project.
        The status change event should be returned since we care about who changed the
        status, not who added it to a project.
        """
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "timelineItems": {
                            # GitHub returns events in chronological order (oldest first)
                            "nodes": [
                                # Status change event (older)
                                {
                                    "__typename": "ProjectV2ItemStatusChangedEvent",
                                    "actor": {"login": "status-changer"},
                                    "createdAt": "2024-01-01T09:00:00Z",
                                },
                                # Add event (newer - but should be ignored for status actor)
                                {
                                    "__typename": "AddedToProjectV2Event",
                                    "actor": {"login": "adder"},
                                    "createdAt": "2024-01-01T10:00:00Z",
                                },
                            ]
                        }
                    }
                }
            }
        }

        with patch.object(
            github_client, "_execute_graphql_query", return_value=mock_response
        ):
            result = github_client.get_last_status_actor("github.com/owner/repo", 123)

        # Even though add event is more recent, we return status change actor
        assert result == "status-changer"

    def test_falls_back_to_add_event_when_no_status_change(self, github_client):
        """When only ADDED_TO_PROJECT_V2_EVENT exists, should return that actor.

        Scenario: Issue was added to project with initial status but never moved.
        """
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "timelineItems": {
                            "nodes": [
                                {
                                    "__typename": "AddedToProjectV2Event",
                                    "actor": {"login": "project-adder"},
                                    "createdAt": "2024-01-01T10:00:00Z",
                                },
                            ]
                        }
                    }
                }
            }
        }

        with patch.object(
            github_client, "_execute_graphql_query", return_value=mock_response
        ):
            result = github_client.get_last_status_actor("github.com/owner/repo", 123)

        assert result == "project-adder"

    def test_returns_most_recent_status_change(self, github_client):
        """Multiple status changes should return the most recent actor.

        Scenario: Issue moved multiple times between statuses.
        """
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "timelineItems": {
                            "nodes": [
                                # Oldest status change
                                {
                                    "__typename": "ProjectV2ItemStatusChangedEvent",
                                    "actor": {"login": "first-mover"},
                                    "createdAt": "2024-01-01T10:00:00Z",
                                },
                                # Middle status change
                                {
                                    "__typename": "ProjectV2ItemStatusChangedEvent",
                                    "actor": {"login": "second-mover"},
                                    "createdAt": "2024-01-02T10:00:00Z",
                                },
                                # Most recent status change (should be returned)
                                {
                                    "__typename": "ProjectV2ItemStatusChangedEvent",
                                    "actor": {"login": "last-mover"},
                                    "createdAt": "2024-01-03T10:00:00Z",
                                },
                            ]
                        }
                    }
                }
            }
        }

        with patch.object(
            github_client, "_execute_graphql_query", return_value=mock_response
        ):
            result = github_client.get_last_status_actor("github.com/owner/repo", 123)

        assert result == "last-mover"

    def test_returns_none_when_no_events(self, github_client):
        """Empty timeline should return None."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "timelineItems": {
                            "nodes": []
                        }
                    }
                }
            }
        }

        with patch.object(
            github_client, "_execute_graphql_query", return_value=mock_response
        ):
            result = github_client.get_last_status_actor("github.com/owner/repo", 123)

        assert result is None

    def test_returns_none_when_issue_not_found(self, github_client):
        """Missing issue should return None."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": None
                }
            }
        }

        with patch.object(
            github_client, "_execute_graphql_query", return_value=mock_response
        ):
            result = github_client.get_last_status_actor("github.com/owner/repo", 999)

        assert result is None

    def test_handles_null_nodes_in_timeline(self, github_client):
        """Should handle null nodes in timeline gracefully."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "timelineItems": {
                            "nodes": [
                                None,  # Null node
                                {
                                    "__typename": "ProjectV2ItemStatusChangedEvent",
                                    "actor": {"login": "valid-user"},
                                    "createdAt": "2024-01-01T10:00:00Z",
                                },
                                None,  # Another null node
                            ]
                        }
                    }
                }
            }
        }

        with patch.object(
            github_client, "_execute_graphql_query", return_value=mock_response
        ):
            result = github_client.get_last_status_actor("github.com/owner/repo", 123)

        assert result == "valid-user"

    def test_handles_null_actor_in_event(self, github_client):
        """Should skip events with null actors."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "timelineItems": {
                            "nodes": [
                                # Event with null actor (e.g., deleted user)
                                {
                                    "__typename": "ProjectV2ItemStatusChangedEvent",
                                    "actor": None,
                                    "createdAt": "2024-01-02T10:00:00Z",
                                },
                                # Event with valid actor
                                {
                                    "__typename": "ProjectV2ItemStatusChangedEvent",
                                    "actor": {"login": "real-user"},
                                    "createdAt": "2024-01-01T10:00:00Z",
                                },
                            ]
                        }
                    }
                }
            }
        }

        with patch.object(
            github_client, "_execute_graphql_query", return_value=mock_response
        ):
            result = github_client.get_last_status_actor("github.com/owner/repo", 123)

        assert result == "real-user"

    def test_handles_graphql_exception(self, github_client):
        """GraphQL errors should be caught and return None."""
        with patch.object(
            github_client,
            "_execute_graphql_query",
            side_effect=Exception("GraphQL error"),
        ):
            result = github_client.get_last_status_actor("github.com/owner/repo", 123)

        assert result is None

    def test_complex_scenario_multiple_users_and_events(self, github_client):
        """Real-world scenario: multiple users interact with issue over time.

        Timeline:
        1. User A creates and adds issue to project
        2. User B moves it to Research
        3. User A moves it back to Backlog
        4. User B (kiln owner) moves it to Plan

        Expected: Should return User B from the most recent status change.
        """
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "timelineItems": {
                            "nodes": [
                                {
                                    "__typename": "AddedToProjectV2Event",
                                    "actor": {"login": "user-a"},
                                    "createdAt": "2024-01-01T10:00:00Z",
                                },
                                {
                                    "__typename": "ProjectV2ItemStatusChangedEvent",
                                    "actor": {"login": "user-b"},
                                    "createdAt": "2024-01-02T10:00:00Z",
                                },
                                {
                                    "__typename": "ProjectV2ItemStatusChangedEvent",
                                    "actor": {"login": "user-a"},
                                    "createdAt": "2024-01-03T10:00:00Z",
                                },
                                {
                                    "__typename": "ProjectV2ItemStatusChangedEvent",
                                    "actor": {"login": "user-b"},
                                    "createdAt": "2024-01-04T10:00:00Z",
                                },
                            ]
                        }
                    }
                }
            }
        }

        with patch.object(
            github_client, "_execute_graphql_query", return_value=mock_response
        ):
            result = github_client.get_last_status_actor("github.com/owner/repo", 123)

        assert result == "user-b"

    def test_only_add_events_returns_most_recent(self, github_client):
        """Multiple add events (e.g., removed and re-added) should return most recent."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "timelineItems": {
                            "nodes": [
                                {
                                    "__typename": "AddedToProjectV2Event",
                                    "actor": {"login": "first-adder"},
                                    "createdAt": "2024-01-01T10:00:00Z",
                                },
                                {
                                    "__typename": "AddedToProjectV2Event",
                                    "actor": {"login": "second-adder"},
                                    "createdAt": "2024-01-02T10:00:00Z",
                                },
                            ]
                        }
                    }
                }
            }
        }

        with patch.object(
            github_client, "_execute_graphql_query", return_value=mock_response
        ):
            result = github_client.get_last_status_actor("github.com/owner/repo", 123)

        assert result == "second-adder"
