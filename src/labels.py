"""Label definitions for kiln workflows.

This module centralizes all label definitions used by the daemon to track
workflow state and provide visual indicators in the GitHub UI.

Labels serve as the source of truth for workflow state:
- Running labels indicate a workflow is currently executing
- Complete labels indicate a workflow has finished successfully
- Special labels control workflow behavior (e.g., yolo, reset)
"""

from typing import TypedDict


class LabelConfig(TypedDict):
    """Configuration for a GitHub label."""

    description: str
    color: str


# Label name constants for type-safe references throughout the codebase
class Labels:
    """Constants for all kiln label names."""

    # Workflow running labels (indicate in-progress state)
    PREPARING = "preparing"
    RESEARCHING = "researching"
    PLANNING = "planning"
    IMPLEMENTING = "implementing"
    REVIEWING = "reviewing"
    EDITING = "editing"
    TESTING_ACCESS = "testing_access"

    # Workflow complete labels
    RESEARCH_READY = "research_ready"
    PLAN_READY = "plan_ready"

    # State labels
    CLEANED_UP = "cleaned_up"

    # Control labels
    YOLO = "yolo"
    YOLO_FAILED = "yolo_failed"
    RESET = "reset"

    # Failure labels
    IMPLEMENTATION_FAILED = "implementation_failed"


# Required labels with descriptions and colors for automatic creation
# These labels are created in repositories when the daemon initializes
REQUIRED_LABELS: dict[str, LabelConfig] = {
    Labels.PREPARING: {
        "description": "Prepare workflow in progress",
        "color": "FFA500",  # Orange
    },
    Labels.RESEARCHING: {
        "description": "Research workflow in progress",
        "color": "FFA500",  # Orange
    },
    Labels.RESEARCH_READY: {
        "description": "Research complete",
        "color": "2ECC71",  # Green
    },
    Labels.PLANNING: {
        "description": "Plan workflow in progress",
        "color": "FFA500",  # Orange
    },
    Labels.PLAN_READY: {
        "description": "Plan complete",
        "color": "2ECC71",  # Green
    },
    Labels.IMPLEMENTING: {
        "description": "Implement workflow in progress",
        "color": "FFA500",  # Orange
    },
    Labels.REVIEWING: {
        "description": "PR under internal review",
        "color": "1D76DB",  # Blue
    },
    Labels.CLEANED_UP: {
        "description": "Worktree has been cleaned up",
        "color": "BFDADC",  # Light gray
    },
    Labels.EDITING: {
        "description": "Processing user comment",
        "color": "1D76DB",  # Blue
    },
    Labels.YOLO: {
        "description": "Auto-progress through Research → Plan → Implement",
        "color": "A855F7",  # Bright purple
    },
    Labels.YOLO_FAILED: {
        "description": "YOLO auto-progression failed",
        "color": "DC2626",  # Red
    },
    Labels.RESET: {
        "description": "Clear kiln content and move issue to Backlog",
        "color": "3B82F6",  # Blue
    },
    Labels.IMPLEMENTATION_FAILED: {
        "description": "Implementation workflow failed after retries",
        "color": "DC2626",  # Red
    },
}

