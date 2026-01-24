"""Tests for GitHub client comment-related functionality."""

import json
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from src.interfaces import Comment


@pytest.mark.unit
class TestGetCommentsSince:
    """Tests for GitHubTicketClient.get_comments_since() REST API method."""

    def test_get_comments_since_with_timestamp(self, github_client):
        """Test fetching comments since a specific timestamp."""
        mock_response = json.dumps(
            [
                {
                    "id": 12345,
                    "node_id": "IC_kwDOABcdef",
                    "body": "New comment after timestamp",
                    "created_at": "2024-01-15T11:00:00Z",
                    "user": {"login": "testuser"},
                    "reactions": {"+1": 0, "-1": 0},
                }
            ]
        )

        with patch.object(github_client, "_run_gh_command", return_value=mock_response):
            comments = github_client.get_comments_since(
                "owner/repo", 42, "2024-01-15T10:30:00+00:00"
            )

        assert len(comments) == 1
        assert comments[0].database_id == 12345
        assert comments[0].body == "New comment after timestamp"
        assert comments[0].author == "testuser"

    def test_get_comments_since_none_returns_all(self, github_client):
        """Test that passing None for since returns all comments."""
        mock_response = json.dumps(
            [
                {
                    "id": 111,
                    "node_id": "IC_1",
                    "body": "First comment",
                    "created_at": "2024-01-15T08:00:00Z",
                    "user": {"login": "user1"},
                    "reactions": {},
                },
                {
                    "id": 222,
                    "node_id": "IC_2",
                    "body": "Second comment",
                    "created_at": "2024-01-15T09:00:00Z",
                    "user": {"login": "user2"},
                    "reactions": {},
                },
            ]
        )

        with patch.object(github_client, "_run_gh_command", return_value=mock_response) as mock_cmd:
            comments = github_client.get_comments_since("owner/repo", 42, None)

            # Verify no ?since= parameter in the endpoint
            call_args = mock_cmd.call_args[0][0]
            assert "?since=" not in call_args[1]

        assert len(comments) == 2

    def test_get_comments_since_includes_since_in_url(self, github_client):
        """Test that the since parameter is correctly added to the URL."""
        mock_response = json.dumps([])
        timestamp = "2024-01-15T10:30:00+00:00"

        with patch.object(github_client, "_run_gh_command", return_value=mock_response) as mock_cmd:
            github_client.get_comments_since("owner/repo", 42, timestamp)

            call_args = mock_cmd.call_args[0][0]
            # Should include the endpoint with since parameter (normalized to Z format)
            assert "?since=2024-01-15T10:30:00Z" in call_args[1]

    def test_get_comments_since_parses_datetime_correctly(self, github_client):
        """Test that created_at timestamps are parsed to datetime objects."""
        mock_response = json.dumps(
            [
                {
                    "id": 12345,
                    "node_id": "IC_kwDOABcdef",
                    "body": "Test comment",
                    "created_at": "2024-01-15T10:30:45Z",
                    "user": {"login": "testuser"},
                    "reactions": {},
                }
            ]
        )

        with patch.object(github_client, "_run_gh_command", return_value=mock_response):
            comments = github_client.get_comments_since("owner/repo", 42, None)

        assert len(comments) == 1
        assert isinstance(comments[0].created_at, datetime)
        assert comments[0].created_at.year == 2024
        assert comments[0].created_at.month == 1
        assert comments[0].created_at.day == 15
        assert comments[0].created_at.hour == 10
        assert comments[0].created_at.minute == 30
        assert comments[0].created_at.second == 45

    def test_get_comments_since_detects_thumbs_up(self, github_client):
        """Test that thumbs up reactions are detected correctly."""
        mock_response = json.dumps(
            [
                {
                    "id": 111,
                    "node_id": "IC_1",
                    "body": "Has thumbs up",
                    "created_at": "2024-01-15T10:00:00Z",
                    "user": {"login": "user1"},
                    "reactions": {"+1": 2, "-1": 0},
                },
                {
                    "id": 222,
                    "node_id": "IC_2",
                    "body": "No thumbs up",
                    "created_at": "2024-01-15T10:30:00Z",
                    "user": {"login": "user2"},
                    "reactions": {"+1": 0, "-1": 1},
                },
            ]
        )

        with patch.object(github_client, "_run_gh_command", return_value=mock_response):
            comments = github_client.get_comments_since("owner/repo", 42, None)

        assert comments[0].is_processed is True
        assert comments[1].is_processed is False

    def test_get_comments_since_detects_eyes_reaction(self, github_client):
        """Test that eyes reactions are detected correctly."""
        mock_response = json.dumps(
            [
                {
                    "id": 111,
                    "node_id": "IC_1",
                    "body": "Has eyes reaction",
                    "created_at": "2024-01-15T10:00:00Z",
                    "user": {"login": "user1"},
                    "reactions": {"+1": 0, "eyes": 1},
                },
                {
                    "id": 222,
                    "node_id": "IC_2",
                    "body": "No eyes reaction",
                    "created_at": "2024-01-15T10:30:00Z",
                    "user": {"login": "user2"},
                    "reactions": {"+1": 0, "eyes": 0},
                },
            ]
        )

        with patch.object(github_client, "_run_gh_command", return_value=mock_response):
            comments = github_client.get_comments_since("owner/repo", 42, None)

        assert comments[0].is_processing is True
        assert comments[1].is_processing is False

    def test_get_comments_since_skips_deleted_users(self, github_client):
        """Test that comments from deleted users (null user) are skipped."""
        mock_response = json.dumps(
            [
                {
                    "id": 111,
                    "node_id": "IC_1",
                    "body": "Comment from deleted user",
                    "created_at": "2024-01-15T10:00:00Z",
                    "user": None,  # Deleted/ghost user
                    "reactions": {},
                },
                {
                    "id": 222,
                    "node_id": "IC_2",
                    "body": "Normal comment",
                    "created_at": "2024-01-15T10:30:00Z",
                    "user": {"login": "normaluser"},
                    "reactions": {},
                },
            ]
        )

        with patch.object(github_client, "_run_gh_command", return_value=mock_response):
            comments = github_client.get_comments_since("owner/repo", 42, None)

        # Should only have one comment (the one with a valid user)
        assert len(comments) == 1
        assert comments[0].database_id == 222

    def test_get_comments_since_empty_response(self, github_client):
        """Test handling empty response (no new comments)."""
        mock_response = json.dumps([])

        with patch.object(github_client, "_run_gh_command", return_value=mock_response):
            comments = github_client.get_comments_since(
                "owner/repo", 42, "2024-01-15T10:30:00+00:00"
            )

        assert comments == []

    def test_get_comments_since_invalid_json(self, github_client):
        """Test handling invalid JSON response."""
        mock_response = "not valid json"

        with patch.object(github_client, "_run_gh_command", return_value=mock_response):
            comments = github_client.get_comments_since("owner/repo", 42, None)

        assert comments == []

    def test_get_comments_since_uses_paginate(self, github_client):
        """Test that --paginate flag is used for complete results."""
        mock_response = json.dumps([])

        with patch.object(github_client, "_run_gh_command", return_value=mock_response) as mock_cmd:
            github_client.get_comments_since("owner/repo", 42, None)

            call_args = mock_cmd.call_args[0][0]
            assert "--paginate" in call_args


