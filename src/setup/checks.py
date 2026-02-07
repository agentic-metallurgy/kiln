"""Pre-flight checks for required CLI tools."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from src.logger import get_logger

logger = get_logger(__name__)


class SetupError(Exception):
    """Raised when setup validation fails."""

    pass


@dataclass
class ClaudeInfo:
    """Information about the Claude CLI installation."""

    path: str
    version: str
    install_method: str


def check_claude_installation() -> ClaudeInfo:
    """Check Claude CLI installation and validate it's the native version.

    Uses shutil.which to resolve the full path, runs claude --version to get
    the version, and detects the installation method from the path.

    Returns:
        ClaudeInfo with path, version, and install_method

    Raises:
        SetupError: If Claude is not found, or if installed via npm/brew
    """
    # Find claude executable
    claude_path = shutil.which("claude")
    if claude_path is None:
        raise SetupError(
            "claude CLI not found. Install from: "
            "https://docs.anthropic.com/en/docs/claude-code/overview"
        )

    # Get version
    try:
        result = subprocess.run(
            ["claude", "--version"],
            capture_output=True,
            check=True,
            text=True,
        )
        version_output = result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise SetupError(f"claude CLI error: {e.stderr if e.stderr else str(e)}") from e

    # Parse version (look for patterns like "v1.0.45" or "1.0.45")
    version_match = re.search(r"v?(\d+\.\d+\.\d+)", version_output)
    version = version_match.group(1) if version_match else version_output

    # Detect installation method from path
    path_lower = claude_path.lower()
    if "node_modules" in path_lower or "/npm/" in path_lower or "/.npm/" in path_lower:
        install_method = "npm"
    elif "/cellar/" in path_lower or "/homebrew/" in path_lower:
        install_method = "brew"
    else:
        install_method = "native"

    # Reject npm and brew installations
    if install_method == "npm":
        raise SetupError(
            f"Claude CLI installed via npm detected at: {claude_path}\n"
            "npm installations are not supported. Please uninstall and use the native installer:\n"
            "  npm uninstall -g @anthropic-ai/claude-code\n"
            "Then install from: https://docs.anthropic.com/en/docs/claude-code/overview"
        )

    if install_method == "brew":
        raise SetupError(
            f"Claude CLI installed via Homebrew detected at: {claude_path}\n"
            "Homebrew installations are not supported. Please uninstall and use the native installer:\n"
            "  brew uninstall claude\n"
            "Then install from: https://docs.anthropic.com/en/docs/claude-code/overview"
        )

    return ClaudeInfo(path=claude_path, version=version, install_method=install_method)


def check_anthropic_env_vars() -> None:
    """Check for ANTHROPIC_* environment variables that may interfere with Claude.

    Scans os.environ for any keys starting with ANTHROPIC_ and raises an error
    if any are found, as these can cause issues with the Claude CLI.

    Raises:
        SetupError: If any ANTHROPIC_* environment variables are found
    """
    anthropic_vars = [key for key in os.environ if key.startswith("ANTHROPIC_")]

    if anthropic_vars:
        unset_commands = "\n".join(f"  unset {var}" for var in sorted(anthropic_vars))
        raise SetupError(
            f"Found ANTHROPIC_* environment variables: {', '.join(sorted(anthropic_vars))}\n"
            "These variables can interfere with Claude CLI operation.\n"
            "Remove ANTHROPIC_* environment variables by running:\n"
            f"{unset_commands}"
        )


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


def check_required_tools() -> ClaudeInfo:
    """Check that required CLI tools are available.

    Checks for:
    - No ANTHROPIC_* environment variables
    - gh CLI (GitHub CLI)
    - claude CLI (Claude Code) - must be native installation

    Returns:
        ClaudeInfo with details about the Claude CLI installation

    Raises:
        SetupError: If any required tool is missing with installation instructions
    """
    # Check for interfering environment variables first
    check_anthropic_env_vars()

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

    if errors:
        raise SetupError("\n".join(errors))

    # Check claude CLI (includes installation method validation)
    claude_info = check_claude_installation()

    return claude_info


FORMULA_URL = "https://raw.githubusercontent.com/agentic-metallurgy/homebrew-tap/main/Formula/kiln.rb"
CACHE_FILE_NAME = "last_update_check"
CACHE_MAX_AGE_SECONDS = 86400  # 24 hours
HTTP_TIMEOUT_SECONDS = 3


class UpdateInfo(NamedTuple):
    """Information about an available update."""

    latest_version: str
    current_version: str


def check_for_updates(kiln_dir: Path | None = None) -> UpdateInfo | None:
    """Check if a newer version of kiln is available from the homebrew tap.

    Fetches the formula file from GitHub and compares the version against
    the current version. Results are cached for 24 hours to avoid repeated
    network requests.

    Args:
        kiln_dir: Path to the .kiln directory for cache storage.
                  Defaults to .kiln/ in the current working directory.

    Returns:
        UpdateInfo if a newer version is available, None otherwise
        (up-to-date, cached, or error).
    """
    try:
        from src.cli import __version__

        if kiln_dir is None:
            kiln_dir = Path.cwd() / ".kiln"

        cache_file = kiln_dir / CACHE_FILE_NAME

        # Check cache - skip network request if checked within 24 hours
        if cache_file.exists():
            last_check = cache_file.stat().st_mtime
            if time.time() - last_check < CACHE_MAX_AGE_SECONDS:
                return None

        # Fetch formula from GitHub
        with urllib.request.urlopen(FORMULA_URL, timeout=HTTP_TIMEOUT_SECONDS) as response:
            content = response.read().decode("utf-8")

        # Parse version from formula
        match = re.search(r'version\s+"([^"]+)"', content)
        if match is None:
            return None

        latest_version = match.group(1)

        # Update cache file (regardless of whether update is available)
        kiln_dir.mkdir(parents=True, exist_ok=True)
        cache_file.touch()

        # Compare versions
        if latest_version != __version__:
            return UpdateInfo(
                latest_version=latest_version,
                current_version=__version__,
            )

        return None

    except Exception:
        return None


def configure_git_credential_env(hostnames: set[str]) -> None:
    """Configure gh CLI as git credential helper via environment variables.

    Sets GIT_CONFIG_COUNT/GIT_CONFIG_KEY_*/GIT_CONFIG_VALUE_* to inject
    credential helper configuration into the current process environment.
    Child processes (git, claude, gh) inherit these variables automatically.

    This approach is preferred over `git config --global` as it:
    - Does not modify the user's ~/.gitconfig
    - Only affects Kiln's process tree
    - Leaves external terminals unaffected

    Requires Git 2.31+ (released March 2021).

    Args:
        hostnames: Set of GitHub hostnames (e.g., {"github.com", "ghes.company.com"})

    Example:
        >>> configure_git_credential_env({"github.com", "ghes.company.com"})

        After calling, environment variables will be set:
        - GIT_CONFIG_COUNT=2
        - GIT_CONFIG_KEY_0=credential.https://ghes.company.com.helper
        - GIT_CONFIG_VALUE_0=!gh auth git-credential
        - GIT_CONFIG_KEY_1=credential.https://github.com.helper
        - GIT_CONFIG_VALUE_1=!gh auth git-credential
    """
    sorted_hostnames = sorted(hostnames)
    os.environ["GIT_CONFIG_COUNT"] = str(len(sorted_hostnames))

    for i, hostname in enumerate(sorted_hostnames):
        os.environ[f"GIT_CONFIG_KEY_{i}"] = f"credential.https://{hostname}.helper"
        os.environ[f"GIT_CONFIG_VALUE_{i}"] = "!gh auth git-credential"

    if sorted_hostnames:
        logger.debug(f"Configured git credential env vars for: {', '.join(sorted_hostnames)}")


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
