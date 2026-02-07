"""Repository credentials module for kiln.

This module provides management of repository credential files,
including loading mappings from .kiln/credentials.yaml and copying
credential files (e.g., .env) into worktrees before workflow execution.
"""

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import yaml

logger = logging.getLogger(__name__)

# Default paths
CREDENTIALS_CONFIG_PATH = ".kiln/credentials.yaml"
DEFAULT_DESTINATION = ".env"


class RepoCredentialsError(Exception):
    """Base exception for repository credential errors."""

    pass


class RepoCredentialsLoadError(RepoCredentialsError):
    """Error loading repository credentials configuration file."""

    pass


def parse_repo_url(url: str) -> tuple[str, str, str]:
    """Parse a repository URL into (host, owner, repo).

    Accepts URLs in various formats:
        - https://github.com/owner/repo
        - https://github.com/owner/repo/
        - https://github.com/owner/repo/tree/main
        - github.com/owner/repo
        - github.com/owner/repo/tree/main
        - http://ghes.example.com/owner/repo

    Args:
        url: Repository URL string (with or without scheme).

    Returns:
        Tuple of (host, owner, repo).

    Raises:
        ValueError: If the URL cannot be parsed into host/owner/repo.
    """
    raw = url.strip()
    if not raw:
        raise ValueError("repo_url cannot be empty")

    # Prepend scheme if missing so urlparse works correctly
    if "://" not in raw:
        raw = f"https://{raw}"

    parsed = urlparse(raw)
    host = parsed.netloc
    if not host:
        raise ValueError(f"Could not extract hostname from repo_url '{url}'")

    # Split path into segments, filtering empty strings from leading/trailing slashes
    segments = [s for s in parsed.path.split("/") if s]
    if len(segments) < 2:
        raise ValueError(
            f"repo_url must contain at least owner/repo in the path, got '{url}'"
        )

    owner = segments[0]
    repo = segments[1]
    # Strip .git suffix if present
    if repo.endswith(".git"):
        repo = repo[:-4]

    return host, owner, repo


@dataclass
class RepoCredentialEntry:
    """Represents a single repository credential mapping.

    Attributes:
        title: Human-readable label for the repository.
        host: GitHub hostname (e.g., "github.com" or "ghes.example.com").
        owner: GitHub organization or user (e.g., "my-org").
        repo: Repository name (e.g., "api-service").
        credential_path: Absolute path to the credential file on disk.
        destination: Where to place the file in the worktree (default: ".env").
    """

    title: str
    host: str
    owner: str
    repo: str
    credential_path: str
    destination: str


