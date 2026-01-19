"""Tests for the security module."""

import logging

from src.security import check_actor_allowed


class TestCheckActorAllowed:
    """Tests for check_actor_allowed function."""

    def test_allowed_actor_returns_true(self):
        """Allowed actor should return True."""
        result = check_actor_allowed(
            actor="allowed-user",
            allowed_username="allowed-user",
            context_key="owner/repo#123",
        )
        assert result is True

    def test_none_actor_returns_false(self, caplog):
        """None actor (unknown) should return False and log warning."""
        with caplog.at_level(logging.WARNING):
            result = check_actor_allowed(
                actor=None,
                allowed_username="allowed-user",
                context_key="owner/repo#123",
            )
        assert result is False
        assert "BLOCKED:" in caplog.text
        assert "Could not determine actor" in caplog.text
        assert "owner/repo#123" in caplog.text

    def test_disallowed_actor_returns_false(self, caplog):
        """Actor not matching allowed_username should return False and log warning."""
        with caplog.at_level(logging.WARNING):
            result = check_actor_allowed(
                actor="evil-user",
                allowed_username="allowed-user",
                context_key="owner/repo#123",
            )
        assert result is False
        assert "BLOCKED:" in caplog.text
        assert "evil-user" in caplog.text
        assert "owner/repo#123" in caplog.text

    def test_action_type_prefix_in_log(self, caplog):
        """Action type should appear in log prefix."""
        with caplog.at_level(logging.WARNING):
            check_actor_allowed(
                actor="evil-user",
                allowed_username="allowed-user",
                context_key="owner/repo#123",
                action_type="YOLO",
            )
        assert "YOLO BLOCKED:" in caplog.text

    def test_action_type_prefix_for_none_actor(self, caplog):
        """Action type prefix should work for None actor too."""
        with caplog.at_level(logging.WARNING):
            check_actor_allowed(
                actor=None,
                allowed_username="allowed-user",
                context_key="owner/repo#123",
                action_type="RESET",
            )
        assert "RESET BLOCKED:" in caplog.text

    def test_empty_allowed_username_blocks_everyone(self, caplog):
        """Empty allowed_username should block all actors."""
        with caplog.at_level(logging.WARNING):
            result = check_actor_allowed(
                actor="any-user",
                allowed_username="",
                context_key="owner/repo#123",
            )
        assert result is False

    def test_allowed_actor_no_warning_logged(self, caplog):
        """Allowed actor should not produce any warning logs."""
        with caplog.at_level(logging.WARNING):
            check_actor_allowed(
                actor="allowed-user",
                allowed_username="allowed-user",
                context_key="owner/repo#123",
            )
        assert caplog.text == ""

    def test_allowed_username_logged_on_denial(self, caplog):
        """Allowed username should be included in denial log for debugging."""
        with caplog.at_level(logging.WARNING):
            check_actor_allowed(
                actor="evil-user",
                allowed_username="user1",
                context_key="owner/repo#123",
            )
        assert "user1" in caplog.text
