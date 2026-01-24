"""Tests for GitHub client board/project-related functionality."""

from unittest.mock import patch

import pytest


@pytest.mark.unit
class TestParseBoardUrl:
    """Tests for GitHubTicketClient._parse_board_url() method."""

    def test_parse_board_url_github_com(self, github_client):
        """Test parsing standard github.com project URL."""
        url = "https://github.com/orgs/myorg/projects/42/views/1"
        hostname, entity_type, login, project_number = github_client._parse_board_url(url)

        assert hostname == "github.com"
        assert entity_type == "organization"
        assert login == "myorg"
        assert project_number == 42

    def test_parse_board_url_without_views(self, github_client):
        """Test parsing URL without /views/ suffix."""
        url = "https://github.com/orgs/testorg/projects/99"
        hostname, entity_type, login, project_number = github_client._parse_board_url(url)

        assert hostname == "github.com"
        assert entity_type == "organization"
        assert login == "testorg"
        assert project_number == 99

    def test_parse_board_url_user_project(self, github_client):
        """Test parsing user project URL."""
        url = "https://github.com/users/myuser/projects/5"
        hostname, entity_type, login, project_number = github_client._parse_board_url(url)

        assert hostname == "github.com"
        assert entity_type == "user"
        assert login == "myuser"
        assert project_number == 5

    def test_parse_board_url_invalid_format(self, github_client):
        """Test parsing invalid URL raises ValueError."""
        url = "https://github.com/testorg/testrepo"  # Not a project URL

        with pytest.raises(ValueError, match="Invalid project URL format"):
            github_client._parse_board_url(url)

    def test_parse_board_url_http(self, github_client):
        """Test parsing http:// URL (not https)."""
        url = "http://github.com/orgs/myorg/projects/10"
        hostname, entity_type, login, project_number = github_client._parse_board_url(url)

        assert hostname == "github.com"
        assert entity_type == "organization"
        assert login == "myorg"
        assert project_number == 10