class RepoCredentialsManager:
    """Manager for repository credential file mappings.

    This class handles:
    - Loading repo-to-credential mappings from .kiln/credentials.yaml
    - Copying credential files into worktree directories for matching repos
    - Validating credential paths and configuration entries

    Attributes:
        config_path: Path to the credentials YAML configuration file.
    """

    def __init__(self, config_path: str | None = None):
        """Initialize the repository credentials manager.

        Args:
            config_path: Optional path to credentials config file.
                Defaults to .kiln/credentials.yaml if not specified.
        """
        self.config_path = config_path or CREDENTIALS_CONFIG_PATH
        self._cached_entries: list[RepoCredentialEntry] | None = None

    def load_config(self) -> list[RepoCredentialEntry] | None:
        """Load repository credential mappings from the config file.

        Returns:
            List of RepoCredentialEntry if the file exists and is valid,
            None if the file doesn't exist.

        Raises:
            RepoCredentialsLoadError: If the file exists but cannot be parsed
                or contains invalid entries.
        """
        config_path = Path(self.config_path)

        if not config_path.exists():
            logger.debug(
                f"Credentials config file not found at {self.config_path}"
            )
            return None

        try:
            with open(config_path, encoding="utf-8") as f:
                raw_config = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise RepoCredentialsLoadError(
                f"Invalid YAML in credentials config file {self.config_path}: {e}"
            ) from e
        except OSError as e:
            raise RepoCredentialsLoadError(
                f"Failed to read credentials config file {self.config_path}: {e}"
            ) from e

        if raw_config is None:
            logger.debug("Credentials config file is empty")
            return None

        if not isinstance(raw_config, dict):
            raise RepoCredentialsLoadError(
                f"Credentials config must be a YAML mapping, "
                f"got {type(raw_config).__name__}"
            )

        repositories = raw_config.get("repositories")
        if repositories is None:
            logger.debug("No 'repositories' key in credentials config")
            return None

        if not isinstance(repositories, list):
            raise RepoCredentialsLoadError(
                f"'repositories' must be a list, got {type(repositories).__name__}"
            )

        entries: list[RepoCredentialEntry] = []
        for i, repo_entry in enumerate(repositories):
            if not isinstance(repo_entry, dict):
                raise RepoCredentialsLoadError(
                    f"Repository entry {i} must be a mapping, "
                    f"got {type(repo_entry).__name__}"
                )

            # Validate required fields
            required_fields = ["title", "repo_url", "credential_path"]
            for field in required_fields:
                if field not in repo_entry:
                    raise RepoCredentialsLoadError(
                        f"Repository entry {i} is missing required field '{field}'"
                    )

            # Parse repo_url into host/owner/repo
            repo_url = str(repo_entry["repo_url"])
            try:
                host, owner, repo = parse_repo_url(repo_url)
            except ValueError as e:
                raise RepoCredentialsLoadError(
                    f"Repository entry {i} has invalid repo_url: {e}"
                ) from e

            credential_path = str(repo_entry["credential_path"])

            # Validate credential_path is absolute
            if not Path(credential_path).is_absolute():
                raise RepoCredentialsLoadError(
                    f"Repository entry {i} credential_path must be absolute, "
                    f"got '{credential_path}'"
                )

            destination = str(
                repo_entry.get("destination", DEFAULT_DESTINATION)
            )

            entries.append(
                RepoCredentialEntry(
                    title=str(repo_entry["title"]),
                    host=host,
                    owner=owner,
                    repo=repo,
                    credential_path=credential_path,
                    destination=destination,
                )
            )

        self._cached_entries = entries
        logger.info(
            f"Loaded credentials config with {len(entries)} repository mapping(s)"
        )
        return self._cached_entries

    def has_config(self) -> bool:
        """Check if credentials config exists and has repository mappings.

        Returns:
            True if credentials config file exists and contains at least
            one repository entry.
        """
        try:
            entries = self.load_config()
            return entries is not None and len(entries) > 0
        except RepoCredentialsError:
            return False

    def copy_to_worktree(
        self, worktree_path: str, repo: str
    ) -> str | None:
        """Copy the matching credential file to a worktree directory.

        Looks up the repo in the loaded credentials config, and if a match
        is found, copies the credential file to the specified destination
        within the worktree.

        Args:
            worktree_path: Path to the worktree directory.
            repo: Repository identifier in hostname/owner/repo format
                (e.g., "github.com/my-org/api-service").

        Returns:
            Absolute path to the copied credential file, or None if no
            matching entry was found or the source file doesn't exist.
        """
        entries = self._cached_entries
        if entries is None:
            entries = self.load_config()
        if not entries:
            return None

        # Normalize the repo identifier to host/owner/repo for matching
        parts = repo.split("/")
        if len(parts) == 3:
            repo_key = repo  # Already host/owner/repo
        elif len(parts) == 2:
            repo_key = repo  # owner/repo — will only match if entry also lacks host
        else:
            repo_key = repo

        # Find matching entry by full host/owner/repo
        matching_entry: RepoCredentialEntry | None = None
        for entry in entries:
            entry_key = f"{entry.host}/{entry.owner}/{entry.repo}"
            if entry_key == repo_key:
                matching_entry = entry
                break

        if matching_entry is None:
            logger.debug(
                f"No credential mapping found for repo '{repo_key}'"
            )
            return None

        # Check source file exists
        source_path = Path(matching_entry.credential_path)
        if not source_path.exists():
            logger.warning(
                f"Credential file not found at {matching_entry.credential_path} "
                f"for repo '{matching_entry.title}'"
            )
            return None

        # Determine destination path
        dest_path = Path(worktree_path) / matching_entry.destination

        # Create parent directories if needed
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        # Copy the credential file
        shutil.copy2(str(source_path), str(dest_path))

        abs_dest = str(dest_path.absolute())
        logger.info(
            f"Copied credentials for '{matching_entry.title}' to {abs_dest}"
        )
        return abs_dest

    def validate_credential_paths(self) -> None:
        """Validate that all configured credential files exist on disk.

        Logs an error for each entry whose credential_path does not exist.
        Does not raise exceptions — intended for startup diagnostics.
        """
        try:
            entries = self.load_config()
        except RepoCredentialsError as e:
            logger.error(f"Failed to load credentials config: {e}")
            return

        if not entries:
            return

        for entry in entries:
            if not Path(entry.credential_path).exists():
                logger.error(
                    f"Credential file not found for '{entry.title}': "
                    f"{entry.credential_path}"
                )

    def clear_cache(self) -> None:
        """Clear the cached configuration.

        Forces the next load_config() call to re-read from disk.
        """
        self._cached_entries = None
        logger.debug("Repo credentials config cache cleared")
