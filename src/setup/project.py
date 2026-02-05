"""GitHub project column validation and auto-configuration."""

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.setup.checks import SetupError

if TYPE_CHECKING:
    from src.ticket_clients import GitHubClient


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

# GitHub's default Status field columns for new Project V2s
GITHUB_DEFAULT_COLUMNS = frozenset({"Backlog", "Ready", "In progress", "In review", "Done"})


@dataclass
class ValidationResult:
    """Result of column validation."""

    project_url: str
    action: str  # "ok", "created", "reordered", "error"
    message: str


def _migrate_items_to_backlog(
    client: "GitHubClient",
    project_url: str,
    deprecated_statuses: set[str],
    hostname: str,
) -> int:
    """Migrate items from deprecated statuses to Backlog.

    Args:
        client: GitHubClient instance
        project_url: URL of the GitHub project
        deprecated_statuses: Set of status names to migrate from
        hostname: GitHub hostname for API calls

    Returns:
        Number of items migrated
    """
    items = client.get_board_items(project_url)
    migrated_count = 0

    for item in items:
        if item.status in deprecated_statuses:
            client.update_item_status(item.item_id, "Backlog", hostname=hostname)
            migrated_count += 1

    return migrated_count


def _format_column_checklist(
    existing_names: list[str],
    project_url: str,
    project_index: int = 1,
    total_projects: int = 1,
) -> str:
    """Format a checklist showing which columns are correct and which need fixing.

    Args:
        existing_names: List of existing column names in current order
        project_url: URL of the GitHub project
        project_index: Current project number (1-indexed)
        total_projects: Total number of projects being validated

    Returns:
        Formatted checklist string
    """
    existing_set = set(existing_names)

    # Extract org/project# from URL for display
    # URL format: https://hostname/orgs/ORG/projects/NUMBER
    try:
        _, login, project_num = _parse_project_url(project_url)
        project_label = f"{login}/projects/{project_num}"
    except ValueError:
        project_label = project_url

    lines = [
        "",
        "GitHub Enterprise 3.14 API doesn't support fixing the project board for you.",
        "You need to manually configure the columns in the correct order and capitalization.",
        "",
        "#" * 50,
        f"##### Project {project_index} of {total_projects}: {project_label} #####",
        "#" * 50,
        "",
        "Click here to go to your project:",
        f"  {project_url}",
        "",
        "Required columns (in order):",
    ]

    # Show checklist with status for each required column
    for i, col_name in enumerate(REQUIRED_COLUMN_NAMES, 1):
        if col_name in existing_set:
            # Check if it's in the right position
            try:
                actual_pos = existing_names.index(col_name) + 1
                if actual_pos == i:
                    lines.append(f"  [{chr(10003)}] {i}. {col_name}")
                else:
                    lines.append(f"  [!] {i}. {col_name} (currently at position {actual_pos})")
            except ValueError:
                lines.append(f"  [ ] {i}. {col_name} (missing)")
        else:
            lines.append(f"  [ ] {i}. {col_name} (missing)")

    # Show extra columns that need to be removed
    extra_cols = existing_set - set(REQUIRED_COLUMN_NAMES)
    if extra_cols:
        lines.append("")
        lines.append("Extra columns to DELETE:")
        for col in sorted(extra_cols):
            lines.append(f"  [X] {col}")

    lines.extend([
        "",
        "Steps to fix:",
        "  1. Go to your project settings",
        "  2. Delete all columns except 'Backlog'",
        "  3. Create columns in THIS EXACT ORDER:",
        "     - Backlog",
        "     - Research",
        "     - Plan",
        "     - Implement",
        "     - Validate",
        "     - Done",
        "",
        "After fixing, run `kiln` again.",
        "",
    ])

    return "\n".join(lines)


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
    client: "GitHubClient",
    project_url: str,
    project_index: int = 1,
    total_projects: int = 1,
) -> ValidationResult:
    """Validate and optionally fix project board columns.

    Logic:
    1. If only Backlog exists -> create remaining columns
    2. If all required columns exist in correct order -> proceed
    3. If all required columns exist in wrong order -> reorder
    4. Otherwise -> error with instructions

    Args:
        client: GitHubClient instance
        project_url: URL of the GitHub project
        project_index: Current project number (1-indexed) for error messages
        total_projects: Total number of projects being validated

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
        if not client.supports_column_management:
            raise SetupError(_format_column_checklist(
                existing_names, project_url, project_index, total_projects
            ))

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

    existing_set = set(existing_names)

    # Case 1.5: GitHub default columns - replace with Kiln columns
    if existing_set == GITHUB_DEFAULT_COLUMNS:
        if not client.supports_column_management:
            raise SetupError(_format_column_checklist(
                existing_names, project_url, project_index, total_projects
            ))

        # Migrate items from deprecated statuses to Backlog before replacing columns
        deprecated_statuses = {"Ready", "In progress", "In review"}
        migrated_count = _migrate_items_to_backlog(
            client, project_url, deprecated_statuses, hostname
        )

        new_options = [
            {"name": col["name"], "color": col["color"], "description": col["description"]}
            for col in REQUIRED_COLUMNS
        ]
        client.update_status_field_options(status_field_id, new_options, hostname)

        message = "Replaced GitHub default columns with Kiln workflow columns"
        if migrated_count > 0:
            message += f" ({migrated_count} item(s) moved to Backlog)"

        return ValidationResult(
            project_url=project_url,
            action="replaced",
            message=message,
        )

    # Case 2: All required columns exist
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
            if not client.supports_column_management:
                raise SetupError(_format_column_checklist(
                existing_names, project_url, project_index, total_projects
            ))

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
