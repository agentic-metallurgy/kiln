"""Base GitHub client with shared functionality.

This module provides the base class for GitHub clients, containing common
GraphQL/REST logic that works across github.com and GitHub Enterprise Server.
"""

import json
import re
import subprocess
from datetime import datetime
from typing import Any

from src.interfaces import Comment, LinkedPullRequest, TicketItem
from src.logger import get_logger, is_debug_mode

logger = get_logger(__name__)


class NetworkError(Exception):
    """Raised when a GitHub API call fails due to network connectivity issues.

    This exception is used to distinguish transient network errors (TLS timeouts,
    connection refused, etc.) from permanent failures (auth errors, invalid requests).
    The daemon uses this to trigger hibernation mode when GitHub API connectivity
    is lost.

    Examples of network errors that should raise this exception:
    - TLS handshake timeout
    - Connection timeout
    - Connection refused
    - Temporary DNS failures
    - I/O timeout

    This exception should NOT be raised for:
    - Authentication errors (bad token, expired token)
    - Permission errors (insufficient scopes)
    - Invalid API requests (bad query, missing fields)
    - Rate limiting (has its own handling)
    """

    pass


class GitHubClientBase:
    """Base class for GitHub clients with shared functionality.

    Provides common token management, GraphQL execution, and methods that
    work identically across github.com and GHES versions.
    """

    # Required OAuth scopes for Kiln operations
    REQUIRED_SCOPES = {"repo", "read:org", "project"}

    # Scopes that grant excessive permissions - reject these for security
    EXCESSIVE_SCOPES = {
        "admin:org",
        "delete_repo",
        "admin:org_hook",
        "admin:repo_hook",
        "admin:public_key",
        "admin:gpg_key",
        "write:org",
        "workflow",
        "delete:packages",
        "codespace",
        "user",
    }

    # Token prefix constants for type detection
    CLASSIC_PAT_PREFIX = "ghp_"
    FINE_GRAINED_PAT_PREFIX = "github_pat_"

    def __init__(self, tokens: dict[str, str] | None = None) -> None:
        """Initialize the GitHub client.

        Args:
            tokens: Dictionary mapping hostname to token, or None to use gh auth login credentials.
                    Example: {"github.com": "ghp_xxx", "github.mycompany.com": "ghp_yyy"}
        """
        self.tokens = tokens or {}
        # Internal cache mapping repo -> hostname, populated by get_board_items()
        self._repo_host_map: dict[str, str] = {}
        logger.debug(f"{self.__class__.__name__} initialized")

    # Feature capability properties - override in subclasses as needed
    @property
    def supports_linked_prs(self) -> bool:
        """Whether this client supports querying linked PRs."""
        return True

    @property
    def supports_sub_issues(self) -> bool:
        """Whether this client supports sub-issues (parent/child relationships)."""
        return True

    @property
    def supports_status_actor_check(self) -> bool:
        """Whether this client supports checking who changed project status."""
        return True

    @property
    def client_description(self) -> str:
        """Human-readable description of this client for logging."""
        return "GitHub"

    def validate_connection(self, hostname: str = "github.com") -> bool:
        """Validate that the client can authenticate with GitHub.

        Makes a simple API call to verify credentials work before entering
        the main poll loop. This provides fast failure with clear error
        messages if authentication is broken.

        Args:
            hostname: GitHub hostname to validate (default: github.com)

        Returns:
            True if authentication succeeds

        Raises:
            RuntimeError: If authentication fails with details about the error
        """
        logger.debug(f"Validating GitHub connection for {hostname}")

        # Simple viewer query - minimal permissions required
        query = """
        query {
          viewer {
            login
          }
        }
        """

        try:
            response = self._execute_graphql_query(query, {}, hostname=hostname)
            viewer = response.get("data", {}).get("viewer")
            login = viewer.get("login") if viewer else None
            if login:
                logger.info(f"GitHub authentication successful for {hostname} as '{login}'")
                return True
            else:
                raise RuntimeError(
                    f"GitHub authentication failed for {hostname}: "
                    "Could not retrieve authenticated user"
                )
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr or e.stdout or str(e)
            raise RuntimeError(f"GitHub authentication failed for {hostname}: {error_msg}") from e
        except ValueError as e:
            raise RuntimeError(f"GitHub authentication failed for {hostname}: {e}") from e

    def _get_token_scopes(self, hostname: str = "github.com") -> set[str] | None:
        """Get the OAuth scopes for the configured token.

        Makes a REST API call with headers to extract the X-OAuth-Scopes header.
        This only works for classic PATs - fine-grained PATs do not expose scopes.

        Args:
            hostname: GitHub hostname to check (default: github.com)

        Returns:
            Set of scope strings (e.g., {"repo", "read:org", "project"}),
            or None if scopes could not be determined (e.g., fine-grained PAT)
        """
        # Build command: gh api -i user (includes headers in output)
        cmd = ["gh", "api", "-i", "user"]
        if hostname != "github.com":
            cmd.extend(["--hostname", hostname])

        try:
            env = {}
            token = self._get_token_for_host(hostname)
            if token:
                # gh CLI uses different env vars for github.com vs GHES
                if hostname == "github.com":
                    env["GITHUB_TOKEN"] = token
                else:
                    env["GH_ENTERPRISE_TOKEN"] = token

            import os

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                env={**os.environ, **env},
            )

            # Parse X-OAuth-Scopes header from response
            # Format: "X-OAuth-Scopes: repo, read:org, project"
            for line in result.stdout.split("\n"):
                if line.lower().startswith("x-oauth-scopes:"):
                    scopes_str = line.split(":", 1)[1].strip()
                    if not scopes_str:
                        return set()
                    # Split on comma, strip whitespace
                    return {s.strip() for s in scopes_str.split(",")}

            # Header not found - likely fine-grained PAT
            logger.debug(f"X-OAuth-Scopes header not found for {hostname}")
            return None

        except subprocess.CalledProcessError as e:
            logger.warning(f"Failed to get token scopes for {hostname}: {e.stderr}")
            return None

    def validate_scopes(self, hostname: str = "github.com") -> bool:
        """Validate that the token has exactly the required OAuth scopes.

        Checks that the configured token has the scopes needed for Kiln operations:
        - repo: Repository access (issues, labels, comments)
        - read:org: Organization read access (projectV2 queries)
        - project: Project V2 read/write access

        Rejects tokens with missing scopes, excessive scopes, or any extra scopes.
        Also rejects fine-grained PATs since their scopes cannot be validated via API.

        Args:
            hostname: GitHub hostname to validate (default: github.com)

        Returns:
            True if validation passes (classic PAT with exact required scopes)

        Raises:
            RuntimeError: If token is fine-grained, has wrong scopes, or validation fails
        """
        logger.debug(f"Validating GitHub token scopes for {hostname}")

        # Check token prefix to detect fine-grained PATs early
        token = self._get_token_for_host(hostname)
        if token and token.startswith(self.FINE_GRAINED_PAT_PREFIX):
            raise RuntimeError(
                f"Fine-grained PAT detected for {hostname} (token starts with 'github_pat_'). "
                "Kiln requires a classic Personal Access Token for scope validation. "
                "Please create a classic PAT with ONLY these scopes: repo, read:org, project. "
                "See: https://github.com/settings/tokens/new?scopes=repo,read:org,project"
            )

        scopes = self._get_token_scopes(hostname)

        if scopes is None:
            # Could not determine scopes - likely fine-grained PAT
            # Fine-grained PATs don't expose scopes via API, so we can't validate them.
            # Require classic PATs for security clarity.
            raise RuntimeError(
                f"Could not verify token scopes for {hostname}. "
                "This usually means you're using a fine-grained PAT, which Kiln does not support. "
                "Please create a classic Personal Access Token with ONLY these scopes: "
                "repo, read:org, project. "
                "See: https://github.com/settings/tokens/new?scopes=repo,read:org,project"
            )

        # Check for missing required scopes or excessive scopes
        missing = self.REQUIRED_SCOPES - scopes
        excessive = scopes & self.EXCESSIVE_SCOPES
        extra = scopes - self.REQUIRED_SCOPES

        if missing or excessive or extra:
            required_scopes = ", ".join(sorted(self.REQUIRED_SCOPES))
            raise RuntimeError(
                f"GitHub (classic) token for {hostname} should ONLY have these scopes: "
                f"{required_scopes}. Provided token either has too many or too few. "
                f"Create a new classic token with {required_scopes} ONLY."
            )

        logger.info(f"GitHub token scopes validated for {hostname}: {', '.join(sorted(scopes))}")
        return True

    def _get_token_for_host(self, hostname: str) -> str | None:
        """Get the token for a specific hostname.

        Args:
            hostname: GitHub hostname (e.g., 'github.com' or 'github.mycompany.com')

        Returns:
            Token for the host, or None if not configured
        """
        return self.tokens.get(hostname)

    def _parse_repo(self, repo: str) -> tuple[str, str, str]:
        """Parse repository string into hostname, owner, and repo name.

        Args:
            repo: Repository in 'hostname/owner/repo' format

        Returns:
            Tuple of (hostname, owner, repo_name)
        """
        parts = repo.split("/")
        if len(parts) >= 3 and "." in parts[0]:
            return parts[0], parts[1], parts[2]
        # Fallback for old format (shouldn't happen in normal operation)
        if len(parts) == 2:
            return "github.com", parts[0], parts[1]
        return "github.com", "", repo

    def _get_hostname_for_repo(self, repo: str) -> str:
        """Get the hostname for a repository.

        Parses the hostname from the repo string (format: hostname/owner/repo).
        Falls back to cache lookup for backward compatibility.

        Args:
            repo: Repository in 'hostname/owner/repo' format

        Returns:
            Hostname for the repo, defaults to 'github.com' if not determinable
        """
        # First try to parse from repo string (new format)
        parts = repo.split("/")
        if len(parts) >= 3 and "." in parts[0]:
            return parts[0]
        # Fallback to cache for backward compat
        return self._repo_host_map.get(repo, "github.com")

    def _get_repo_ref(self, repo: str) -> str:
        """Get the repository reference for gh CLI commands.

        Returns the full URL format which works for both github.com and GHES.

        Args:
            repo: Repository in 'hostname/owner/repo' format

        Returns:
            Full URL like https://hostname/owner/repo
        """
        return f"https://{repo}"

    # Board operations

    def get_board_items(self, board_url: str) -> list[TicketItem]:
        """Get all items from a GitHub project board.

        Args:
            board_url: URL of the GitHub project (e.g.,
                https://github.com/orgs/myorg/projects/1/views/1)

        Returns:
            List of TicketItem objects representing items in the project
        """
        logger.debug(f"Fetching board items from: {board_url}")
        hostname, entity_type, login, project_number = self._parse_board_url(board_url)
        items = self._query_board_items(hostname, entity_type, login, project_number, board_url)
        logger.debug(f"Retrieved {len(items)} board items")
        return items

    def get_board_metadata(self, board_url: str) -> dict:
        """Get GitHub project metadata including status field and options.

        Args:
            board_url: URL of the GitHub project

        Returns:
            Dict with keys: project_id, status_field_id, status_options
        """
        hostname, entity_type, login, project_number = self._parse_board_url(board_url)

        query = f"""
        query($login: String!, $projectNumber: Int!) {{
          {entity_type}(login: $login) {{
            projectV2(number: $projectNumber) {{
              id
              fields(first: 50) {{
                nodes {{
                  ... on ProjectV2SingleSelectField {{
                    id
                    name
                    options {{
                      id
                      name
                    }}
                  }}
                }}
              }}
            }}
          }}
        }}
        """

        response = self._execute_graphql_query(
            query,
            {
                "login": login,
                "projectNumber": project_number,
            },
            hostname=hostname,
        )

        project_data = response.get("data", {}).get(entity_type, {}).get("projectV2", {})
        if not project_data:
            logger.warning(f"Could not fetch project metadata for {board_url}")
            return {"project_id": None, "status_field_id": None, "status_options": {}}

        project_id = project_data.get("id")
        status_field_id = None
        status_options: dict[str, str] = {}

        for field in project_data.get("fields", {}).get("nodes", []):
            if field and field.get("name") == "Status":
                status_field_id = field.get("id")
                for option in field.get("options", []):
                    status_options[option["name"]] = option["id"]
                break

        logger.debug(f"Fetched project metadata: {len(status_options)} status options")
        return {
            "project_id": project_id,
            "status_field_id": status_field_id,
            "status_options": status_options,
        }

    def update_status_field_options(
        self,
        field_id: str,
        options: list[dict],
        hostname: str = "github.com",
    ) -> None:
        """Update the Status field options for a GitHub project.

        Args:
            field_id: The Status field's node ID
            options: List of option dicts with keys: name, color, description
            hostname: GitHub hostname

        Raises:
            ValueError: If the mutation fails
        """
        # Build options input - GraphQL requires specific format
        # ProjectV2SingleSelectFieldOptionInput only accepts: name, color, description
        options_input = []
        for opt in options:
            opt_dict = {
                "name": opt["name"],
                "color": opt["color"],
                "description": opt.get("description", ""),
            }
            options_input.append(opt_dict)

        mutation = """
        mutation($fieldId: ID!, $options: [ProjectV2SingleSelectFieldOptionInput!]!) {
          updateProjectV2Field(input: {
            fieldId: $fieldId
            singleSelectOptions: $options
          }) {
            projectV2Field {
              ... on ProjectV2SingleSelectField {
                id
                options { id name }
              }
            }
          }
        }
        """

        self._execute_graphql_query(
            mutation,
            {"fieldId": field_id, "options": options_input},
            hostname=hostname,
        )
        logger.info(f"Updated Status field options for field {field_id}")

    def update_item_status(
        self, item_id: str, new_status: str, *, hostname: str = "github.com"
    ) -> None:
        """Update the status of a project item.

        Args:
            item_id: The ID of the project item to update
            new_status: The new status value to set
            hostname: GitHub hostname for API calls
        """
        logger.info(f"Updating project item {item_id} to status: {new_status}")

        # Query the item to find its parent project and status field
        item_query = """
        query($itemId: ID!) {
          node(id: $itemId) {
            ... on ProjectV2Item {
              project {
                id
                field(name: "Status") {
                  ... on ProjectV2SingleSelectField {
                    id
                    options {
                      id
                      name
                    }
                  }
                }
              }
            }
          }
        }
        """

        response = self._execute_graphql_query(
            item_query, {"itemId": item_id}, hostname=hostname
        )

        try:
            node = response["data"]["node"]
            project_id = node["project"]["id"]
            field_data = node["project"]["field"]
            field_id = field_data["id"]

            option_id = None
            for option in field_data["options"]:
                if option["name"] == new_status:
                    option_id = option["id"]
                    break

            if not option_id:
                available = [o["name"] for o in field_data["options"]]
                raise ValueError(f"Status '{new_status}' not found. Available: {available}")

        except (KeyError, TypeError) as e:
            raise ValueError(f"Failed to parse project item data: {e}") from e

        mutation = """
        mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $optionId: String!) {
          updateProjectV2ItemFieldValue(
            input: {
              projectId: $projectId
              itemId: $itemId
              fieldId: $fieldId
              value: { singleSelectOptionId: $optionId }
            }
          ) {
            projectV2Item {
              id
            }
          }
        }
        """

        self._execute_graphql_query(
            mutation,
            {
                "projectId": project_id,
                "itemId": item_id,
                "fieldId": field_id,
                "optionId": option_id,
            },
            hostname=hostname,
        )

        logger.info(f"Successfully updated project item {item_id} to '{new_status}'")

    def archive_item(
        self, board_id: str, item_id: str, *, hostname: str = "github.com"
    ) -> bool:
        """Archive a project item.

        Args:
            board_id: The project's node ID
            item_id: The project item's node ID
            hostname: GitHub hostname for API calls

        Returns:
            True if archived successfully, False otherwise
        """
        mutation = """
        mutation($projectId: ID!, $itemId: ID!) {
          archiveProjectV2Item(input: {projectId: $projectId, itemId: $itemId}) {
            item {
              id
            }
          }
        }
        """

        try:
            self._execute_graphql_query(
                mutation,
                {
                    "projectId": board_id,
                    "itemId": item_id,
                },
                hostname=hostname,
            )
            logger.info(f"Archived project item {item_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to archive project item {item_id}: {e}")
            return False

    # Ticket operations

    def get_ticket_body(self, repo: str, ticket_id: int) -> str | None:
        """Get the body/description of an issue.

        Args:
            repo: Repository in 'hostname/owner/repo' format
            ticket_id: Issue number

        Returns:
            The issue body text, or None if the issue doesn't exist
        """
        _, owner, repo_name = self._parse_repo(repo)

        query = """
        query($owner: String!, $repo: String!, $issueNumber: Int!) {
          repository(owner: $owner, name: $repo) {
            issue(number: $issueNumber) {
              body
            }
          }
        }
        """

        try:
            response = self._execute_graphql_query(
                query,
                {
                    "owner": owner,
                    "repo": repo_name,
                    "issueNumber": ticket_id,
                },
                repo=repo,
            )

            issue_data = response.get("data", {}).get("repository", {}).get("issue")
            if issue_data is None:
                return None

            return issue_data.get("body")

        except Exception as e:
            logger.error(f"Failed to get issue body for {repo}#{ticket_id}: {e}")
            return None

    def get_issue_labels(self, repo: str, ticket_id: int) -> set[str]:
        """Get current labels for an issue via GraphQL.

        Args:
            repo: Repository in 'hostname/owner/repo' format
            ticket_id: Issue number

        Returns:
            Set of label names currently on the issue
        """
        _, owner, repo_name = self._parse_repo(repo)

        query = """
        query($owner: String!, $repo: String!, $issueNumber: Int!) {
          repository(owner: $owner, name: $repo) {
            issue(number: $issueNumber) {
              labels(first: 50) {
                nodes {
                  name
                }
              }
            }
          }
        }
        """

        try:
            response = self._execute_graphql_query(
                query,
                {
                    "owner": owner,
                    "repo": repo_name,
                    "issueNumber": ticket_id,
                },
                repo=repo,
            )

            issue_data = response.get("data", {}).get("repository", {}).get("issue")
            if not issue_data:
                return set()

            label_nodes = issue_data.get("labels", {}).get("nodes", [])
            return {label["name"] for label in label_nodes if label}

        except Exception as e:
            logger.error(f"Failed to get issue labels for {repo}#{ticket_id}: {e}")
            return set()

    def add_label(self, repo: str, ticket_id: int, label: str) -> None:
        """Add a label to an issue.

        If the label doesn't exist in the repository, it will be created first.

        Args:
            repo: Repository in 'hostname/owner/repo' format
            ticket_id: Issue number
            label: Label name to add
        """
        repo_ref = self._get_repo_ref(repo)
        args = ["issue", "edit", str(ticket_id), "--repo", repo_ref, "--add-label", label]
        try:
            self._run_gh_command(args, repo=repo)
            logger.info(f"Added label '{label}' to {repo}#{ticket_id}")
        except subprocess.CalledProcessError as e:
            # Check if error is due to label not existing
            error_output = (e.stderr or "") + (e.stdout or "")
            if "label" in error_output.lower() and (
                "not found" in error_output.lower()
                or "does not exist" in error_output.lower()
                or "no labels" in error_output.lower()
            ):
                logger.info(f"Label '{label}' not found in {repo}, creating it")
                if self.create_repo_label(repo, label):
                    # Retry adding the label after creation
                    self._run_gh_command(args, repo=repo)
                    logger.info(f"Added label '{label}' to {repo}#{ticket_id}")
                else:
                    raise RuntimeError(f"Failed to create label '{label}' in {repo}") from e
            else:
                # Re-raise if it's a different error
                raise

    def remove_label(self, repo: str, ticket_id: int, label: str) -> None:
        """Remove a label from an issue.

        Args:
            repo: Repository in 'hostname/owner/repo' format
            ticket_id: Issue number
            label: Label name to remove
        """
        repo_ref = self._get_repo_ref(repo)
        try:
            args = ["issue", "edit", str(ticket_id), "--repo", repo_ref, "--remove-label", label]
            self._run_gh_command(args, repo=repo)
            logger.info(f"Removed label '{label}' from {repo}#{ticket_id}")
        except subprocess.CalledProcessError:
            logger.debug(f"Label '{label}' not on {repo}#{ticket_id} or doesn't exist")

    # Repo label management

    def get_repo_labels(self, repo: str) -> list[str]:
        """Get all labels defined in a repository.

        Args:
            repo: Repository in 'hostname/owner/repo' format
        """
        repo_ref = self._get_repo_ref(repo)
        try:
            args = ["label", "list", "--repo", repo_ref, "--json", "name"]
            output = self._run_gh_command(args, repo=repo)
            data = json.loads(output)
            return [label["name"] for label in data]
        except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
            logger.error(f"Failed to get repo labels for {repo}: {e}")
            return []

    def create_repo_label(
        self, repo: str, name: str, description: str = "", color: str = ""
    ) -> bool:
        """Create a label in a repository if it doesn't exist.

        Args:
            repo: Repository in 'hostname/owner/repo' format
            name: Label name
            description: Label description
            color: Label color (hex code without #)
        """
        repo_ref = self._get_repo_ref(repo)
        args = ["label", "create", name, "--repo", repo_ref, "--force"]
        if description:
            args.extend(["--description", description])
        if color:
            args.extend(["--color", color])

        try:
            self._run_gh_command(args, repo=repo)
            logger.info(f"Created label '{name}' in {repo}")
            return True
        except subprocess.CalledProcessError as e:
            logger.warning(f"Failed to create label '{name}' in {repo}: {e}")
            return False

    # Comment operations

    def get_comments(self, repo: str, ticket_id: int) -> list[Comment]:
        """Get all comments for an issue.

        Args:
            repo: Repository in 'hostname/owner/repo' format
            ticket_id: Issue number

        Returns:
            List of Comment objects, ordered by creation time
        """
        _, owner, repo_name = self._parse_repo(repo)

        query = """
        query($owner: String!, $repo: String!, $issueNumber: Int!, $cursor: String) {
          repository(owner: $owner, name: $repo) {
            issue(number: $issueNumber) {
              comments(first: 100, after: $cursor) {
                pageInfo {
                  hasNextPage
                  endCursor
                }
                nodes {
                  id
                  databaseId
                  body
                  createdAt
                  author {
                    login
                  }
                  thumbsUp: reactions(content: THUMBS_UP, first: 1) {
                    totalCount
                  }
                  eyes: reactions(content: EYES, first: 1) {
                    totalCount
                  }
                }
              }
            }
          }
        }
        """

        comments: list[Comment] = []
        cursor: str | None = None
        has_next_page = True
        max_pages = 100
        page_count = 0

        while has_next_page and page_count < max_pages:
            page_count += 1
            prev_cursor = cursor
            response = self._execute_graphql_query(
                query,
                {
                    "owner": owner,
                    "repo": repo_name,
                    "issueNumber": ticket_id,
                    "cursor": cursor,
                },
                repo=repo,
            )

            try:
                issue_data = response["data"]["repository"]["issue"]
                if issue_data is None:
                    return []
                comments_data = issue_data["comments"]
                page_info = comments_data["pageInfo"]

                for node in comments_data["nodes"]:
                    if node.get("author") is None:
                        continue
                    is_processed = node.get("thumbsUp", {}).get("totalCount", 0) > 0
                    is_processing = node.get("eyes", {}).get("totalCount", 0) > 0
                    comments.append(
                        Comment(
                            id=node["id"],
                            database_id=node["databaseId"],
                            body=node["body"],
                            created_at=datetime.fromisoformat(
                                node["createdAt"].replace("Z", "+00:00")
                            ),
                            author=node["author"]["login"],
                            is_processed=is_processed,
                            is_processing=is_processing,
                        )
                    )

                has_next_page = page_info["hasNextPage"]
                cursor = page_info["endCursor"] if has_next_page else None

                if has_next_page and cursor == prev_cursor:
                    logger.error("Comments pagination cursor not advancing, breaking loop")
                    break

            except (KeyError, TypeError) as e:
                logger.error(f"Failed to parse comments response: {e}")
                return comments

        return comments

    def get_comments_since(self, repo: str, ticket_id: int, since: str | None) -> list[Comment]:
        """Get comments created after a specific timestamp using REST API.

        Args:
            repo: Repository in 'hostname/owner/repo' format
            ticket_id: Issue number
            since: ISO 8601 timestamp, or None for all

        Returns:
            List of comments newer than the timestamp, ordered oldest first
        """
        # Extract owner/repo for REST API endpoint
        _, owner, repo_name = self._parse_repo(repo)
        endpoint = f"repos/{owner}/{repo_name}/issues/{ticket_id}/comments"
        if since:
            normalized_since = since.replace("+00:00", "Z")
            endpoint += f"?since={normalized_since}"

        args = ["api", endpoint, "--paginate"]
        output = self._run_gh_command(args, repo=repo)

        try:
            data = json.loads(output)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse REST API response: {e}")
            return []

        comments: list[Comment] = []
        for item in data:
            if item.get("user") is None:
                continue

            reactions = item.get("reactions", {})
            is_processed = reactions.get("+1", 0) > 0
            is_processing = reactions.get("eyes", 0) > 0

            comments.append(
                Comment(
                    id=item["node_id"],
                    database_id=item["id"],
                    body=item["body"],
                    created_at=datetime.fromisoformat(item["created_at"].replace("Z", "+00:00")),
                    author=item["user"]["login"],
                    is_processed=is_processed,
                    is_processing=is_processing,
                )
            )

        return comments

    def add_comment(self, repo: str, ticket_id: int, body: str) -> Comment:
        """Add a comment to an issue.

        Args:
            repo: Repository in 'hostname/owner/repo' format
            ticket_id: Issue number
            body: Comment body text

        Returns:
            Comment object with the created comment's data
        """
        _, owner, name = self._parse_repo(repo)

        # Get the issue node ID
        issue_query = """
        query($owner: String!, $name: String!, $number: Int!) {
          repository(owner: $owner, name: $name) {
            issue(number: $number) { id }
          }
        }
        """
        result = self._execute_graphql_query(
            issue_query, {"owner": owner, "name": name, "number": ticket_id}, repo=repo
        )
        issue_id = result["data"]["repository"]["issue"]["id"]

        # Add the comment
        add_mutation = """
        mutation($subjectId: ID!, $body: String!) {
          addComment(input: {subjectId: $subjectId, body: $body}) {
            commentEdge {
              node {
                id
                databaseId
                body
                createdAt
                author { login }
              }
            }
          }
        }
        """
        result = self._execute_graphql_query(
            add_mutation, {"subjectId": issue_id, "body": body}, repo=repo
        )
        node = result["data"]["addComment"]["commentEdge"]["node"]
        logger.debug(f"Added comment to {repo}#{ticket_id}")
        return Comment(
            id=node["id"],
            database_id=node["databaseId"],
            body=node["body"],
            created_at=datetime.fromisoformat(node["createdAt"].replace("Z", "+00:00")),
            author=node["author"]["login"],
            is_processed=False,
            is_processing=False,
        )

    def add_reaction(self, comment_id: str, reaction: str, repo: str | None = None) -> None:
        """Add a reaction to a comment.

        Args:
            comment_id: GitHub node ID of the comment
            reaction: Reaction type (THUMBS_UP, EYES, etc.)
            repo: Optional repository to determine hostname for GHE support
        """
        mutation = """
        mutation($subjectId: ID!, $content: ReactionContent!) {
          addReaction(input: {subjectId: $subjectId, content: $content}) {
            reaction {
              content
            }
          }
        }
        """

        self._execute_graphql_query(
            mutation,
            {
                "subjectId": comment_id,
                "content": reaction,
            },
            repo=repo,
        )
        logger.debug(f"Added {reaction} reaction to comment {comment_id}")

    # Security/audit

    def get_last_status_actor(self, repo: str, ticket_id: int) -> str | None:
        """Get the username of who last changed the issue's project status.

        Args:
            repo: Repository in 'hostname/owner/repo' format
            ticket_id: Issue number

        Returns:
            Username of the actor, or None if no project status events found
        """
        _, owner, repo_name = self._parse_repo(repo)

        query = """
        query($owner: String!, $repo: String!, $issueNumber: Int!) {
          repository(owner: $owner, name: $repo) {
            issue(number: $issueNumber) {
              timelineItems(
                itemTypes: [ADDED_TO_PROJECT_V2_EVENT, PROJECT_V2_ITEM_STATUS_CHANGED_EVENT],
                last: 10
              ) {
                nodes {
                  __typename
                  ... on AddedToProjectV2Event {
                    actor { login }
                    createdAt
                  }
                  ... on ProjectV2ItemStatusChangedEvent {
                    actor { login }
                    createdAt
                  }
                }
              }
            }
          }
        }
        """

        try:
            response = self._execute_graphql_query(
                query,
                {
                    "owner": owner,
                    "repo": repo_name,
                    "issueNumber": ticket_id,
                },
                repo=repo,
            )

            issue_data = response.get("data", {}).get("repository", {}).get("issue")
            if not issue_data:
                return None

            nodes = issue_data.get("timelineItems", {}).get("nodes", [])
            if not nodes:
                return None

            for node in reversed(nodes):
                if node and node.get("actor"):
                    return node["actor"].get("login")

            return None

        except Exception as e:
            logger.error(f"Failed to get project status actor for {repo}#{ticket_id}: {e}")
            return None

    def get_label_actor(self, repo: str, ticket_id: int, label_name: str) -> str | None:
        """Get the username of who added a specific label to an issue.

        Queries the issue's timeline for LABELED_EVENT items and finds
        the actor who added the specified label.

        Args:
            repo: Repository in 'hostname/owner/repo' format
            ticket_id: Issue number
            label_name: Name of the label to find the actor for

        Returns:
            Username of the actor who added the label, or None if not found
        """
        _, owner, repo_name = self._parse_repo(repo)

        query = """
        query($owner: String!, $repo: String!, $issueNumber: Int!) {
          repository(owner: $owner, name: $repo) {
            issue(number: $issueNumber) {
              timelineItems(itemTypes: [LABELED_EVENT], last: 50) {
                nodes {
                  ... on LabeledEvent {
                    actor { login }
                    label { name }
                    createdAt
                  }
                }
              }
            }
          }
        }
        """

        try:
            response = self._execute_graphql_query(
                query,
                {
                    "owner": owner,
                    "repo": repo_name,
                    "issueNumber": ticket_id,
                },
                repo=repo,
            )

            issue_data = response.get("data", {}).get("repository", {}).get("issue")
            if not issue_data:
                return None

            nodes = issue_data.get("timelineItems", {}).get("nodes", [])
            if not nodes:
                return None

            # Find the most recent addition of this specific label
            for node in reversed(nodes):
                if node and node.get("label", {}).get("name") == label_name:
                    actor = node.get("actor")
                    if actor:
                        return actor.get("login")

            return None

        except Exception as e:
            logger.error(f"Failed to get label actor for {repo}#{ticket_id}: {e}")
            return None

    # PR operations - these may be overridden by version-specific clients

    def get_linked_prs(self, repo: str, ticket_id: int) -> list[LinkedPullRequest]:
        """Get pull requests that are linked to close this issue.

        This is a base implementation that should be overridden by clients
        that don't support closedByPullRequestsReferences.

        Args:
            repo: Repository in 'hostname/owner/repo' format
            ticket_id: Issue number

        Returns:
            List of LinkedPullRequest objects with PR details
        """
        raise NotImplementedError("Subclasses must implement get_linked_prs")

    def get_parent_issue(self, repo: str, ticket_id: int) -> int | None:
        """Get the parent issue number if this issue is a sub-issue.

        This is a base implementation that should be overridden by clients
        that don't support sub-issues.

        Args:
            repo: Repository in 'hostname/owner/repo' format
            ticket_id: Issue number

        Returns:
            Parent issue number if this issue has a parent, None otherwise
        """
        raise NotImplementedError("Subclasses must implement get_parent_issue")

    def get_pr_for_issue(
        self, repo: str, ticket_id: int, state: str = "OPEN"
    ) -> dict[str, str | int] | None:
        """Get a PR that is linked to close this issue.

        This is a base implementation that should be overridden by clients
        that don't support closedByPullRequestsReferences.

        Args:
            repo: Repository in 'hostname/owner/repo' format
            ticket_id: Issue number
            state: PR state filter (default: "OPEN")

        Returns:
            Dict with PR info (number, url, branch_name) or None if not found
        """
        raise NotImplementedError("Subclasses must implement get_pr_for_issue")

    def get_child_issues(self, repo: str, ticket_id: int) -> list[dict[str, int | str]]:
        """Get child issues of a parent issue using sub-issues API.

        This is a base implementation that should be overridden by clients
        that don't support sub-issues.

        Args:
            repo: Repository in 'hostname/owner/repo' format
            ticket_id: Parent issue number

        Returns:
            List of dicts with child issue info: {'number': int, 'state': str}
            Empty list if no children or on error
        """
        raise NotImplementedError("Subclasses must implement get_child_issues")

    def get_pr_head_sha(self, repo: str, pr_number: int) -> str | None:
        """Get the HEAD commit SHA of a pull request.

        Args:
            repo: Repository in 'hostname/owner/repo' format
            pr_number: Pull request number

        Returns:
            HEAD commit SHA, or None if not found
        """
        _, owner, repo_name = self._parse_repo(repo)

        query = """
        query($owner: String!, $repo: String!, $prNumber: Int!) {
          repository(owner: $owner, name: $repo) {
            pullRequest(number: $prNumber) {
              headRefOid
            }
          }
        }
        """

        try:
            response = self._execute_graphql_query(
                query,
                {
                    "owner": owner,
                    "repo": repo_name,
                    "prNumber": pr_number,
                },
                repo=repo,
            )

            pr_data = response.get("data", {}).get("repository", {}).get("pullRequest")
            if not pr_data:
                logger.debug(f"No PR data found for {repo}#{pr_number}")
                return None

            sha = pr_data.get("headRefOid")
            logger.debug(f"PR {repo}#{pr_number} HEAD SHA: {sha}")
            return sha

        except Exception as e:
            logger.error(f"Failed to get HEAD SHA for PR {repo}#{pr_number}: {e}")
            return None

    def set_commit_status(
        self,
        repo: str,
        sha: str,
        state: str,
        context: str,
        description: str,
        target_url: str | None = None,
    ) -> bool:
        """Set a commit status check on a commit.

        Args:
            repo: Repository in 'hostname/owner/repo' format
            sha: Commit SHA to set status on
            state: Status state ('pending', 'success', 'failure', 'error')
            context: Status context identifier (e.g., 'kiln/child-issues')
            description: Human-readable status description
            target_url: Optional URL with more details

        Returns:
            True if status was set successfully, False otherwise
        """
        hostname, owner, repo_name = self._parse_repo(repo)

        # Use REST API for commit statuses
        endpoint = f"repos/{owner}/{repo_name}/statuses/{sha}"
        payload = {
            "state": state,
            "context": context,
            "description": description,
        }
        if target_url:
            payload["target_url"] = target_url

        try:
            args = ["api", endpoint, "-X", "POST"]
            for key, value in payload.items():
                args.extend(["-f", f"{key}={value}"])

            self._run_gh_command(args, hostname=hostname)
            logger.info(f"Set commit status on {sha[:8]}: {state} ({context})")
            return True

        except Exception as e:
            logger.error(f"Failed to set commit status on {sha}: {e}")
            return False

    def remove_pr_issue_link(self, repo: str, pr_number: int, issue_number: int) -> bool:
        """Remove the linking keyword from a PR body while preserving the issue reference.

        Edits the PR body to remove keywords like 'closes', 'fixes', 'resolves'
        while keeping the issue number as a breadcrumb (e.g., 'closes #44' -> '#44').

        Args:
            repo: Repository in 'hostname/owner/repo' format
            pr_number: PR number to edit
            issue_number: Issue number whose linking keyword should be removed

        Returns:
            True if the PR was edited, False if no linking keyword was found
        """
        # First, get the current PR body
        _, owner, repo_name = self._parse_repo(repo)

        query = """
        query($owner: String!, $repo: String!, $prNumber: Int!) {
          repository(owner: $owner, name: $repo) {
            pullRequest(number: $prNumber) {
              body
            }
          }
        }
        """

        try:
            response = self._execute_graphql_query(
                query,
                {
                    "owner": owner,
                    "repo": repo_name,
                    "prNumber": pr_number,
                },
                repo=repo,
            )

            pr_data = response.get("data", {}).get("repository", {}).get("pullRequest")
            if not pr_data:
                logger.warning(f"Could not find PR {repo}#{pr_number}")
                return False

            original_body = pr_data.get("body", "")
            new_body = self._remove_closes_keyword(original_body, issue_number)

            if new_body == original_body:
                logger.debug(
                    f"No linking keyword found for #{issue_number} in PR {repo}#{pr_number}"
                )
                return False

            # Update the PR body using gh CLI
            repo_ref = self._get_repo_ref(repo)
            args = ["pr", "edit", str(pr_number), "--repo", repo_ref, "--body", new_body]
            self._run_gh_command(args, repo=repo)

            logger.info(f"Removed linking keyword for #{issue_number} from PR {repo}#{pr_number}")
            return True

        except Exception as e:
            logger.error(f"Failed to remove linking keyword from PR {repo}#{pr_number}: {e}")
            return False

    def _remove_closes_keyword(self, body: str, issue_number: int) -> str:
        """Remove linking keywords for a specific issue from PR body text.

        Removes keywords (close, closes, closed, fix, fixes, fixed, resolve,
        resolves, resolved) that link to the specified issue number, while
        preserving the issue reference as a breadcrumb.

        Args:
            body: PR body text
            issue_number: Issue number to unlink

        Returns:
            Modified body with linking keywords removed
        """
        # Pattern matches: keyword + optional colon + whitespace + #issue_number
        # Keywords: close, closes, closed, fix, fixes, fixed, resolve, resolves, resolved
        # Examples: "closes #44", "Fixes: #123", "resolves #44"
        pattern = rf"\b(close[sd]?|fix(?:e[sd])?|resolve[sd]?):?\s*#{issue_number}\b"

        def replace_fn(_match: re.Match[str]) -> str:
            # Keep just the issue reference as a breadcrumb
            return f"#{issue_number}"

        return re.sub(pattern, replace_fn, body, flags=re.IGNORECASE)

    # Internal helpers

    def _parse_board_url(self, board_url: str) -> tuple[str, str, str, int]:
        """Parse a GitHub project URL to extract hostname, entity type, login and project number.

        Args:
            board_url: URL of the GitHub project

        Returns:
            Tuple of (hostname, entity_type, login, project_number)
            entity_type is "organization" or "user"

        Raises:
            ValueError: If the URL format is invalid
        """
        # Try org pattern: https://{hostname}/orgs/{org}/projects/{number}
        org_pattern = r"https?://([^/]+)/orgs/([^/]+)/projects/(\d+)"
        org_match = re.search(org_pattern, board_url)
        if org_match:
            return org_match.group(1), "organization", org_match.group(2), int(org_match.group(3))

        # Try user pattern: https://{hostname}/users/{user}/projects/{number}
        user_pattern = r"https?://([^/]+)/users/([^/]+)/projects/(\d+)"
        user_match = re.search(user_pattern, board_url)
        if user_match:
            return user_match.group(1), "user", user_match.group(2), int(user_match.group(3))

        raise ValueError(
            f"Invalid project URL format: {board_url}. "
            "Expected format: https://HOSTNAME/orgs/ORG/projects/NUMBER "
            "or https://HOSTNAME/users/USER/projects/NUMBER"
        )

    def _query_board_items(
        self, hostname: str, entity_type: str, login: str, project_number: int, board_url: str
    ) -> list[TicketItem]:
        """Query GitHub API for project items using GraphQL.

        This method should be overridden by version-specific clients that need
        different GraphQL queries (e.g., without closedByPullRequestsReferences).
        """
        raise NotImplementedError("Subclasses must implement _query_board_items")

    def _parse_board_item_node(
        self, node: dict[str, Any], board_url: str, hostname: str
    ) -> TicketItem | None:
        """Parse a project item node from GraphQL response.

        This method should be overridden by version-specific clients that parse
        different response structures.
        """
        raise NotImplementedError("Subclasses must implement _parse_board_item_node")

    def _execute_graphql_query(
        self,
        query: str,
        variables: dict[str, Any],
        *,
        hostname: str | None = None,
        repo: str | None = None,
    ) -> dict[str, Any]:
        """Execute a GraphQL query using gh CLI.

        Args:
            query: GraphQL query string
            variables: Variables to pass to the query
            hostname: Explicit hostname (for board operations)
            repo: Repository to look up hostname for (for repo operations)
        """
        if hostname is None:
            hostname = self._get_hostname_for_repo(repo) if repo else "github.com"

        payload = {
            "query": query,
            "variables": variables,
        }

        output = self._run_gh_command(
            ["api", "graphql", "--input", "-"],
            input_data=json.dumps(payload),
            hostname=hostname,
        )

        try:
            response = json.loads(output)

            if "errors" in response:
                error_messages = [e.get("message", str(e)) for e in response["errors"]]
                raise ValueError(f"GraphQL errors: {', '.join(error_messages)}")

            return response

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.debug(f"Raw output: {output}")
            raise ValueError(f"Invalid JSON response from gh CLI: {e}") from e

    def _execute_graphql_query_with_headers(
        self,
        query: str,
        variables: dict[str, Any],
        headers: list[str],
        *,
        hostname: str | None = None,
        repo: str | None = None,
    ) -> dict[str, Any]:
        """Execute a GraphQL query with custom headers using gh CLI.

        Args:
            query: GraphQL query string
            variables: Variables to pass to the query
            headers: List of headers in "Name: Value" format
            hostname: Explicit hostname (for board operations)
            repo: Repository to look up hostname for (for repo operations)
        """
        if hostname is None:
            hostname = self._get_hostname_for_repo(repo) if repo else "github.com"

        payload = {
            "query": query,
            "variables": variables,
        }

        # Build command with headers
        cmd_args = ["api", "graphql", "--input", "-"]
        for header in headers:
            cmd_args.extend(["-H", header])

        output = self._run_gh_command(
            cmd_args,
            input_data=json.dumps(payload),
            hostname=hostname,
        )

        try:
            response = json.loads(output)

            if "errors" in response:
                error_messages = [e.get("message", str(e)) for e in response["errors"]]
                raise ValueError(f"GraphQL errors: {', '.join(error_messages)}")

            return response

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.debug(f"Raw output: {output}")
            raise ValueError(f"Invalid JSON response from gh CLI: {e}") from e

    def _run_gh_command(
        self,
        args: list[str],
        input_data: str | None = None,
        *,
        hostname: str | None = None,
        repo: str | None = None,
    ) -> str:
        """Run a gh CLI command with proper error handling.

        Args:
            args: Command arguments (excluding 'gh' itself)
            input_data: Optional data to pass to stdin
            hostname: Explicit hostname (for board operations)
            repo: Repository to look up hostname for (for repo operations)

        Returns:
            Command output as string

        Raises:
            subprocess.CalledProcessError: If the command fails
        """
        if hostname is None:
            hostname = self._get_hostname_for_repo(repo) if repo else "github.com"

        cmd = ["gh"]
        # Add --hostname flag for non-github.com hosts on API commands
        if hostname != "github.com" and args and args[0] == "api":
            cmd.extend(["api", "--hostname", hostname] + args[1:])
        else:
            cmd.extend(args)
        logger.debug(f"Running command: {' '.join(cmd)}")

        try:
            env = {}
            token = self._get_token_for_host(hostname)
            if token:
                # gh CLI uses different env vars for github.com vs GHES
                if hostname == "github.com":
                    env["GITHUB_TOKEN"] = token
                else:
                    env["GH_ENTERPRISE_TOKEN"] = token

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                input=input_data,
                env={**subprocess.os.environ, **env},
            )

            logger.debug(f"Command succeeded, output length: {len(result.stdout)} bytes")
            return result.stdout

        except subprocess.CalledProcessError as e:
            logger.error(f"Command failed with exit code {e.returncode}")
            logger.error(f"Error output: {e.stderr}")
            # Check for authentication errors and provide user-friendly message
            error_output = (e.stderr or "").lower()
            if any(
                indicator in error_output
                for indicator in [
                    "gh auth login",
                    "authentication",
                    "unauthorized",
                    "401",
                    "not logged in",
                    "no token",
                ]
            ):
                if is_debug_mode():
                    raise RuntimeError(
                        f"GitHub authentication failed for {hostname}.\n"
                        f"Please ensure GITHUB_TOKEN is set in .kiln/config or run 'gh auth login'.\n"
                        f"Error: {e.stderr}"
                    ) from e
                else:
                    raise RuntimeError(
                        f"GitHub authentication failed for {hostname}. "
                        f"Please set GITHUB_TOKEN in .kiln/config"
                    ) from e
            raise
        except FileNotFoundError as e:
            logger.error("gh CLI not found. Please install GitHub CLI: https://cli.github.com/")
            raise RuntimeError(
                "GitHub CLI (gh) is not installed or not in PATH. "
                "Please install it from https://cli.github.com/"
            ) from e