@pytest.mark.unit
class TestGetBoardItems:
    """Tests for GitHubTicketClient.get_board_items() method."""

    def test_get_board_items_returns_list(self, github_client):
        """Test that board items are returned as a list of TicketItem."""
        mock_response = {
            "data": {
                "organization": {
                    "projectV2": {
                        "items": {
                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                            "nodes": [
                                {
                                    "id": "PVTI_item123",
                                    "content": {
                                        "number": 42,
                                        "title": "Test Issue",
                                        "state": "OPEN",
                                        "stateReason": None,
                                        "repository": {"nameWithOwner": "owner/repo"},
                                        "labels": {"nodes": [{"name": "bug"}]},
                                        "closedByPullRequestsReferences": {"nodes": []},
                                        "comments": {"totalCount": 5},
                                    },
                                    "fieldValues": {
                                        "nodes": [{"field": {"name": "Status"}, "name": "Research"}]
                                    },
                                }
                            ],
                        }
                    }
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            items = github_client.get_board_items("https://github.com/orgs/testorg/projects/1")

        assert len(items) == 1
        assert items[0].ticket_id == 42
        assert items[0].title == "Test Issue"
        assert items[0].status == "Research"

    def test_get_board_items_handles_pagination(self, github_client):
        """Test that pagination is handled correctly."""
        page1 = {
            "data": {
                "organization": {
                    "projectV2": {
                        "items": {
                            "pageInfo": {"hasNextPage": True, "endCursor": "cursor1"},
                            "nodes": [
                                {
                                    "id": "PVTI_1",
                                    "content": {
                                        "number": 1,
                                        "title": "Issue 1",
                                        "state": "OPEN",
                                        "stateReason": None,
                                        "repository": {"nameWithOwner": "owner/repo"},
                                        "labels": {"nodes": []},
                                        "closedByPullRequestsReferences": {"nodes": []},
                                        "comments": {"totalCount": 0},
                                    },
                                    "fieldValues": {"nodes": []},
                                }
                            ],
                        }
                    }
                }
            }
        }
        page2 = {
            "data": {
                "organization": {
                    "projectV2": {
                        "items": {
                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                            "nodes": [
                                {
                                    "id": "PVTI_2",
                                    "content": {
                                        "number": 2,
                                        "title": "Issue 2",
                                        "state": "OPEN",
                                        "stateReason": None,
                                        "repository": {"nameWithOwner": "owner/repo"},
                                        "labels": {"nodes": []},
                                        "closedByPullRequestsReferences": {"nodes": []},
                                        "comments": {"totalCount": 0},
                                    },
                                    "fieldValues": {"nodes": []},
                                }
                            ],
                        }
                    }
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query") as mock_query:
            mock_query.side_effect = [page1, page2]
            items = github_client.get_board_items("https://github.com/orgs/testorg/projects/1")

        assert len(items) == 2
        assert items[0].ticket_id == 1
        assert items[1].ticket_id == 2


@pytest.mark.unit
class TestGetBoardMetadata:
    """Tests for GitHubTicketClient.get_board_metadata() method."""

    def test_get_board_metadata_returns_project_info(self, github_client):
        """Test fetching project metadata including status field."""
        mock_response = {
            "data": {
                "organization": {
                    "projectV2": {
                        "id": "PVT_123",
                        "fields": {
                            "nodes": [
                                {
                                    "id": "PVTSSF_456",
                                    "name": "Status",
                                    "options": [
                                        {"id": "opt1", "name": "Backlog"},
                                        {"id": "opt2", "name": "Research"},
                                        {"id": "opt3", "name": "Plan"},
                                    ],
                                }
                            ]
                        },
                    }
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            metadata = github_client.get_board_metadata(
                "https://github.com/orgs/testorg/projects/1"
            )

        assert metadata["project_id"] == "PVT_123"
        assert metadata["status_field_id"] == "PVTSSF_456"
        assert metadata["status_options"] == {
            "Backlog": "opt1",
            "Research": "opt2",
            "Plan": "opt3",
        }

    def test_get_board_metadata_handles_missing_status_field(self, github_client):
        """Test handling when Status field is not found."""
        mock_response = {
            "data": {
                "organization": {
                    "projectV2": {
                        "id": "PVT_123",
                        "fields": {
                            "nodes": [
                                {
                                    "id": "PVTSSF_789",
                                    "name": "Priority",
                                    "options": [],
                                }
                            ]
                        },
                    }
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            metadata = github_client.get_board_metadata(
                "https://github.com/orgs/testorg/projects/1"
            )

        assert metadata["project_id"] == "PVT_123"
        assert metadata["status_field_id"] is None
        assert metadata["status_options"] == {}


@pytest.mark.unit
class TestUpdateItemStatus:
    """Tests for GitHubTicketClient.update_item_status() method."""

    def test_update_item_status_success(self, github_client):
        """Test successfully updating item status."""
        item_query_response = {
            "data": {
                "node": {
                    "project": {
                        "id": "PVT_123",
                        "field": {
                            "id": "PVTSSF_456",
                            "options": [
                                {"id": "opt1", "name": "Backlog"},
                                {"id": "opt2", "name": "Research"},
                            ],
                        },
                    }
                }
            }
        }
        mutation_response = {
            "data": {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "PVTI_789"}}}
        }

        with patch.object(github_client, "_execute_graphql_query") as mock_query:
            mock_query.side_effect = [item_query_response, mutation_response]
            github_client.update_item_status("PVTI_789", "Research")

        assert mock_query.call_count == 2

    def test_update_item_status_raises_on_invalid_status(self, github_client):
        """Test that ValueError is raised for non-existent status."""
        item_query_response = {
            "data": {
                "node": {
                    "project": {
                        "id": "PVT_123",
                        "field": {
                            "id": "PVTSSF_456",
                            "options": [
                                {"id": "opt1", "name": "Backlog"},
                            ],
                        },
                    }
                }
            }
        }

        with patch.object(
            github_client, "_execute_graphql_query", return_value=item_query_response
        ):
            with pytest.raises(ValueError, match="Status 'NonExistent' not found"):
                github_client.update_item_status("PVTI_789", "NonExistent")

    def test_update_item_status_accepts_hostname_kwarg(self, github_client):
        """Test that update_item_status accepts hostname keyword argument.

        This ensures signature compatibility with GitHubClientBase for GHES support.
        """
        item_query_response = {
            "data": {
                "node": {
                    "project": {
                        "id": "PVT_123",
                        "field": {
                            "id": "PVTSSF_456",
                            "options": [
                                {"id": "opt1", "name": "Backlog"},
                                {"id": "opt2", "name": "Research"},
                            ],
                        },
                    }
                }
            }
        }
        mutation_response = {
            "data": {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "PVTI_789"}}}
        }

        with patch.object(github_client, "_execute_graphql_query") as mock_query:
            mock_query.side_effect = [item_query_response, mutation_response]
            # This call pattern matches how Daemon calls the method
            github_client.update_item_status("PVTI_789", "Research", hostname="github.com")

        assert mock_query.call_count == 2


@pytest.mark.unit
class TestArchiveItem:
    """Tests for GitHubTicketClient.archive_item() method."""

    def test_archive_item_success(self, github_client):
        """Test successfully archiving an item."""
        mock_response = {"data": {"archiveProjectV2Item": {"item": {"id": "PVTI_123"}}}}

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            result = github_client.archive_item("PVT_project", "PVTI_123")

        assert result is True

    def test_archive_item_failure(self, github_client):
        """Test archive_item returns False on error."""
        with patch.object(
            github_client, "_execute_graphql_query", side_effect=Exception("API error")
        ):
            result = github_client.archive_item("PVT_project", "PVTI_123")

        assert result is False

    def test_archive_item_accepts_hostname_kwarg(self, github_client):
        """Test that archive_item accepts hostname keyword argument.

        This ensures signature compatibility with GitHubClientBase for GHES support.
        """
        mock_response = {"data": {"archiveProjectV2Item": {"item": {"id": "PVTI_123"}}}}

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            # This call pattern matches how Daemon calls the method
            result = github_client.archive_item("PVT_project", "PVTI_123", hostname="github.com")

        assert result is True
