"""
Workspace management module for agentic-metallurgy.

Provides WorkspaceManager class for creating and managing git worktrees
for individual issues.
"""

import contextlib
import subprocess
from pathlib import Path

from src.logger import get_logger

logger = get_logger(__name__)


class WorkspaceError(Exception):
    """Base exception for workspace management errors."""

    pass


class WorkspaceManager:
    """
    Manages git worktrees for individual issues.

    Creates isolated working directories for each issue using git worktrees,
    allowing concurrent work on multiple issues from the same repository.
    """

    def __init__(self, workspace_dir: str):
        """
        Initialize the workspace manager.

        Args:
            workspace_dir: Base directory for all worktrees and repository clones
        """
        self.workspace_dir = Path(workspace_dir).resolve()

        # Create directories if they don't exist
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

        logger.debug(f"WorkspaceManager initialized with workspace_dir: {self.workspace_dir}")

    def _extract_repo_name(self, repo_url: str) -> str:
        """
        Extract repository name from URL.

        Args:
            repo_url: Git repository URL

        Returns:
            Repository name (e.g., "repo" from "https://github.com/org/repo.git")

        Examples:
            https://github.com/org/repo -> repo
            https://github.com/org/repo.git -> repo
            git@github.com:org/repo.git -> repo
        """
        # Remove trailing .git if present
        url = repo_url.rstrip("/")
        if url.endswith(".git"):
            url = url[:-4]

        # Extract the last component of the path
        repo_name = url.split("/")[-1]

        logger.debug(f"Extracted repo name '{repo_name}' from URL: {repo_url}")
        return repo_name

    def _run_git_command(
        self, args: list[str], cwd: Path | None = None, check: bool = True
    ) -> subprocess.CompletedProcess:
        """
        Run a git command with proper error handling.

        Args:
            args: Git command arguments (without 'git' prefix)
            cwd: Working directory for the command
            check: Whether to raise exception on non-zero exit code

        Returns:
            CompletedProcess instance

        Raises:
            WorkspaceError: If command fails and check=True
        """
        cmd = ["git"] + args
        logger.debug(f"Running git command: {' '.join(cmd)}" + (f" in {cwd}" if cwd else ""))

        # Validate cwd is within workspace boundaries if provided
        if cwd is not None:
            cwd_resolved = Path(cwd).resolve()
            # cwd must be under workspace_dir
            if not cwd_resolved.is_relative_to(self.workspace_dir):
                raise WorkspaceError(
                    f"Security violation: git command cwd '{cwd_resolved}' is outside "
                    f"workspace boundaries ('{self.workspace_dir}')"
                )

        try:
            result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=check)

            if result.stdout:
                logger.debug(f"Git stdout: {result.stdout.strip()}")
            if result.stderr:
                logger.debug(f"Git stderr: {result.stderr.strip()}")

            return result

        except subprocess.CalledProcessError as e:
            error_msg = f"Git command failed: {' '.join(cmd)}\n"
            error_msg += f"Exit code: {e.returncode}\n"
            if e.stdout:
                error_msg += f"Stdout: {e.stdout}\n"
            if e.stderr:
                error_msg += f"Stderr: {e.stderr}"
            logger.error(error_msg)
            raise WorkspaceError(error_msg) from e

    def _validate_path_containment(self, path: Path, container: Path, context: str) -> Path:
        """
        Validate that a path is contained within a container directory.

        Args:
            path: Path to validate (will be resolved to absolute)
            container: Container directory the path must be within
            context: Description for error messages (e.g., "worktree path")

        Returns:
            The resolved absolute path

        Raises:
            WorkspaceError: If path would escape the container directory
        """
        resolved = path.resolve()
        container_resolved = container.resolve()

        if not resolved.is_relative_to(container_resolved):
            raise WorkspaceError(
                f"Security violation: {context} '{resolved}' is outside "
                f"allowed directory '{container_resolved}'"
            )

        return resolved

    def _validate_name_component(self, name: str, context: str) -> None:
        """
        Validate that a name component doesn't contain path traversal sequences.

        Args:
            name: Name to validate (e.g., repo_name)
            context: Description for error messages

        Raises:
            WorkspaceError: If name contains path separators or traversal sequences
        """
        # Check for path separators and traversal patterns
        forbidden = ["/", "\\", ".."]
        for pattern in forbidden:
            if pattern in name:
                raise WorkspaceError(
                    f"Security violation: {context} '{name}' contains "
                    f"forbidden path component '{pattern}'"
                )

    def _ensure_repo_cloned(self, repo_url: str, repo_name: str) -> Path:
        """
        Ensure the main repository is cloned.

        Args:
            repo_url: Git repository URL
            repo_name: Repository name

        Returns:
            Path to the cloned repository

        Raises:
            WorkspaceError: If clone fails
        """
        self._validate_name_component(repo_name, "repository name")
        repo_path = self._validate_path_containment(
            self.workspace_dir / repo_name, self.workspace_dir, "repository path"
        )

        if repo_path.exists():
            logger.info(f"Repository '{repo_name}' already cloned at {repo_path}")
            # Verify it's a valid git repository
            if not (repo_path / ".git").exists():
                raise WorkspaceError(f"Directory exists but is not a git repository: {repo_path}")
            return repo_path

        logger.info(f"Cloning repository '{repo_url}' to {repo_path}")
        self._run_git_command(["clone", repo_url, str(repo_path)])
        logger.info(f"Successfully cloned repository to {repo_path}")

        return repo_path

    def get_workspace_path(self, repo_name: str, issue_number: int) -> str:
        """
        Get the expected workspace path for a repository and issue.

        Args:
            repo_name: Repository name
            issue_number: Issue number

        Returns:
            Absolute path to the workspace (may not exist)
        """
        self._validate_name_component(repo_name, "repository name")
        worktree_name = f"{repo_name}-issue-{issue_number}"
        worktree_path = self._validate_path_containment(
            self.workspace_dir / worktree_name, self.workspace_dir, "worktree path"
        )
        return str(worktree_path)

    def cleanup_workspace(self, repo_name: str, issue_number: int) -> None:
        """
        Remove a worktree and its directory.

        Args:
            repo_name: Repository name
            issue_number: Issue number

        Raises:
            WorkspaceError: If cleanup fails
        """
        worktree_path = Path(self.get_workspace_path(repo_name, issue_number))
        # get_workspace_path already validates, but double-check worktree_path
        self._validate_path_containment(worktree_path, self.workspace_dir, "worktree path")

        self._validate_name_component(repo_name, "repository name")
        repo_path = self._validate_path_containment(
            self.workspace_dir / repo_name, self.workspace_dir, "repository path"
        )

        if not worktree_path.exists():
            logger.warning(f"Worktree does not exist: {worktree_path}")
            return

        logger.info(f"Cleaning up worktree at {worktree_path}")

        # Remove the worktree using git worktree remove --force
        if repo_path.exists():
            self._run_git_command(
                ["worktree", "remove", "--force", str(worktree_path)], cwd=repo_path
            )
            logger.info("Successfully removed worktree via git")
            logger.info(f"Successfully cleaned up workspace for {repo_name} issue {issue_number}")
        else:
            logger.warning(f"Repository not found at {repo_path}, cannot clean worktree")
            raise WorkspaceError(f"Cannot cleanup worktree: repository not found at {repo_path}")

    def rebase_from_main(self, worktree_path: str) -> bool:
        """
        Rebase the worktree's branch from origin/main.

        Args:
            worktree_path: Path to the worktree to rebase

        Returns:
            True if rebase succeeded, False if conflicts occurred

        Raises:
            WorkspaceError: If git commands fail for reasons other than conflicts
        """
        worktree = Path(worktree_path)

        if not worktree.exists():
            logger.warning(f"Worktree does not exist: {worktree_path}")
            return False

        logger.info(f"Fetching origin/main for {worktree_path}")
        self._run_git_command(["fetch", "origin", "main"], cwd=worktree)

        logger.info("Rebasing from origin/main")
        try:
            self._run_git_command(["rebase", "origin/main"], cwd=worktree)
            logger.info("Rebase completed successfully")
            return True
        except WorkspaceError as e:
            if "conflict" in str(e).lower() or "could not apply" in str(e).lower():
                logger.warning(f"Rebase failed due to conflicts: {e}")
                with contextlib.suppress(WorkspaceError):
                    self._run_git_command(["rebase", "--abort"], cwd=worktree, check=False)
                return False
            raise
