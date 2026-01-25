"""Property-based tests using Hypothesis.

This module contains property-based tests that complement the existing example-based
tests by generating random inputs to find edge cases and verify invariants.
"""

from unittest.mock import MagicMock

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

from src.cli import parse_issue_arg
from src.comment_processor import CommentProcessor
from src.logger import _extract_org_from_url
from src.workspace import WorkspaceManager


@pytest.mark.unit
class TestURLParsingProperties:
    """Property-based tests for URL parsing functions."""

    @given(st.text())
    @example("")  # Empty string regression case
    @example("https://github.com/owner/repo.git")  # Valid URL case
    def test_extract_repo_name_never_crashes(self, url: str):
        """Test that _extract_repo_name never crashes on arbitrary text input."""
        manager = WorkspaceManager("/tmp/test-workspace")
        # Should never raise an unexpected exception
        result = manager._extract_repo_name(url)
        # Should always return a string
        assert isinstance(result, str)

    @given(st.text())
    @example("")
    @example("https://github.com/owner/repo")
    def test_extract_repo_name_always_returns_string(self, url: str):
        """Test that _extract_repo_name always returns a string type."""
        manager = WorkspaceManager("/tmp/test-workspace")
        result = manager._extract_repo_name(url)
        assert isinstance(result, str)

    @given(st.text())
    @example("")
    @example("invalid")
    @example("owner")
    @example("repo#")
    @example("#123")
    def test_parse_issue_arg_raises_valueerror_for_invalid_formats(self, text: str):
        """Test that parse_issue_arg raises ValueError for invalid formats.

        Valid formats are:
        - owner/repo#42
        - hostname/owner/repo#42

        Everything else should raise ValueError.
        """
        # Skip inputs that match valid patterns
        import re

        valid_pattern = r"^(?:([^/]+)/)?([^/]+)/([^#]+)#(\d+)$"
        if re.match(valid_pattern, text):
            # This is a valid format, should not raise
            repo, issue_num = parse_issue_arg(text)
            assert isinstance(repo, str)
            assert isinstance(issue_num, int)
            assert issue_num >= 0
        else:
            # Invalid format should raise ValueError
            with pytest.raises(ValueError, match="Invalid issue format"):
                parse_issue_arg(text)

    @given(
        owner=st.text(
            min_size=1, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"))
        ).filter(lambda x: "/" not in x and "#" not in x),
        repo=st.text(
            min_size=1, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"))
        ).filter(lambda x: "/" not in x and "#" not in x),
        issue_num=st.integers(min_value=1, max_value=999999999),
    )
    @example(owner="owner", repo="repo", issue_num=42)
    def test_parse_issue_arg_valid_owner_repo_format(
        self, owner: str, repo: str, issue_num: int
    ):
        """Test that valid owner/repo#number formats are parsed correctly."""
        issue_arg = f"{owner}/{repo}#{issue_num}"
        result_repo, result_num = parse_issue_arg(issue_arg)

        assert result_repo == f"github.com/{owner}/{repo}"
        assert result_num == issue_num

    @given(
        hostname=st.text(
            min_size=1, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"))
        ).filter(lambda x: "/" not in x and "#" not in x),
        owner=st.text(
            min_size=1, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"))
        ).filter(lambda x: "/" not in x and "#" not in x),
        repo=st.text(
            min_size=1, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"))
        ).filter(lambda x: "/" not in x and "#" not in x),
        issue_num=st.integers(min_value=1, max_value=999999999),
    )
    @example(hostname="github.corp.com", owner="owner", repo="repo", issue_num=123)
    def test_parse_issue_arg_valid_hostname_format(
        self, hostname: str, owner: str, repo: str, issue_num: int
    ):
        """Test that valid hostname/owner/repo#number formats are parsed correctly."""
        issue_arg = f"{hostname}/{owner}/{repo}#{issue_num}"
        result_repo, result_num = parse_issue_arg(issue_arg)

        assert result_repo == f"{hostname}/{owner}/{repo}"
        assert result_num == issue_num

    @given(st.text())
    @example("")
    @example("https://github.com/orgs/myorg/projects/1")
    @example("https://github.com/orgs/test-org/projects/42")
    @example("invalid-url")
    def test_extract_org_from_url_returns_none_or_valid_org(self, url: str):
        """Test that _extract_org_from_url returns None or a valid org name."""
        result = _extract_org_from_url(url)

        # Should return None or a string
        assert result is None or isinstance(result, str)

        # If it returns a string, it should be non-empty
        if result is not None:
            assert len(result) > 0

    @given(
        org_name=st.text(
            min_size=1, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "Pd"))
        ).filter(lambda x: "/" not in x),
        project_num=st.integers(min_value=1, max_value=999999),
    )
    @example(org_name="myorg", project_num=1)
    @example(org_name="test-org", project_num=42)
    def test_extract_org_from_url_extracts_org_correctly(
        self, org_name: str, project_num: int
    ):
        """Test that _extract_org_from_url correctly extracts org from valid URLs."""
        url = f"https://github.com/orgs/{org_name}/projects/{project_num}"
        result = _extract_org_from_url(url)

        assert result == org_name


