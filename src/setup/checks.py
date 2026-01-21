"""Pre-flight checks for required CLI tools."""

import subprocess

from src.logger import get_logger

logger = get_logger(__name__)


class SetupError(Exception):
    """Raised when setup validation fails."""

    pass


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
