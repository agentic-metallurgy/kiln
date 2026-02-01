"""Property-based tests using Hypothesis.

This module contains property-based tests that verify invariants and discover
edge cases across URL parsing, config parsing, diff generation, comment
filtering, and label operations.
"""

import tempfile

import pytest
from hypothesis import assume, example, given
from hypothesis import strategies as st

from src.cli import parse_issue_arg
from src.logger import _extract_org_from_url
from src.workspace import WorkspaceManager

# =============================================================================
# Custom Strategies
# =============================================================================

# Strategy for valid organization names (alphanumeric, hyphens)
org_name_strategy = st.from_regex(r"[a-zA-Z][a-zA-Z0-9\-]{0,38}", fullmatch=True)

# Strategy for valid repo/owner names
repo_name_strategy = st.from_regex(r"[a-zA-Z][a-zA-Z0-9\-_\.]{0,38}", fullmatch=True)

# Strategy for valid hostnames
hostname_strategy = st.from_regex(r"[a-zA-Z][a-zA-Z0-9\-\.]{0,62}", fullmatch=True)

# Strategy for positive issue numbers
issue_number_strategy = st.integers(min_value=1, max_value=999999999)

# Strategy for valid project numbers
project_number_strategy = st.integers(min_value=1, max_value=9999)


# =============================================================================
# URL Parsing Property Tests
# =============================================================================


@pytest.mark.unit
@pytest.mark.hypothesis
class TestExtractOrgFromUrlProperties:
    """Property-based tests for _extract_org_from_url."""

    @given(org_name=org_name_strategy, project_num=project_number_strategy)
    @example(org_name="myorg", project_num=1)
    @example(org_name="my-org-123", project_num=42)
    @example(org_name="A", project_num=9999)
    def test_valid_org_url_returns_org_name(self, org_name: str, project_num: int):
        """Property: Valid project URLs always extract the correct org name."""
        url = f"https://github.com/orgs/{org_name}/projects/{project_num}"
        result = _extract_org_from_url(url)
        assert result == org_name

    @given(org_name=org_name_strategy, project_num=project_number_strategy)
    def test_org_extraction_with_trailing_slash(self, org_name: str, project_num: int):
        """Property: Trailing content after projects/ doesn't affect extraction."""
        url = f"https://github.com/orgs/{org_name}/projects/{project_num}/views/1"
        result = _extract_org_from_url(url)
        assert result == org_name

    @given(org_name=org_name_strategy, project_num=project_number_strategy)
    def test_enterprise_urls_extract_org(self, org_name: str, project_num: int):
        """Property: Enterprise GitHub URLs with /orgs/ pattern work."""
        url = f"https://github.example.com/orgs/{org_name}/projects/{project_num}"
        result = _extract_org_from_url(url)
        assert result == org_name

    @given(text=st.text(max_size=200))
    @example(text="")
    @example(text="not-a-url")
    @example(text="/orgs/")
    @example(text="https://github.com/user/repo")
    def test_invalid_urls_return_none(self, text: str):
        """Property: URLs without /orgs/.../projects/ pattern return None."""
        # Skip if it accidentally matches the valid pattern
        assume("/orgs/" not in text or "/projects/" not in text)
        result = _extract_org_from_url(text)
        assert result is None


@pytest.mark.unit
@pytest.mark.hypothesis
class TestParseIssueArgProperties:
    """Property-based tests for parse_issue_arg."""

    @given(
        owner=repo_name_strategy,
        repo=repo_name_strategy,
        issue_num=issue_number_strategy,
    )
    @example(owner="owner", repo="repo", issue_num=42)
    @example(owner="my-org", repo="my-repo", issue_num=1)
    @example(owner="A", repo="B", issue_num=999999999)
    def test_owner_repo_format_roundtrip(
        self, owner: str, repo: str, issue_num: int
    ):
        """Property: owner/repo#N format parses correctly with github.com default."""
        issue_arg = f"{owner}/{repo}#{issue_num}"
        result_repo, result_num = parse_issue_arg(issue_arg)

        assert result_num == issue_num
        assert result_repo == f"github.com/{owner}/{repo}"

    @given(
        hostname=hostname_strategy,
        owner=repo_name_strategy,
        repo=repo_name_strategy,
        issue_num=issue_number_strategy,
    )
    @example(hostname="github.corp.com", owner="org", repo="repo", issue_num=123)
    @example(hostname="git.example.org", owner="team", repo="project", issue_num=1)
    def test_hostname_format_roundtrip(
        self, hostname: str, owner: str, repo: str, issue_num: int
    ):
        """Property: hostname/owner/repo#N format preserves all components."""
        issue_arg = f"{hostname}/{owner}/{repo}#{issue_num}"
        result_repo, result_num = parse_issue_arg(issue_arg)

        assert result_num == issue_num
        assert result_repo == f"{hostname}/{owner}/{repo}"

    @given(
        owner=repo_name_strategy,
        repo=repo_name_strategy,
        issue_num=issue_number_strategy,
    )
    def test_issue_number_always_positive(
        self, owner: str, repo: str, issue_num: int
    ):
        """Property: Parsed issue numbers are always positive integers."""
        issue_arg = f"{owner}/{repo}#{issue_num}"
        _, result_num = parse_issue_arg(issue_arg)
        assert result_num > 0

    @given(text=st.text(max_size=100))
    @example(text="invalid")
    @example(text="owner/repo")
    @example(text="repo#42")
    @example(text="")
    def test_invalid_format_raises_valueerror(self, text: str):
        """Property: Invalid formats always raise ValueError."""
        # Skip if it accidentally matches a valid pattern
        assume(not (
            "/" in text
            and "#" in text
            and text.split("#")[-1].isdigit()
            and len(text.split("/")) >= 2
        ))
        with pytest.raises(ValueError):
            parse_issue_arg(text)