def _make_comment_processor() -> CommentProcessor:
    """Create a CommentProcessor with mocked dependencies for testing."""
    return CommentProcessor(
        ticket_client=MagicMock(),
        database=MagicMock(),
        runner=MagicMock(),
        workspace_dir="/tmp/test-workspace",
    )


@pytest.mark.unit
class TestDiffGenerationProperties:
    """Property-based tests for diff generation functions."""

    @given(content=st.text())
    @example(content="")
    @example(content="line1\nline2\nline3")
    def test_generate_diff_identity_property(self, content: str):
        """Test that _generate_diff returns empty string for identical content.

        The identity property states that diff(x, x) == "" for all x.
        """
        processor = _make_comment_processor()
        result = processor._generate_diff(content, content, "test")
        assert result == ""

    @given(
        before=st.text(min_size=1).filter(lambda x: x.strip()),
        after=st.text(min_size=1).filter(lambda x: x.strip()),
    )
    @example(before="old content", after="new content")
    @example(before="line1", after="line2")
    def test_generate_diff_different_content(self, before: str, after: str):
        """Test that _generate_diff returns non-empty for different content."""
        if before == after:
            # Skip if inputs happen to be equal
            return
        processor = _make_comment_processor()
        result = processor._generate_diff(before, after, "test")
        assert result != ""

    @given(
        content=st.text(min_size=1, max_size=200).filter(lambda x: "\n" not in x),
        width=st.integers(min_value=10, max_value=200),
    )
    @example(content="short", width=70)
    @example(content="a" * 100, width=70)
    def test_wrap_diff_line_respects_width_constraint(self, content: str, width: int):
        """Test that _wrap_diff_line respects width constraint.

        Each output line should be at most `width` characters.
        Note: _wrap_diff_line is designed for single-line input only.
        """
        processor = _make_comment_processor()
        # Test with a diff-like line (with prefix)
        line = f"+{content}"
        result = processor._wrap_diff_line(line, width)

        # Each resulting line should respect the width
        for output_line in result.split("\n"):
            assert len(output_line) <= width

    @given(
        content=st.text(min_size=1, max_size=100).filter(lambda x: "\n" not in x),
        prefix=st.sampled_from(["+", "-", " "]),
    )
    @example(content="some content", prefix="+")
    @example(content="deleted line", prefix="-")
    @example(content="context line", prefix=" ")
    def test_wrap_diff_line_preserves_prefix(self, content: str, prefix: str):
        """Test that _wrap_diff_line preserves diff prefix (+, -, space).

        All wrapped lines should start with the same prefix.
        Note: _wrap_diff_line is designed for single-line input only.
        """
        processor = _make_comment_processor()
        line = f"{prefix}{content}"
        result = processor._wrap_diff_line(line, width=70)

        # All non-empty output lines should start with the prefix
        for output_line in result.split("\n"):
            if output_line:  # Skip empty lines
                assert output_line.startswith(prefix), (
                    f"Expected line to start with '{prefix}', got: {output_line!r}"
                )

    @given(
        content=st.text(min_size=1, max_size=50).filter(lambda x: "\n" not in x),
        prefix=st.sampled_from(["+", "-", " ", ""]),
        width=st.integers(min_value=60, max_value=100),
    )
    @example(content="short line", prefix="+", width=70)
    @example(content="context", prefix=" ", width=70)
    def test_wrap_diff_line_idempotent_on_short_lines(
        self, content: str, prefix: str, width: int
    ):
        """Test that _wrap_diff_line is idempotent on already-short lines.

        If a line is already within the width limit, wrapping should not change it.
        Note: _wrap_diff_line is designed for single-line input only.
        """
        processor = _make_comment_processor()
        line = f"{prefix}{content}"

        # Only test lines that are already short enough
        if len(line) <= width:
            result = processor._wrap_diff_line(line, width)
            assert result == line, (
                f"Short line should be unchanged: {line!r} -> {result!r}"
            )
