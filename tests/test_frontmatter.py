"""Unit tests for the frontmatter module."""

import pytest

from src.frontmatter import parse_issue_frontmatter


@pytest.mark.unit
class TestParseIssueFrontmatter:
    """Tests for parse_issue_frontmatter function."""

    def test_valid_frontmatter_with_feature_branch(self):
        """Test parsing valid frontmatter with feature_branch setting."""
        body = """---
feature_branch: my-feature-branch
---

## Description
This is the issue description.
"""
        result = parse_issue_frontmatter(body)
        assert result == {"feature_branch": "my-feature-branch"}

    def test_valid_frontmatter_with_multiple_settings(self):
        """Test parsing frontmatter with multiple settings."""
        body = """---
feature_branch: develop
skip_research: true
priority: high
---

Some description here.
"""
        result = parse_issue_frontmatter(body)
        assert result == {
            "feature_branch": "develop",
            "skip_research": True,
            "priority": "high",
        }

    def test_no_frontmatter_returns_empty_dict(self):
        """Test that body without frontmatter returns empty dict."""
        body = """## Description
This is just a regular issue without frontmatter.
"""
        result = parse_issue_frontmatter(body)
        assert result == {}

    def test_none_body_returns_empty_dict(self):
        """Test that None body returns empty dict."""
        result = parse_issue_frontmatter(None)
        assert result == {}

    def test_empty_string_body_returns_empty_dict(self):
        """Test that empty string body returns empty dict."""
        result = parse_issue_frontmatter("")
        assert result == {}

    def test_malformed_yaml_returns_empty_dict(self, caplog):
        """Test that malformed YAML returns empty dict and logs warning."""
        body = """---
feature_branch: [unclosed bracket
invalid: yaml: here: too many colons
---

Description.
"""
        result = parse_issue_frontmatter(body)
        assert result == {}
        assert "Failed to parse issue frontmatter" in caplog.text

    def test_frontmatter_without_closing_delimiter_returns_empty_dict(self):
        """Test that frontmatter without closing --- returns empty dict."""
        body = """---
feature_branch: my-branch

## Description
This frontmatter is never closed.
"""
        result = parse_issue_frontmatter(body)
        assert result == {}

    def test_frontmatter_not_at_start_returns_empty_dict(self):
        """Test that frontmatter not at document start is ignored."""
        body = """Some content before.

---
feature_branch: my-branch
---

More content.
"""
        result = parse_issue_frontmatter(body)
        assert result == {}

    def test_empty_frontmatter_returns_empty_dict(self):
        """Test that empty frontmatter returns empty dict."""
        body = """---

---

Description here.
"""
        result = parse_issue_frontmatter(body)
        assert result == {}

    def test_frontmatter_with_only_whitespace_returns_empty_dict(self):
        """Test that frontmatter with only whitespace returns empty dict."""
        body = """---

---

Description here.
"""
        result = parse_issue_frontmatter(body)
        assert result == {}

    def test_frontmatter_with_branch_containing_slashes(self):
        """Test parsing branch name with path-like structure."""
        body = """---
feature_branch: user/feature/my-cool-feature
---

Description.
"""
        result = parse_issue_frontmatter(body)
        assert result == {"feature_branch": "user/feature/my-cool-feature"}

    def test_frontmatter_scalar_value_returns_empty_dict(self):
        """Test that scalar YAML (not a dict) returns empty dict."""
        body = """---
just a string value
---

Description.
"""
        result = parse_issue_frontmatter(body)
        assert result == {}

    def test_frontmatter_list_value_returns_empty_dict(self):
        """Test that list YAML (not a dict) returns empty dict."""
        body = """---
- item1
- item2
---

Description.
"""
        result = parse_issue_frontmatter(body)
        assert result == {}

    def test_frontmatter_with_quoted_values(self):
        """Test parsing frontmatter with quoted string values."""
        body = """---
feature_branch: "main"
description: 'A quoted string'
---

Description.
"""
        result = parse_issue_frontmatter(body)
        assert result == {
            "feature_branch": "main",
            "description": "A quoted string",
        }

    def test_frontmatter_preserves_case(self):
        """Test that key/value case is preserved."""
        body = """---
Feature_Branch: MyBranch
UPPERCASE: VALUE
---

Description.
"""
        result = parse_issue_frontmatter(body)
        assert result == {
            "Feature_Branch": "MyBranch",
            "UPPERCASE": "VALUE",
        }
