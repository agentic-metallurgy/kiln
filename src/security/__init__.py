"""Security and authorization utilities for Kiln."""

from src.security.authorization import ActorCategory, check_actor_allowed

__all__ = [
    "ActorCategory",
    "check_actor_allowed",
]