@pytest.mark.unit
@pytest.mark.hypothesis
class TestExtractRepoNameProperties:
    """Property-based tests for WorkspaceManager._extract_repo_name."""

    @given(org=repo_name_strategy, repo=repo_name_strategy)
    @example(org="org", repo="repo")
    @example(org="my-org", repo="my-repo")
    @example(org="A", repo="B")
    def test_https_url_extracts_repo_name(self, org: str, repo: str):
        """Property: HTTPS URLs extract the correct repo name."""
        with tempfile.TemporaryDirectory() as tmp_path:
            manager = WorkspaceManager(tmp_path)
            url = f"https://github.com/{org}/{repo}"
            result = manager._extract_repo_name(url)
            assert result == repo

    @given(org=repo_name_strategy, repo=repo_name_strategy)
    @example(org="org", repo="repo")
    def test_https_url_with_git_suffix(self, org: str, repo: str):
        """Property: .git suffix is stripped from repo names."""
        with tempfile.TemporaryDirectory() as tmp_path:
            manager = WorkspaceManager(tmp_path)
            url = f"https://github.com/{org}/{repo}.git"
            result = manager._extract_repo_name(url)
            assert result == repo
            assert not result.endswith(".git")

    @given(org=repo_name_strategy, repo=repo_name_strategy)
    @example(org="org", repo="repo")
    def test_trailing_slash_handling(self, org: str, repo: str):
        """Property: Trailing slashes don't affect repo name extraction."""
        with tempfile.TemporaryDirectory() as tmp_path:
            manager = WorkspaceManager(tmp_path)
            url_without_slash = f"https://github.com/{org}/{repo}"
            url_with_slash = f"https://github.com/{org}/{repo}/"

            result_without = manager._extract_repo_name(url_without_slash)
            result_with = manager._extract_repo_name(url_with_slash)

            assert result_without == result_with == repo

    @given(org=repo_name_strategy, repo=repo_name_strategy)
    @example(org="org", repo="repo")
    def test_ssh_url_extracts_repo_name(self, org: str, repo: str):
        """Property: SSH URLs extract the correct repo name."""
        with tempfile.TemporaryDirectory() as tmp_path:
            manager = WorkspaceManager(tmp_path)
            url = f"git@github.com:{org}/{repo}.git"
            result = manager._extract_repo_name(url)
            assert result == repo

    @given(org=repo_name_strategy, repo=repo_name_strategy)
    def test_result_never_empty(self, org: str, repo: str):
        """Property: Extracted repo name is never empty."""
        with tempfile.TemporaryDirectory() as tmp_path:
            manager = WorkspaceManager(tmp_path)
            url = f"https://github.com/{org}/{repo}"
            result = manager._extract_repo_name(url)
            assert len(result) > 0

    @given(
        hostname=hostname_strategy,
        org=repo_name_strategy,
        repo=repo_name_strategy,
    )
    @example(hostname="github.corp.com", org="enterprise", repo="app")
    def test_enterprise_https_url(self, hostname: str, org: str, repo: str):
        """Property: Enterprise HTTPS URLs extract the correct repo name."""
        with tempfile.TemporaryDirectory() as tmp_path:
            manager = WorkspaceManager(tmp_path)
            url = f"https://{hostname}/{org}/{repo}.git"
            result = manager._extract_repo_name(url)
            assert result == repo
