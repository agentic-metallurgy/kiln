"""GitHub Enterprise Server 3.14 implementation of the TicketClient protocol.

This module provides a client for GHES 3.14 Projects using the GitHub CLI (gh).
It uses alternative APIs since GHES 3.14 lacks certain github.com features:
- closedByPullRequestsReferences is NOT available (uses CLOSED_EVENT instead)
- sub-issues API is NOT available
- Project V2 timeline events don't exist (uses field creator instead)

Key alternative approaches:
- Merged PR detection: timelineItems with CLOSED_EVENT
- Linked PRs: timelineItems with CrossReferencedEvent + closing keywords
- Status actor: projectsV2 -> items -> fieldValues -> Status -> creator
"""

import json
import re
from typing import Any

from src.interfaces import LinkedPullRequest, TicketItem
from src.logger import get_logger
from src.ticket_clients.base import GitHubClientBase

logger = get_logger(__name__)

# Closing keywords that GitHub recognizes
# See: https://docs.github.com/en/issues/tracking-your-work-with-issues/linking-a-pull-request-to-an-issue
CLOSING_KEYWORDS = [
    "close",
    "closes",
    "closed",
    "fix",
    "fixes",
    "fixed",
    "resolve",
    "resolves",
    "resolved",
]


class GitHubEnterprise314Client(GitHubClientBase):
    """GitHub Enterprise Server 3.14 implementation of TicketClient protocol.

    Uses alternative APIs for features not available in GHES 3.14:
    - timelineItems + CLOSED_EVENT for merged PR detection in board queries
    - timelineItems + CrossReferencedEvent for linked PR detection
    - projectsV2 -> items -> fieldValues -> Status -> creator for actor check
    - Sub-issues API is disabled (not available in GHES 3.14)

    Note: The CrossReferencedEvent approach for linked PRs may include PRs that
    mention but don't actually close the issue. We filter by closing keywords to
    reduce false positives.
    """

    @property
    def supports_linked_prs(self) -> bool:
        """GHES 3.14 supports linked PRs via CrossReferencedEvent alternative."""
        return True

    @property
    def supports_sub_issues(self) -> bool:
        """GHES 3.14 does NOT support sub-issues API."""
        return False

    @property
    def supports_status_actor_check(self) -> bool:
        """GHES 3.14 supports status actor check via field creator."""
        return True

    @property
    def client_description(self) -> str:
        """Human-readable description of this client."""
        return "GitHub Enterprise Server 3.14"

    def get_last_status_actor(self, repo: str, ticket_id: int) -> str | None:
        """Get the username of who last changed the issue's project status.

        GHES 3.14 does NOT support ADDED_TO_PROJECT_V2_EVENT or
        PROJECT_V2_ITEM_STATUS_CHANGED_EVENT timeline item types.

        Instead, we use the 'creator' field on the Status field value.
        This queries the issue's projectsV2 connection to find the item and
        extract the creator of the current status field value.

        Args:
            repo: Repository in 'hostname/owner/repo' format
            ticket_id: Issue number

        Returns:
            Username of the actor who set the current status, or None if not found
        """
        _, owner, repo_name = self._parse_repo(repo)

        # Query through issue -> projectsV2 -> items -> fieldValues
        query = """
        query($owner: String!, $repo: String!, $issueNumber: Int!) {
          repository(owner: $owner, name: $repo) {
            issue(number: $issueNumber) {
              projectsV2(first: 10) {
                nodes {
                  items(first: 100) {
                    nodes {
                      fieldValues(first: 20) {
                        nodes {
                          ... on ProjectV2ItemFieldSingleSelectValue {
                            field {
                              ... on ProjectV2SingleSelectField {
                                name
                              }
                            }
                            creator {
                              login
                            }
                          }
                        }
                      }
                      content {
                        ... on Issue {
                          number
                        }
                      }
                    }
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
                logger.debug(f"No issue data found for {repo}#{ticket_id}")
                return None

            projects = issue_data.get("projectsV2", {}).get("nodes", [])
            if not projects:
                logger.debug(f"No projects found for {repo}#{ticket_id}")
                return None

            # Look through all projects and their items for our issue
            for project in projects:
                if not project:
                    continue
                items = project.get("items", {}).get("nodes", [])
                for item in items:
                    if not item:
                        continue
                    # Check if this item is our issue
                    content = item.get("content", {})
                    if content.get("number") != ticket_id:
                        continue
                    # Found our issue - look for Status field creator
                    field_values = item.get("fieldValues", {}).get("nodes", [])
                    for field_value in field_values:
                        if not field_value:
                            continue
                        field_info = field_value.get("field", {})
                        if field_info.get("name") == "Status":
                            creator = field_value.get("creator")
                            if creator:
                                login = creator.get("login")
                                logger.debug(f"Found status actor for {repo}#{ticket_id}: {login}")
                                return login

            logger.debug(f"No Status field creator found for {repo}#{ticket_id}")
            return None

        except Exception as e:
            logger.error(f"Failed to get project status actor for {repo}#{ticket_id}: {e}")
            return None

    def _has_closing_keyword(self, pr_body: str | None, issue_number: int) -> bool:
        """Check if PR body contains a closing keyword for the given issue.

        Args:
            pr_body: Pull request body text
            issue_number: Issue number to check for

        Returns:
            True if PR body contains a closing keyword linking to the issue
        """
        if not pr_body:
            return False

        # Build pattern: (keyword) + optional colon + whitespace + #issue_number
        keywords_pattern = "|".join(CLOSING_KEYWORDS)
        pattern = rf"\b({keywords_pattern}):?\s*#?{issue_number}\b"

        return bool(re.search(pattern, pr_body, re.IGNORECASE))

    def _get_cross_referenced_prs(
        self, repo: str, ticket_id: int, filter_by_closing_keywords: bool = True
    ) -> list[dict[str, Any]]:
        """Get PRs that cross-reference this issue using timelineItems API.

        Args:
            repo: Repository in 'hostname/owner/repo' format
            ticket_id: Issue number
            filter_by_closing_keywords: If True, only return PRs with closing keywords

        Returns:
            List of PR data dicts with number, url, body, state, merged, headRefName
        """
        _, owner, repo_name = self._parse_repo(repo)

        query = """
        query($owner: String!, $repo: String!, $issueNumber: Int!) {
          repository(owner: $owner, name: $repo) {
            issue(number: $issueNumber) {
              timelineItems(itemTypes: [CROSS_REFERENCED_EVENT], first: 100) {
                nodes {
                  ... on CrossReferencedEvent {
                    source {
                      ... on PullRequest {
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

            timeline_nodes = issue_data.get("timelineItems", {}).get("nodes", [])

            prs = []
            for node in timeline_nodes:
                if not node:
                    continue
                source = node.get("source")
                if not source or "number" not in source:
                    # Not a PR or missing data
                    continue

                # Filter by closing keywords if requested
                if filter_by_closing_keywords:
                    if not self._has_closing_keyword(source.get("body"), ticket_id):
                        logger.debug(
                            f"PR #{source['number']} references #{ticket_id} but has no closing keyword"
                        )
                        continue

                prs.append(source)

            return prs

        except Exception as e:
            logger.error(f"Failed to get cross-referenced PRs for {repo}#{ticket_id}: {e}")
            return []

    def get_linked_prs(self, repo: str, ticket_id: int) -> list[LinkedPullRequest]:
        """Get pull requests that are linked to close this issue.

        Uses timelineItems + CrossReferencedEvent as an alternative to
        closedByPullRequestsReferences (which is not available in GHES 3.14).
        Filters by closing keywords to reduce false positives.

        Args:
            repo: Repository in 'hostname/owner/repo' format
            ticket_id: Issue number

        Returns:
            List of LinkedPullRequest objects with PR details
        """
        prs = self._get_cross_referenced_prs(repo, ticket_id, filter_by_closing_keywords=True)

        linked_prs = []
        for pr in prs:
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

        logger.debug(f"Found {len(linked_prs)} linked PRs for {repo}#{ticket_id} (via CrossReferencedEvent)")
        return linked_prs

    def get_parent_issue(self, repo: str, ticket_id: int) -> int | None:
        """Get the parent issue number if this issue is a sub-issue.

        GHES 3.14 does NOT support sub-issues API, so this always returns None.

        Args:
            repo: Repository in 'hostname/owner/repo' format
            ticket_id: Issue number

        Returns:
            Always None (sub-issues not supported)
        """
        logger.debug(f"Sub-issues not supported in GHES 3.14, returning None for {repo}#{ticket_id}")
        return None

    def get_pr_for_issue(
        self, repo: str, ticket_id: int, state: str = "OPEN"
    ) -> dict[str, str | int] | None:
        """Get a PR that is linked to close this issue.

        Uses timelineItems + CrossReferencedEvent as an alternative to
        closedByPullRequestsReferences (which is not available in GHES 3.14).

        Args:
            repo: Repository in 'hostname/owner/repo' format
            ticket_id: Issue number
            state: PR state filter (default: "OPEN")

        Returns:
            Dict with PR info (number, url, branch_name) or None if not found
        """
        prs = self._get_cross_referenced_prs(repo, ticket_id, filter_by_closing_keywords=True)

        for pr in prs:
            if pr.get("state") == state:
                result = {
                    "number": pr["number"],
                    "url": pr["url"],
                    "branch_name": pr.get("headRefName", ""),
                }
                logger.debug(f"Found {state} PR #{pr['number']} for {repo}#{ticket_id}")
                return result

        logger.debug(f"No {state} PR found for {repo}#{ticket_id}")
        return None

    def get_child_issues(self, repo: str, ticket_id: int) -> list[dict[str, int | str]]:
        """Get child issues of a parent issue.

        GHES 3.14 does NOT support sub-issues API, so this always returns empty list.

        Args:
            repo: Repository in 'hostname/owner/repo' format
            ticket_id: Parent issue number

        Returns:
            Always empty list (sub-issues not supported)
        """
        logger.debug(f"Sub-issues not supported in GHES 3.14, returning [] for {repo}#{ticket_id}")
        return []

    def _query_board_items(
        self, hostname: str, entity_type: str, login: str, project_number: int, board_url: str
    ) -> list[TicketItem]:
        """Query GitHub API for project items using GraphQL.

        Uses timelineItems with CLOSED_EVENT instead of closedByPullRequestsReferences
        (which is not available in GHES 3.14). The CLOSED_EVENT provides the closer,
        which can be a merged PR.
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
                      comments {{
                        totalCount
                      }}
                      timelineItems(itemTypes: [CLOSED_EVENT], last: 1) {{
                        nodes {{
                          ... on ClosedEvent {{
                            closer {{
                              ... on PullRequest {{
                                merged
                              }}
                            }}
                          }}
                        }}
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
        """Parse a project item node from GraphQL response.

        Uses timelineItems CLOSED_EVENT to detect merged PRs instead of
        closedByPullRequestsReferences (which is not available in GHES 3.14).
        """
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
            # Format: hostname/owner/repo (e.g., github.mycompany.com/owner/repo)
            repo = f"{hostname}/{name_with_owner}"

            label_nodes = content.get("labels", {}).get("nodes", [])
            labels = {label["name"] for label in label_nodes if label}

            state = content.get("state", "OPEN")
            state_reason = content.get("stateReason")

            # GHES 3.14: Check timelineItems CLOSED_EVENT for merged PR
            has_merged_changes = False
            timeline_nodes = content.get("timelineItems", {}).get("nodes", [])
            for event in timeline_nodes:
                if event:
                    closer = event.get("closer")
                    if closer and closer.get("merged"):
                        has_merged_changes = True
                        break

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

    def check_merged_changes_for_issue(self, repo: str, ticket_id: int) -> bool:
        """Check if an issue has any merged PRs linked to it via cross-references.

        Note: The board query now uses CLOSED_EVENT for merged status detection.
        This helper uses CrossReferencedEvent with closing keywords, which can
        detect merged PRs that would close the issue even if the issue isn't
        closed yet.

        Args:
            repo: Repository in 'hostname/owner/repo' format
            ticket_id: Issue number

        Returns:
            True if any linked PR has been merged
        """
        prs = self._get_cross_referenced_prs(repo, ticket_id, filter_by_closing_keywords=True)
        has_merged = any(pr.get("merged", False) for pr in prs)
        logger.debug(f"Issue {repo}#{ticket_id} has_merged_changes={has_merged}")
        return has_merged
