"""GitHub.com implementation of the TicketClient protocol.

This module provides a client for GitHub.com Projects using the GitHub CLI (gh).
It uses github.com-specific APIs like closedByPullRequestsReferences and sub-issues.
"""

import json
import re
import subprocess
from typing import Any

from src.interfaces import LinkedPullRequest, TicketItem
from src.logger import get_logger
from src.ticket_clients.base import GitHubClientBase

logger = get_logger(__name__)


class GitHubTicketClient(GitHubClientBase):
    """GitHub.com implementation of TicketClient protocol.

    Uses github.com-specific APIs including:
    - closedByPullRequestsReferences for linked PR detection
    - sub-issues API for parent/child issue relationships

    For GitHub Enterprise Server, use the version-specific client instead.
    """

    @property
    def supports_linked_prs(self) -> bool:
        """github.com supports closedByPullRequestsReferences."""
        return True

    @property
    def supports_sub_issues(self) -> bool:
        """github.com supports sub-issues API."""
        return True

    @property
    def client_description(self) -> str:
        """Human-readable description of this client."""
        return "GitHub.com"

    def get_linked_prs(self, repo: str, ticket_id: int) -> list[LinkedPullRequest]:
        """Get pull requests that are linked to close this issue.

        Queries the issue's closedByPullRequestsReferences to find PRs with
        linking keywords (closes, fixes, resolves, etc.) pointing to this issue.

        Args:
            repo: Repository in 'hostname/owner/repo' format
            ticket_id: Issue number

        Returns:
            List of LinkedPullRequest objects with PR details
        """
        _, owner, repo_name = self._parse_repo(repo)

        query = """
        query($owner: String!, $repo: String!, $issueNumber: Int!) {
          repository(owner: $owner, name: $repo) {
            issue(number: $issueNumber) {
              closedByPullRequestsReferences(first: 10) {
                nodes {
                  number
                  url
                  body
                  state
                  merged
                  headRefName
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
                logger.debug(f"No issue data found for {repo}#{ticket_id}")
                return []

            pr_nodes = issue_data.get("closedByPullRequestsReferences", {}).get("nodes", [])

            linked_prs = []
            for pr in pr_nodes:
                if pr is None:
                    continue
                linked_prs.append(
                    LinkedPullRequest(
                        number=pr["number"],
                        url=pr["url"],
                        body=pr.get("body", ""),
                        state=pr["state"],
                        merged=pr.get("merged", False),
                        branch_name=pr.get("headRefName"),
                    )
                )

            logger.debug(f"Found {len(linked_prs)} linked PRs for {repo}#{ticket_id}")
            return linked_prs

        except Exception as e:
            logger.error(f"Failed to get linked PRs for {repo}#{ticket_id}: {e}")
            return []

    def get_parent_issue(self, repo: str, ticket_id: int) -> int | None:
        """Get the parent issue number if this issue is a sub-issue.

        Uses GitHub's sub-issues API to check if the given issue has a parent
        issue set.

        Args:
            repo: Repository in 'hostname/owner/repo' format
            ticket_id: Issue number

        Returns:
            Parent issue number if this issue has a parent, None otherwise
        """
        hostname, owner, repo_name = self._parse_repo(repo)

        query = """
        query($owner: String!, $repo: String!, $issueNumber: Int!) {
          repository(owner: $owner, name: $repo) {
            issue(number: $issueNumber) {
              parent {
                number
              }
            }
          }
        }
        """

        try:
            # Sub-issues API requires special header
            response = self._execute_graphql_query_with_headers(
                query,
                {
                    "owner": owner,
                    "repo": repo_name,
                    "issueNumber": ticket_id,
                },
                headers=["GraphQL-Features: sub_issues"],
                hostname=hostname,
            )

            issue_data = response.get("data", {}).get("repository", {}).get("issue")
            if not issue_data:
                logger.debug(f"No issue data found for {repo}#{ticket_id}")
                return None

            parent = issue_data.get("parent")
            if parent is None:
                logger.debug(f"Issue {repo}#{ticket_id} has no parent")
                return None

            parent_number = parent.get("number")
            logger.info(f"Issue {repo}#{ticket_id} has parent issue #{parent_number}")
            return parent_number

        except Exception as e:
            logger.error(f"Failed to get parent issue for {repo}#{ticket_id}: {e}")
            return None

    def get_pr_for_issue(
        self, repo: str, ticket_id: int, state: str = "OPEN"
    ) -> dict[str, str | int] | None:
        """Get a PR that is linked to close this issue.

        Queries the issue's closedByPullRequestsReferences to find PRs with
        linking keywords (closes, fixes, resolves, etc.) pointing to this issue.

        Args:
            repo: Repository in 'hostname/owner/repo' format
            ticket_id: Issue number
            state: PR state filter (default: "OPEN")

        Returns:
            Dict with PR info (number, url, branch_name) or None if not found
        """
        _, owner, repo_name = self._parse_repo(repo)

        query = """
        query($owner: String!, $repo: String!, $issueNumber: Int!) {
          repository(owner: $owner, name: $repo) {
            issue(number: $issueNumber) {
              closedByPullRequestsReferences(first: 10, includeClosedPrs: false) {
                nodes {
                  number
                  url
                  headRefName
                  state
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
                logger.debug(f"No issue data found for {repo}#{ticket_id}")
                return None

            pr_nodes = issue_data.get("closedByPullRequestsReferences", {}).get("nodes", [])

            for pr in pr_nodes:
                if pr is None:
                    continue
                if pr.get("state") == state:
                    result = {
                        "number": pr["number"],
                        "url": pr["url"],
                        "branch_name": pr["headRefName"],
                    }
                    logger.debug(f"Found {state} PR #{pr['number']} for {repo}#{ticket_id}")
                    return result

            logger.debug(f"No {state} PR found for {repo}#{ticket_id}")
            return None

        except Exception as e:
            logger.error(f"Failed to get PR for {repo}#{ticket_id}: {e}")
            return None

    def get_child_issues(self, repo: str, ticket_id: int) -> list[dict[str, int | str]]:
        """Get child issues of a parent issue using sub-issues API.

        Args:
            repo: Repository in 'hostname/owner/repo' format
            ticket_id: Parent issue number

        Returns:
            List of dicts with child issue info: {'number': int, 'state': str}
            Empty list if no children or on error
        """
        hostname, owner, repo_name = self._parse_repo(repo)

        query = """
        query($owner: String!, $repo: String!, $issueNumber: Int!) {
          repository(owner: $owner, name: $repo) {
            issue(number: $issueNumber) {
              subIssues(first: 50) {
                nodes {
                  number
                  state
                }
              }
            }
          }
        }
        """

        try:
            response = self._execute_graphql_query_with_headers(
                query,
                {
                    "owner": owner,
                    "repo": repo_name,
                    "issueNumber": ticket_id,
                },
                headers=["GraphQL-Features: sub_issues"],
                hostname=hostname,
            )

            issue_data = response.get("data", {}).get("repository", {}).get("issue")
            if not issue_data:
                logger.debug(f"No issue data found for {repo}#{ticket_id}")
                return []

            sub_issues = issue_data.get("subIssues", {}).get("nodes", [])
            children = []
            for child in sub_issues:
                if child:
                    children.append({
                        "number": child["number"],
                        "state": child["state"],
                    })

            logger.debug(f"Found {len(children)} child issues for {repo}#{ticket_id}")
            return children

        except Exception as e:
            logger.error(f"Failed to get child issues for {repo}#{ticket_id}: {e}")
            return []

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

    def close_pr(self, repo: str, pr_number: int) -> bool:
        """Close a pull request without merging.

        Args:
            repo: Repository in 'hostname/owner/repo' format
            pr_number: PR number to close

        Returns:
            True if PR was closed successfully, False otherwise
        """
        repo_ref = self._get_repo_ref(repo)
        try:
            args = ["pr", "close", str(pr_number), "--repo", repo_ref]
            self._run_gh_command(args, repo=repo)
            logger.info(f"Closed PR #{pr_number} in {repo}")
            return True
        except subprocess.CalledProcessError as e:
            # PR may already be closed or merged
            logger.warning(f"Failed to close PR #{pr_number} in {repo}: {e.stderr}")
            return False

    def delete_branch(self, repo: str, branch_name: str) -> bool:
        """Delete a remote branch.

        Args:
            repo: Repository in 'hostname/owner/repo' format
            branch_name: Name of the branch to delete

        Returns:
            True if branch was deleted successfully, False otherwise
        """
        hostname, owner, repo_name = self._parse_repo(repo)
        # URL-encode the branch name for the API path
        encoded_branch = branch_name.replace("/", "%2F")
        endpoint = f"repos/{owner}/{repo_name}/git/refs/heads/{encoded_branch}"

        try:
            args = ["api", endpoint, "-X", "DELETE"]
            self._run_gh_command(args, hostname=hostname)
            logger.info(f"Deleted branch '{branch_name}' in {repo}")
            return True
        except subprocess.CalledProcessError as e:
            # Branch may not exist or already be deleted
            error_output = (e.stderr or "").lower()
            if "not found" in error_output or "404" in error_output:
                logger.debug(f"Branch '{branch_name}' not found in {repo}")
            else:
                logger.warning(f"Failed to delete branch '{branch_name}' in {repo}: {e.stderr}")
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

        Uses closedByPullRequestsReferences to get linked PR merge status.
        """
        query = f"""
        query($login: String!, $projectNumber: Int!, $cursor: String) {{
          {entity_type}(login: $login) {{
            projectV2(number: $projectNumber) {{
              items(first: 100, after: $cursor) {{
                pageInfo {{
                  hasNextPage
                  endCursor
                }}
                nodes {{
                  id
                  fieldValues(first: 20) {{
                    nodes {{
                      ... on ProjectV2ItemFieldSingleSelectValue {{
                        name
                        field {{
                          ... on ProjectV2SingleSelectField {{
                            name
                          }}
                        }}
                      }}
                    }}
                  }}
                  content {{
                    ... on Issue {{
                      number
                      title
                      state
                      stateReason
                      repository {{
                        nameWithOwner
                      }}
                      labels(first: 20) {{
                        nodes {{
                          name
                        }}
                      }}
                      closedByPullRequestsReferences(first: 10) {{
                        nodes {{
                          merged
                        }}
                      }}
                      comments {{
                        totalCount
                      }}
                    }}
                  }}
                }}
              }}
            }}
          }}
        }}
        """

        items: list[TicketItem] = []
        cursor: str | None = None
        has_next_page = True
        max_pages = 100
        page_count = 0

        while has_next_page and page_count < max_pages:
            page_count += 1
            prev_cursor = cursor
            variables = {"login": login, "projectNumber": project_number, "cursor": cursor}

            logger.debug(f"Executing GraphQL query page {page_count} with cursor: {cursor}")
            response = self._execute_graphql_query(query, variables, hostname=hostname)

            try:
                project_data = response["data"][entity_type]["projectV2"]
                items_data = project_data["items"]
                page_info = items_data["pageInfo"]
                nodes = items_data["nodes"]

                for node in nodes:
                    item = self._parse_board_item_node(node, board_url, hostname)
                    if item:
                        items.append(item)
                        # Cache repo -> hostname mapping for future API calls
                        self._repo_host_map[item.repo] = hostname

                has_next_page = page_info["hasNextPage"]
                cursor = page_info["endCursor"] if has_next_page else None

                if has_next_page and cursor == prev_cursor:
                    logger.error("Pagination cursor not advancing, breaking loop")
                    break

            except (KeyError, TypeError) as e:
                logger.error(f"Failed to parse GraphQL response: {e}")
                logger.debug(f"Response data: {json.dumps(response, indent=2)}")
                raise ValueError(f"Unexpected GraphQL response structure: {e}") from e

        if page_count >= max_pages:
            logger.warning(f"Reached max pagination limit ({max_pages} pages)")

        return items

    def _parse_board_item_node(
        self, node: dict[str, Any], board_url: str, hostname: str
    ) -> TicketItem | None:
        """Parse a project item node from GraphQL response."""
        try:
            item_id = node["id"]

            content = node.get("content")
            if not content or "number" not in content:
                logger.debug(f"Skipping non-issue item: {item_id}")
                return None

            ticket_id = content["number"]
            title = content["title"]
            name_with_owner = content["repository"]["nameWithOwner"]
            # Include hostname in repo for unambiguous identification
            # Format: hostname/owner/repo (e.g., github.com/owner/repo)
            repo = f"{hostname}/{name_with_owner}"

            label_nodes = content.get("labels", {}).get("nodes", [])
            labels = {label["name"] for label in label_nodes if label}

            state = content.get("state", "OPEN")
            state_reason = content.get("stateReason")

            pr_refs = content.get("closedByPullRequestsReferences", {}).get("nodes", [])
            has_merged_changes = any(pr.get("merged", False) for pr in pr_refs if pr)

            comment_count = content.get("comments", {}).get("totalCount", 0)

            status = "Unknown"
            field_values = node.get("fieldValues", {}).get("nodes", [])
            for field_value in field_values:
                field_info = field_value.get("field", {})
                if field_info.get("name") == "Status":
                    status = field_value.get("name", "Unknown")
                    break

            return TicketItem(
                item_id=item_id,
                board_url=board_url,
                ticket_id=ticket_id,
                repo=repo,
                status=status,
                title=title,
                labels=labels,
                state=state,
                state_reason=state_reason,
                has_merged_changes=has_merged_changes,
                comment_count=comment_count,
            )

        except (KeyError, TypeError) as e:
            logger.warning(f"Failed to parse project item node: {e}")
            logger.debug(f"Node data: {json.dumps(node, indent=2)}")
            return None
