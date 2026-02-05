"""Repository credentials module for kiln.

This module provides management of repository credential files,
including loading mappings from .kiln/credentials.yaml and copying
credential files (e.g., .env) into worktrees before workflow execution.
"""

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

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


@dataclass
class RepoCredentialEntry:
    """Represents a single repository credential mapping.

    Attributes:
        title: Human-readable label for the repository.
        owner: GitHub organization or user (e.g., "my-org").
        repo: Repository name (e.g., "api-service").
        credential_path: Absolute path to the credential file on disk.
        destination: Where to place the file in the worktree (default: ".env").
    """

    title: str
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
            required_fields = ["title", "owner", "repo", "credential_path"]
            for field in required_fields:
                if field not in repo_entry:
                    raise RepoCredentialsLoadError(
                        f"Repository entry {i} is missing required field '{field}'"
                    )

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
                    owner=str(repo_entry["owner"]),
                    repo=str(repo_entry["repo"]),
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

        # Extract owner/repo from hostname/owner/repo format
        parts = repo.split("/")
        owner_repo = f"{parts[-2]}/{parts[-1]}" if len(parts) >= 2 else repo

        # Find matching entry
        matching_entry: RepoCredentialEntry | None = None
        for entry in entries:
            entry_key = f"{entry.owner}/{entry.repo}"
            if entry_key == owner_repo:
                matching_entry = entry
                break

        if matching_entry is None:
            logger.debug(
                f"No credential mapping found for repo '{owner_repo}'"
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

    def clear_cache(self) -> None:
        """Clear the cached configuration.

        Forces the next load_config() call to re-read from disk.
        """
        self._cached_entries = None
        logger.debug("Repo credentials config cache cleared")
