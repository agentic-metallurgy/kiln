"""Frontmatter parsing for issue descriptions."""

import re
from typing import Any

import yaml

from src.logger import get_logger

logger = get_logger(__name__)

# Pattern to match YAML frontmatter (content between first two ---)
FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)


def parse_issue_frontmatter(body: str | None) -> dict[str, Any]:
    """Parse YAML frontmatter from issue body.

    Frontmatter is the YAML content between the first two `---` delimiters
    at the start of the issue body. For example:

        ---
        feature_branch: my-feature
        ---

        Issue description here...

    Args:
        body: Issue body text, may be None

    Returns:
        Dict of frontmatter settings, empty if none found or parsing fails
    """
    if not body:
        return {}

    match = FRONTMATTER_PATTERN.match(body)
    if not match:
        return {}

    frontmatter_text = match.group(1)
    try:
        result = yaml.safe_load(frontmatter_text)
        if isinstance(result, dict):
            return result
        return {}
    except yaml.YAMLError as e:
        logger.warning(f"Failed to parse issue frontmatter: {e}")
        return {}