@pytest.mark.unit
class TestComment:
    """Tests for Comment dataclass."""

    def test_comment_creation(self):
        """Test creating a Comment instance."""
        timestamp = datetime.now(UTC)
        comment = Comment(
            id="IC_abc123",
            database_id=12345,
            body="Test comment body",
            created_at=timestamp,
            author="testuser",
            is_processed=True,
        )

        assert comment.id == "IC_abc123"
        assert comment.database_id == 12345
        assert comment.body == "Test comment body"
        assert comment.created_at == timestamp
        assert comment.author == "testuser"
        assert comment.is_processed is True

    def test_comment_default_is_processed(self):
        """Test that is_processed defaults to False."""
        timestamp = datetime.now(UTC)
        comment = Comment(
            id="IC_abc123",
            database_id=12345,
            body="Test comment",
            created_at=timestamp,
            author="testuser",
        )

        assert comment.is_processed is False

    def test_comment_default_is_processing(self):
        """Test that is_processing defaults to False."""
        timestamp = datetime.now(UTC)
        comment = Comment(
            id="IC_abc123",
            database_id=12345,
            body="Test comment",
            created_at=timestamp,
            author="testuser",
        )

        assert comment.is_processing is False

    def test_comment_created_at_isoformat(self):
        """Test converting created_at to ISO format for storage."""
        timestamp = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        comment = Comment(
            id="IC_abc123",
            database_id=12345,
            body="Test",
            created_at=timestamp,
            author="testuser",
        )

        # This is how we store timestamps in the database
        iso_string = comment.created_at.isoformat()
        assert iso_string == "2024-01-15T10:30:00+00:00"

        # Verify it can be parsed back
        parsed = datetime.fromisoformat(iso_string)
        assert parsed == timestamp


