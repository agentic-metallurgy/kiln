"""Pre-flight checks for required CLI tools."""

from __future__ import annotations

import subprocess
from pathlib import Path

from src.logger import get_logger

logger = get_logger(__name__)


class SetupError(Exception):
    """Raised when setup validation fails."""

    pass


def is_restricted_directory(directory: Path | None = None) -> bool:
    """Check if a directory is a restricted location (root or home directory).

    Kiln should not run in:
    - Root directory (/)
    - Users directory (/Users/ on macOS, /home/ on Linux)
    - User's home directory (/Users/<username>/ or /home/<username>/)

    Args:
        directory: The directory to check. Defaults to current working directory.

    Returns:
        True if the directory is restricted, False otherwise.
    """
    if directory is None:
        directory = Path.cwd()

    # Resolve to absolute path
    resolved = directory.resolve()

    # Check for root directory
    if resolved == Path("/"):
        return True

    # Get parts of the path (e.g., ('/', 'Users', 'username') for /Users/username)
    parts = resolved.parts

    # Check for /Users/ or /home/ (users directory itself)
    if len(parts) == 2 and parts[1] in ("Users", "home"):
        return True

    # Check for user's home directory (/Users/<username>/ or /home/<username>/)
    # This catches the home directory exactly (not subdirectories)
    home = Path.home().resolve()
    return resolved == home


def validate_working_directory(directory: Path | None = None) -> None:
    """Validate that the working directory is not a restricted location.

    Raises SetupError if running in root, users directory, or home directory.

    Args:
        directory: The directory to validate. Defaults to current working directory.

    Raises:
        SetupError: If the directory is a restricted location.
    """
    if directory is None:
        directory = Path.cwd()

    resolved = directory.resolve()

    if is_restricted_directory(resolved):
        raise SetupError(
            f"Cannot run kiln in '{resolved}'.\n"
            "Running kiln in root or home directory is not allowed.\n"
            "Please create a dedicated directory and run kiln from there:\n"
            "  mkdir ~/kiln-workspace && cd ~/kiln-workspace && kiln"
        )


def check_required_tools() -> None:
    """Check that required CLI tools are available.

    Checks for:
    - gh CLI (GitHub CLI)
    - claude CLI (Claude Code)

    Raises:
        SetupError: If any required tool is missing with installation instructions
    """
    errors = []

    # Check gh CLI
    try:
        subprocess.run(
            ["gh", "--version"],
            capture_output=True,
            check=True,
        )
    except FileNotFoundError:
        errors.append("gh CLI not found. Install from: https://cli.github.com/")
    except subprocess.CalledProcessError as e:
        errors.append(f"gh CLI error: {e.stderr.decode() if e.stderr else str(e)}")

    # Check claude CLI
    try:
        subprocess.run(
            ["claude", "--version"],
            capture_output=True,
            check=True,
        )
    except FileNotFoundError:
        errors.append(
            "claude CLI not found. Install from: "
            "https://docs.anthropic.com/en/docs/claude-code/overview"
        )
    except subprocess.CalledProcessError as e:
        errors.append(f"claude CLI error: {e.stderr.decode() if e.stderr else str(e)}")

    if errors:
        raise SetupError("\n".join(errors))


def configure_git_credential_helper(hostname: str = "github.com") -> None:
    """Configure gh CLI as git credential helper for a hostname.

    Sets up git to use `gh auth git-credential` for HTTPS authentication.
    This is equivalent to running `gh auth setup-git` but supports per-hostname
    configuration for GitHub Enterprise Server.

    The function clears any existing credential helpers for the hostname before
    adding the gh CLI helper to avoid stacking multiple helpers.

    Args:
        hostname: GitHub hostname (e.g., "github.com" or "github.mycompany.com")

    Example:
        >>> configure_git_credential_helper("github.com")
        >>> configure_git_credential_helper("github.enterprise.example.com")

        After calling, `git config --global --get credential.https://github.com.helper`
        will return `!gh auth git-credential`.
    """
    credential_key = f"credential.https://{hostname}.helper"

    try:
        # Clear any existing helpers for this hostname to avoid stacking
        subprocess.run(
            ["git", "config", "--global", credential_key, ""],
            check=False,  # Don't fail if no existing config
            capture_output=True,
        )

        # Add gh as credential helper
        subprocess.run(
            ["git", "config", "--global", "--add", credential_key, "!gh auth git-credential"],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        # Log but don't fail - user might have different setup
        logger.warning(f"Could not configure git credential helper for {hostname}: {e}")


def get_hostnames_from_project_urls(project_urls: list[str]) -> set[str]:
    """Extract unique hostnames from a list of GitHub project URLs.

    Parses each URL to extract the hostname component. Falls back to "github.com"
    for any URL that cannot be parsed successfully.

    Args:
        project_urls: List of GitHub project URLs
            (e.g., ["https://github.com/orgs/test/projects/1",
                    "https://ghes.company.com/orgs/test/projects/2"])

    Returns:
        Set of unique hostnames (e.g., {"github.com", "ghes.company.com"})

    Example:
        >>> get_hostnames_from_project_urls([
        ...     "https://github.com/orgs/test/projects/1",
        ...     "https://ghes.company.com/orgs/test/projects/2"
        ... ])
        {"github.com", "ghes.company.com"}
    """
    hostnames: set[str] = set()

    for url in project_urls:
        try:
            parts = url.split("/")
            if len(parts) >= 3 and parts[0] in ("http:", "https:") and parts[1] == "":
                hostnames.add(parts[2])
            else:
                hostnames.add("github.com")
        except (IndexError, ValueError, AttributeError):
            hostnames.add("github.com")

    # If no URLs provided, default to github.com
    if not hostnames:
        hostnames.add("github.com")

    return hostnames
