"""GitHub project column validation and auto-configuration."""

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.setup.checks import SetupError

if TYPE_CHECKING:
    from src.ticket_clients.github import GitHubTicketClient


# Required columns in order
REQUIRED_COLUMNS = [
    {"name": "Backlog", "color": "GRAY", "description": "Issues waiting to be prioritized"},
    {"name": "Research", "color": "PURPLE", "description": "Claude researches the problem"},
    {"name": "Plan", "color": "PURPLE", "description": "Claude creates implementation plan"},
    {"name": "Implement", "color": "ORANGE", "description": "Claude implements the plan"},
    {"name": "Validate", "color": "YELLOW", "description": "Human review and testing"},
    {"name": "Done", "color": "GREEN", "description": "Completed and merged"},
]

REQUIRED_COLUMN_NAMES = [col["name"] for col in REQUIRED_COLUMNS]


@dataclass
class ValidationResult:
    """Result of column validation."""

    project_url: str
    action: str  # "ok", "created", "reordered", "error"
    message: str


def _parse_project_url(url: str) -> tuple[str, str, int]:
    """Parse project URL to extract hostname, login, and project number."""
    # Try org pattern: https://{hostname}/orgs/{org}/projects/{number}
    org_pattern = r"https?://([^/]+)/orgs/([^/]+)/projects/(\d+)"
    org_match = re.match(org_pattern, url)
    if org_match:
        return org_match.group(1), org_match.group(2), int(org_match.group(3))

    # Try user pattern: https://{hostname}/users/{user}/projects/{number}
    user_pattern = r"https?://([^/]+)/users/([^/]+)/projects/(\d+)"
    user_match = re.match(user_pattern, url)
    if user_match:
        return user_match.group(1), user_match.group(2), int(user_match.group(3))

    raise ValueError(
        f"Invalid project URL: {url}. "
        "Expected format: https://HOSTNAME/orgs/ORG/projects/NUMBER "
        "or https://HOSTNAME/users/USER/projects/NUMBER"
    )


def validate_project_columns(
    client: "GitHubTicketClient",
    project_url: str,
) -> ValidationResult:
    """Validate and optionally fix project board columns.

    Logic:
    1. If only Backlog exists -> create remaining columns
    2. If all required columns exist in correct order -> proceed
    3. If all required columns exist in wrong order -> reorder
    4. Otherwise -> error with instructions

    Args:
        client: GitHubTicketClient instance
        project_url: URL of the GitHub project

    Returns:
        ValidationResult with action taken and message

    Raises:
        SetupError: If columns cannot be auto-fixed and manual intervention needed
    """
    hostname, _, _ = _parse_project_url(project_url)
    metadata = client.get_board_metadata(project_url)

    status_options = metadata.get("status_options", {})
    status_field_id = metadata.get("status_field_id")

    if not status_field_id:
        raise SetupError(f"Could not find Status field in project: {project_url}")

    existing_names = list(status_options.keys())
    existing_ids = status_options  # Maps name -> id

    # Case 1: Only Backlog exists - create all other columns
    if existing_names == ["Backlog"]:
        new_options = [
            {"name": col["name"], "color": col["color"], "description": col["description"]}
            for col in REQUIRED_COLUMNS
        ]

        client.update_status_field_options(status_field_id, new_options, hostname)
        created = [c["name"] for c in REQUIRED_COLUMNS if c["name"] != "Backlog"]
        return ValidationResult(
            project_url=project_url,
            action="created",
            message=f"Created columns: {', '.join(created)}",
        )

    # Case 2: All required columns exist
    existing_set = set(existing_names)
    required_set = set(REQUIRED_COLUMN_NAMES)

    if existing_set == required_set:
        # Check order
        if existing_names == REQUIRED_COLUMN_NAMES:
            # Perfect - all columns in correct order
            return ValidationResult(
                project_url=project_url,
                action="ok",
                message="All required columns present and correctly ordered",
            )
        else:
            # Need to reorder
            new_options = []
            for col in REQUIRED_COLUMNS:
                new_options.append(
                    {
                        "id": existing_ids[col["name"]],
                        "name": col["name"],
                        "color": col["color"],
                        "description": col["description"],
                    }
                )

            client.update_status_field_options(status_field_id, new_options, hostname)
            return ValidationResult(
                project_url=project_url,
                action="reordered",
                message="Columns reordered to: " + " -> ".join(REQUIRED_COLUMN_NAMES),
            )

    # Case 3: Any other configuration - error out
    extra = existing_set - required_set
    missing = required_set - existing_set

    error_lines = [
        "Project board configuration not compatible",
        "",
        f"  Project: {project_url}",
        "",
        f"  Current columns: {', '.join(existing_names)}",
    ]

    if extra:
        error_lines.append(f"  Extra columns: {', '.join(sorted(extra))}")
    if missing:
        error_lines.append(f"  Missing columns: {', '.join(sorted(missing))}")

    error_lines.extend(
        [
            "",
            "  To use Kiln, the project board must have ONLY these columns in this order:",
            "    1. Backlog",
            "    2. Research",
            "    3. Plan",
            "    4. Implement",
            "    5. Validate",
            "    6. Done",
            "",
            "  Please choose one of the following:",
            "",
            "  Option 1: Manually create the columns",
            f"    - Go to: {project_url}",
            "    - Delete all columns except Backlog",
            "    - Add the remaining columns in the order shown above",
            "",
            "  Option 2: Let Kiln create them automatically",
            f"    - Go to: {project_url}",
            "    - Delete all columns except Backlog",
            "    - Run `kiln` again and Kiln will create the required columns",
            "",
            "After fixing, run `kiln` again.",
        ]
    )

    raise SetupError("\n".join(error_lines))
