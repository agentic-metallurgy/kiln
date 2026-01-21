"""GitHub Enterprise Server 3.18 implementation of the TicketClient protocol.

GHES 3.18 sits between 3.14 (limited API) and 3.19 (full API parity):
- Sub-issues API IS available (introduced in 3.18)
- closedByPullRequestsReferences is NOT available (uses CrossReferencedEvent from 3.14)
- Project V2 timeline events are NOT available (uses field creator from 3.14)

This client extends GitHubEnterprise314Client to inherit the workarounds for
linked PR detection (CrossReferencedEvent) and status actor detection (field creator),
while overriding the sub-issues methods to use the actual GraphQL API.

API Feature Comparison:
| Feature                          | GHES 3.14 | GHES 3.18 | GHES 3.19 |
|----------------------------------|-----------|-----------|-----------|
| closedByPullRequestsReferences   | ❌        | ❌        | ✅        |
| Sub-issues API                   | ❌        | ✅        | ✅        |
| ADDED_TO_PROJECT_V2_EVENT        | ❌        | ❌        | ✅        |
| Project V2 (50K items)           | ✅        | ✅        | ✅        |
"""

from src.logger import get_logger
from src.ticket_clients.github_enterprise_3_14 import GitHubEnterprise314Client

logger = get_logger(__name__)


class GitHubEnterprise318Client(GitHubEnterprise314Client):
    """GitHub Enterprise Server 3.18 implementation of TicketClient protocol.

    GHES 3.18 introduces sub-issues API support while still requiring
    the same workarounds as 3.14 for:
    - Linked PRs (CrossReferencedEvent instead of closedByPullRequestsReferences)
    - Status actor detection (field creator instead of timeline events)
    - Merged PR detection (CLOSED_EVENT instead of closedByPullRequestsReferences)
    """

    @property
    def supports_sub_issues(self) -> bool:
        """GHES 3.18 supports sub-issues API."""
        return True

    @property
    def client_description(self) -> str:
        """Human-readable description of this client."""
        return "GitHub Enterprise Server 3.18"

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
