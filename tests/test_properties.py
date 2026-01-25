"""Property-based tests using Hypothesis.

This module contains property-based tests that complement the existing example-based
tests by generating random inputs to find edge cases and verify invariants.
"""

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from src.cli import parse_issue_arg
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