@pytest.mark.unit
class TestAddComment:
    """Tests for GitHubTicketClient.add_comment()."""

    def test_add_comment_returns_issue_comment(self, github_client):
        """Test that add_comment returns an Comment object."""
        # Mock the issue ID query
        issue_response = {"data": {"repository": {"issue": {"id": "I_123"}}}}
        # Mock the add comment mutation
        comment_response = {
            "data": {
                "addComment": {
                    "commentEdge": {
                        "node": {
                            "id": "IC_456",
                            "databaseId": 789,
                            "body": "Test comment body",
                            "createdAt": "2024-01-15T10:30:00Z",
                            "author": {"login": "kiln-bot"},
                        }
                    }
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query") as mock_query:
            mock_query.side_effect = [issue_response, comment_response]
            result = github_client.add_comment("owner/repo", 42, "Test comment body")

        assert isinstance(result, Comment)
        assert result.id == "IC_456"
        assert result.database_id == 789
        assert result.body == "Test comment body"
        assert result.author == "kiln-bot"
        assert result.is_processed is False

    def test_add_comment_parses_created_at(self, github_client):
        """Test that created_at is parsed correctly from ISO format."""
        issue_response = {"data": {"repository": {"issue": {"id": "I_123"}}}}
        comment_response = {
            "data": {
                "addComment": {
                    "commentEdge": {
                        "node": {
                            "id": "IC_456",
                            "databaseId": 789,
                            "body": "Test",
                            "createdAt": "2024-06-20T15:45:30Z",
                            "author": {"login": "test-user"},
                        }
                    }
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query") as mock_query:
            mock_query.side_effect = [issue_response, comment_response]
            result = github_client.add_comment("owner/repo", 42, "Test")

        assert result.created_at.year == 2024
        assert result.created_at.month == 6
        assert result.created_at.day == 20
        assert result.created_at.hour == 15
        assert result.created_at.minute == 45
        assert result.created_at.second == 30

    def test_add_comment_makes_correct_api_calls(self, github_client):
        """Test that the correct GraphQL queries are made."""
        issue_response = {"data": {"repository": {"issue": {"id": "I_test_issue"}}}}
        comment_response = {
            "data": {
                "addComment": {
                    "commentEdge": {
                        "node": {
                            "id": "IC_new",
                            "databaseId": 100,
                            "body": "New comment",
                            "createdAt": "2024-01-15T12:00:00Z",
                            "author": {"login": "author"},
                        }
                    }
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query") as mock_query:
            mock_query.side_effect = [issue_response, comment_response]
            github_client.add_comment("test-owner/test-repo", 99, "New comment")

            # First call: get issue ID
            first_call = mock_query.call_args_list[0]
            assert "repository(owner: $owner, name: $name)" in first_call[0][0]
            assert first_call[0][1]["owner"] == "test-owner"
            assert first_call[0][1]["name"] == "test-repo"
            assert first_call[0][1]["number"] == 99

            # Second call: add comment
            second_call = mock_query.call_args_list[1]
            assert "addComment" in second_call[0][0]
            assert second_call[0][1]["subjectId"] == "I_test_issue"
            assert second_call[0][1]["body"] == "New comment"


@pytest.mark.unit
class TestAddReaction:
    """Tests for GitHubTicketClient.add_reaction() method."""

    def test_add_reaction_success(self, github_client):
        """Test adding a reaction to a comment."""
        mock_response = {"data": {"addReaction": {"reaction": {"content": "THUMBS_UP"}}}}

        with patch.object(
            github_client, "_execute_graphql_query", return_value=mock_response
        ) as mock_query:
            github_client.add_reaction("IC_comment123", "THUMBS_UP")

        call_args = mock_query.call_args
        assert "addReaction" in call_args[0][0]
        assert call_args[0][1]["subjectId"] == "IC_comment123"
        assert call_args[0][1]["content"] == "THUMBS_UP"

    def test_add_reaction_eyes(self, github_client):
        """Test adding eyes reaction."""
        mock_response = {"data": {"addReaction": {"reaction": {"content": "EYES"}}}}

        with patch.object(
            github_client, "_execute_graphql_query", return_value=mock_response
        ) as mock_query:
            github_client.add_reaction("IC_comment123", "EYES")

        call_args = mock_query.call_args
        assert call_args[0][1]["content"] == "EYES"


@pytest.mark.unit
class TestGetComments:
    """Tests for GitHubTicketClient.get_comments() GraphQL method."""

    def test_get_comments_returns_list(self, github_client):
        """Test fetching comments via GraphQL."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "comments": {
                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                            "nodes": [
                                {
                                    "id": "IC_1",
                                    "databaseId": 111,
                                    "body": "First comment",
                                    "createdAt": "2024-01-15T10:00:00Z",
                                    "author": {"login": "user1"},
                                    "thumbsUp": {"totalCount": 0},
                                    "eyes": {"totalCount": 0},
                                },
                                {
                                    "id": "IC_2",
                                    "databaseId": 222,
                                    "body": "Second comment",
                                    "createdAt": "2024-01-15T11:00:00Z",
                                    "author": {"login": "user2"},
                                    "thumbsUp": {"totalCount": 1},
                                    "eyes": {"totalCount": 0},
                                },
                            ],
                        }
                    }
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            comments = github_client.get_comments("github.com/owner/repo", 42)

        assert len(comments) == 2
        assert comments[0].body == "First comment"
        assert comments[0].is_processed is False
        assert comments[1].body == "Second comment"
        assert comments[1].is_processed is True

    def test_get_comments_handles_pagination(self, github_client):
        """Test pagination of comments."""
        page1 = {
            "data": {
                "repository": {
                    "issue": {
                        "comments": {
                            "pageInfo": {"hasNextPage": True, "endCursor": "cursor1"},
                            "nodes": [
                                {
                                    "id": "IC_1",
                                    "databaseId": 111,
                                    "body": "Comment 1",
                                    "createdAt": "2024-01-15T10:00:00Z",
                                    "author": {"login": "user1"},
                                    "thumbsUp": {"totalCount": 0},
                                    "eyes": {"totalCount": 0},
                                }
                            ],
                        }
                    }
                }
            }
        }
        page2 = {
            "data": {
                "repository": {
                    "issue": {
                        "comments": {
                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                            "nodes": [
                                {
                                    "id": "IC_2",
                                    "databaseId": 222,
                                    "body": "Comment 2",
                                    "createdAt": "2024-01-15T11:00:00Z",
                                    "author": {"login": "user2"},
                                    "thumbsUp": {"totalCount": 0},
                                    "eyes": {"totalCount": 0},
                                }
                            ],
                        }
                    }
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query") as mock_query:
            mock_query.side_effect = [page1, page2]
            comments = github_client.get_comments("github.com/owner/repo", 42)

        assert len(comments) == 2

    def test_get_comments_skips_deleted_users(self, github_client):
        """Test that comments from deleted users are skipped."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "comments": {
                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                            "nodes": [
                                {
                                    "id": "IC_1",
                                    "databaseId": 111,
                                    "body": "Ghost comment",
                                    "createdAt": "2024-01-15T10:00:00Z",
                                    "author": None,  # Deleted user
                                    "thumbsUp": {"totalCount": 0},
                                    "eyes": {"totalCount": 0},
                                },
                                {
                                    "id": "IC_2",
                                    "databaseId": 222,
                                    "body": "Valid comment",
                                    "createdAt": "2024-01-15T11:00:00Z",
                                    "author": {"login": "user"},
                                    "thumbsUp": {"totalCount": 0},
                                    "eyes": {"totalCount": 0},
                                },
                            ],
                        }
                    }
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            comments = github_client.get_comments("github.com/owner/repo", 42)

        assert len(comments) == 1
        assert comments[0].body == "Valid comment"
