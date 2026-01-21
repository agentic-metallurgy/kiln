"""Tests for the security module."""

import logging

from src.security import ActorCategory, check_actor_allowed


class TestCheckActorAllowed:
    """Tests for check_actor_allowed function."""

    def test_self_actor_returns_self(self, caplog):
        """Actor matching username_self should return SELF and log INFO."""
        with caplog.at_level(logging.INFO):
            result = check_actor_allowed(
                actor="allowed-user",
                username_self="allowed-user",
                context_key="owner/repo#123",
            )
        assert result == ActorCategory.SELF
        assert "Action by self" in caplog.text
        assert "'allowed-user'" in caplog.text

    def test_none_actor_returns_unknown(self, caplog):
        """None actor (unknown) should return UNKNOWN and log WARNING."""
        with caplog.at_level(logging.WARNING):
            result = check_actor_allowed(
                actor=None,
                username_self="allowed-user",
                context_key="owner/repo#123",
            )
        assert result == ActorCategory.UNKNOWN
        assert "BLOCKED" in caplog.text
        assert "Could not determine actor" in caplog.text
        assert "owner/repo#123" in caplog.text

    def test_blocked_actor_returns_blocked(self, caplog):
        """Actor not matching username_self or team should return BLOCKED and log WARNING."""
        with caplog.at_level(logging.WARNING):
            result = check_actor_allowed(
                actor="evil-user",
                username_self="allowed-user",
                context_key="owner/repo#123",
            )
        assert result == ActorCategory.BLOCKED
        assert "BLOCKED" in caplog.text
        assert "evil-user" in caplog.text
        assert "owner/repo#123" in caplog.text

    def test_team_member_returns_team(self, caplog):
        """Actor in team_usernames should return TEAM and log DEBUG."""
        with caplog.at_level(logging.DEBUG):
            result = check_actor_allowed(
                actor="teammate",
                username_self="allowed-user",
                context_key="owner/repo#123",
                team_usernames=["teammate", "other-team-member"],
            )
        assert result == ActorCategory.TEAM
        assert "Action by team member" in caplog.text
        assert "'teammate'" in caplog.text
        assert "Observing silently" in caplog.text

    def test_team_member_no_warning_logged(self, caplog):
        """Team member should not produce any WARNING logs."""
        with caplog.at_level(logging.WARNING):
            check_actor_allowed(
                actor="teammate",
                username_self="allowed-user",
                context_key="owner/repo#123",
                team_usernames=["teammate"],
            )
        assert caplog.text == ""

    def test_action_type_prefix_in_log(self, caplog):
        """Action type should appear in log prefix."""
        with caplog.at_level(logging.WARNING):
            check_actor_allowed(
                actor="evil-user",
                username_self="allowed-user",
                context_key="owner/repo#123",
                action_type="YOLO",
            )
        assert "YOLO:" in caplog.text

    def test_action_type_prefix_for_none_actor(self, caplog):
        """Action type prefix should work for None actor too."""
        with caplog.at_level(logging.WARNING):
            check_actor_allowed(
                actor=None,
                username_self="allowed-user",
                context_key="owner/repo#123",
                action_type="RESET",
            )
        assert "RESET:" in caplog.text

    def test_action_type_prefix_for_self(self, caplog):
        """Action type prefix should work for self actor too."""
        with caplog.at_level(logging.INFO):
            check_actor_allowed(
                actor="allowed-user",
                username_self="allowed-user",
                context_key="owner/repo#123",
                action_type="YOLO",
            )
        assert "YOLO:" in caplog.text

    def test_action_type_prefix_for_team(self, caplog):
        """Action type prefix should work for team member too."""
        with caplog.at_level(logging.DEBUG):
            check_actor_allowed(
                actor="teammate",
                username_self="allowed-user",
                context_key="owner/repo#123",
                action_type="STATUS",
                team_usernames=["teammate"],
            )
        assert "STATUS:" in caplog.text

    def test_empty_username_self_blocks_everyone(self, caplog):
        """Empty username_self should block all actors."""
        with caplog.at_level(logging.WARNING):
            result = check_actor_allowed(
                actor="any-user",
                username_self="",
                context_key="owner/repo#123",
            )
        assert result == ActorCategory.BLOCKED

    def test_self_actor_no_warning_logged(self, caplog):
        """Self actor should not produce any WARNING logs."""
        with caplog.at_level(logging.WARNING):
            check_actor_allowed(
                actor="allowed-user",
                username_self="allowed-user",
                context_key="owner/repo#123",
            )
        assert caplog.text == ""

    def test_username_self_logged_on_denial(self, caplog):
        """Username_self should be included in denial log for debugging."""
        with caplog.at_level(logging.WARNING):
            check_actor_allowed(
                actor="evil-user",
                username_self="user1",
                context_key="owner/repo#123",
            )
        assert "user1" in caplog.text

    def test_empty_team_list_treated_as_no_team(self):
        """Empty team list should be treated same as None."""
        result = check_actor_allowed(
            actor="some-user",
            username_self="allowed-user",
            context_key="owner/repo#123",
            team_usernames=[],
        )
        assert result == ActorCategory.BLOCKED

    def test_self_takes_priority_over_team(self):
        """If actor is both self and in team list, should return SELF."""
        result = check_actor_allowed(
            actor="allowed-user",
            username_self="allowed-user",
            context_key="owner/repo#123",
            team_usernames=["allowed-user", "teammate"],
        )
        assert result == ActorCategory.SELF


class TestActorCategory:
    """Tests for ActorCategory enum."""

    def test_enum_values_exist(self):
        """All expected enum values should exist."""
        assert ActorCategory.SELF.value == "self"
        assert ActorCategory.TEAM.value == "team"
        assert ActorCategory.UNKNOWN.value == "unknown"
        assert ActorCategory.BLOCKED.value == "blocked"

    def test_enum_equality(self):
        """Enum values should be comparable."""
        assert ActorCategory.SELF == ActorCategory.SELF
        assert ActorCategory.SELF != ActorCategory.TEAM
        assert ActorCategory.UNKNOWN != ActorCategory.BLOCKED
