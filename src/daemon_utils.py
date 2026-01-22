"""Shared utility functions for daemon classes.

This module contains common helper functions used across multiple daemon-related
classes, extracted from the monolithic Daemon class for better code organization.
"""

from src.logger import get_logger

logger = get_logger(__name__)


def get_worktree_path(workspace_dir: str, repo: str, issue_number: int) -> str:
    """Get the worktree path for a repo and issue.

    Args:
        workspace_dir: Base workspace directory path
        repo: Repository in 'owner/repo' or 'hostname/owner/repo' format
        issue_number: Issue number

    Returns:
        Path to the worktree directory
    """
    # Extract just the repo name from 'owner/repo' or 'hostname/owner/repo'
    repo_name = repo.split("/")[-1] if "/" in repo else repo
    return f"{workspace_dir}/{repo_name}-issue-{issue_number}"


def get_hostname_from_url(url: str) -> str:
    """Extract hostname from a GitHub URL.

    Args:
        url: GitHub URL (e.g., https://github.com/orgs/myorg/projects/1)

    Returns:
        Hostname (e.g., "github.com"), defaults to "github.com" if parsing fails
    """
    try:
        parts = url.split("/")
        if len(parts) >= 3 and parts[0] in ("http:", "https:") and parts[1] == "":
            return parts[2]
    except (IndexError, ValueError):
        pass
    return "github.com"
