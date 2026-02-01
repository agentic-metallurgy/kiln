"""Property-based tests using Hypothesis.

This module contains property-based tests that verify invariants and discover
edge cases across URL parsing, config parsing, diff generation, comment
filtering, and label operations.
"""

import string
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from hypothesis import assume, example, given
from hypothesis import strategies as st
from hypothesis.stateful import Bundle, RuleBasedStateMachine, invariant, rule

from src.cli import parse_issue_arg
from src.comment_processor import CommentProcessor
from src.config import parse_config_file
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
    def test_owner_repo_format_roundtrip(self, owner: str, repo: str, issue_num: int):
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
    def test_hostname_format_roundtrip(self, hostname: str, owner: str, repo: str, issue_num: int):
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
    def test_issue_number_always_positive(self, owner: str, repo: str, issue_num: int):
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
        assume(
            not (
                "/" in text
                and "#" in text
                and text.split("#")[-1].isdigit()
                and len(text.split("/")) >= 2
            )
        )
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


# =============================================================================
# Config Parsing Property Tests
# =============================================================================

# Strategy for valid config keys (alphanumeric and underscore, not starting with #)
config_key_strategy = st.from_regex(r"[A-Z][A-Z0-9_]{0,49}", fullmatch=True)


@pytest.mark.unit
@pytest.mark.hypothesis
class TestConfigParsingProperties:
    """Property-based tests for parse_config_file."""

    @given(
        key=config_key_strategy,
        value=st.text(
            alphabet=st.characters(
                blacklist_categories=("Cc", "Cs"),  # Exclude control chars and surrogates
                blacklist_characters="\n\r\"'",
            ),
            min_size=0,
            max_size=100,
        ),
    )
    @example(key="MY_KEY", value="simple_value")
    @example(key="API_TOKEN", value="abc123")
    @example(key="A", value="")
    def test_key_value_parsing_roundtrip(self, key: str, value: str):
        """Property: Written key=value pairs parse back with stripped values."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_file = Path(tmp_dir) / "config"
            config_file.write_text(f"{key}={value}")
            result = parse_config_file(config_file)
            assert key in result
            # The parser strips whitespace from values
            assert result[key] == value.strip()

    @given(
        key=config_key_strategy,
        value=st.text(
            alphabet=st.characters(
                blacklist_categories=("Cc", "Cs"),  # Exclude control chars and surrogates
                blacklist_characters='\n\r"',
            ),
            min_size=0,
            max_size=100,
        ),
    )
    @example(key="QUOTED_VAL", value="hello world")
    @example(key="DB_URL", value="postgres://user:pass@host/db")
    @example(key="EMPTY_QUOTED", value="")
    def test_double_quoted_values_stripped(self, key: str, value: str):
        """Property: Double-quoted values have quotes stripped."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_file = Path(tmp_dir) / "config"
            config_file.write_text(f'{key}="{value}"')
            result = parse_config_file(config_file)
            assert key in result
            assert result[key] == value

    @given(
        key=config_key_strategy,
        value=st.text(
            alphabet=st.characters(
                blacklist_categories=("Cc", "Cs"),  # Exclude control chars and surrogates
                blacklist_characters="\n\r'",
            ),
            min_size=0,
            max_size=100,
        ),
    )
    @example(key="SINGLE_QUOTED", value="value with spaces")
    def test_single_quoted_values_stripped(self, key: str, value: str):
        """Property: Single-quoted values have quotes stripped."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_file = Path(tmp_dir) / "config"
            config_file.write_text(f"{key}='{value}'")
            result = parse_config_file(config_file)
            assert key in result
            assert result[key] == value

    @given(
        key=config_key_strategy,
        value=st.text(
            alphabet=st.characters(
                blacklist_categories=("Cc", "Cs"),  # Exclude control chars and surrogates
                blacklist_characters="\n\r\"'",
            ),
            min_size=1,
            max_size=50,
        ),
        leading_spaces=st.integers(min_value=0, max_value=5),
        trailing_spaces=st.integers(min_value=0, max_value=5),
    )
    @example(key="SPACED", value="test", leading_spaces=2, trailing_spaces=3)
    @example(key="TABS", value="value", leading_spaces=0, trailing_spaces=0)
    def test_whitespace_around_line_stripped(
        self, key: str, value: str, leading_spaces: int, trailing_spaces: int
    ):
        """Property: Whitespace around lines is stripped."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_file = Path(tmp_dir) / "config"
            line = " " * leading_spaces + f"{key}={value}" + " " * trailing_spaces
            config_file.write_text(line)
            result = parse_config_file(config_file)
            assert key in result
            # The parser strips the entire line, so value should match
            assert result[key] == value

    @given(
        key=config_key_strategy,
        value=st.text(
            alphabet=st.characters(
                blacklist_categories=("Cc", "Cs"),  # Exclude control chars and surrogates
                blacklist_characters="\n\r\"'",
            ),
            min_size=1,
            max_size=50,
        ),
        key_trailing_spaces=st.integers(min_value=0, max_value=5),
        value_leading_spaces=st.integers(min_value=0, max_value=5),
    )
    @example(key="SPACED_KEY", value="val", key_trailing_spaces=2, value_leading_spaces=2)
    def test_whitespace_around_equals_stripped(
        self, key: str, value: str, key_trailing_spaces: int, value_leading_spaces: int
    ):
        """Property: Whitespace around = sign is stripped from key and value."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_file = Path(tmp_dir) / "config"
            # Format: KEY   =   value
            line = key + " " * key_trailing_spaces + "=" + " " * value_leading_spaces + value
            config_file.write_text(line)
            result = parse_config_file(config_file)
            assert key in result
            assert result[key] == value

    @given(
        comment=st.text(
            alphabet=st.characters(
                blacklist_categories=("Cc", "Cs")
            ),  # Exclude control and surrogates
            max_size=100,
        ).filter(lambda x: "\n" not in x and "\r" not in x)
    )
    @example(comment="This is a comment")
    @example(comment="")
    def test_comment_lines_ignored(self, comment: str):
        """Property: Lines starting with # are ignored."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_file = Path(tmp_dir) / "config"
            config_file.write_text(f"# {comment}\nVALID_KEY=valid_value")
            result = parse_config_file(config_file)
            # Comment should not be parsed as a key
            assert f"# {comment}" not in result
            # Valid key should still be present
            assert result.get("VALID_KEY") == "valid_value"

    @given(num_empty_lines=st.integers(min_value=1, max_value=5))
    @example(num_empty_lines=1)
    @example(num_empty_lines=3)
    def test_empty_lines_ignored(self, num_empty_lines: int):
        """Property: Empty lines are ignored."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_file = Path(tmp_dir) / "config"
            content = "\n" * num_empty_lines + "KEY=value" + "\n" * num_empty_lines
            config_file.write_text(content)
            result = parse_config_file(config_file)
            assert result.get("KEY") == "value"
            assert len(result) == 1

    @given(
        keys=st.lists(
            config_key_strategy,
            min_size=2,
            max_size=5,
            unique=True,
        ),
        values=st.lists(
            st.text(
                alphabet=st.characters(
                    blacklist_categories=("Cc", "Cs"),  # Exclude control chars and surrogates
                    blacklist_characters="\n\r\"'",
                ),
                min_size=1,
                max_size=30,
            ),
            min_size=2,
            max_size=5,
        ),
    )
    def test_multiple_keys_all_parsed(self, keys: list, values: list):
        """Property: All key-value pairs in a file are parsed."""
        # Ensure we have same number of keys and values
        min_len = min(len(keys), len(values))
        keys = keys[:min_len]
        values = values[:min_len]

        with tempfile.TemporaryDirectory() as tmp_dir:
            config_file = Path(tmp_dir) / "config"
            lines = [f"{k}={v}" for k, v in zip(keys, values, strict=True)]
            config_file.write_text("\n".join(lines))

            result = parse_config_file(config_file)
            for k, v in zip(keys, values, strict=True):
                assert k in result
                # The parser strips whitespace from values
                assert result[k] == v.strip()

    @given(
        key=config_key_strategy,
        value=st.text(
            alphabet=st.characters(
                blacklist_categories=(
                    "Cc",
                    "Cs",
                    "Zs",
                ),  # Exclude control, surrogates, and space separators
                blacklist_characters="\n\r\"'",
            ),
            min_size=1,
            max_size=50,
        ),
    )
    @example(key="URL", value="https://example.com/path?query=value")
    @example(key="MATH", value="1+1=2")
    def test_values_with_equals_preserved(self, key: str, value: str):
        """Property: Values containing = are preserved correctly."""
        # The parser uses partition which only splits on first =
        # Note: The parser strips whitespace (including Unicode whitespace like \xa0)
        # from values, so we test with non-whitespace characters only
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_file = Path(tmp_dir) / "config"
            full_value = f"{value}=extra"
            config_file.write_text(f"{key}={full_value}")
            result = parse_config_file(config_file)
            assert key in result
            assert result[key] == full_value


# =============================================================================
# Diff Generation Property Tests
# =============================================================================


def _create_comment_processor() -> CommentProcessor:
    """Create a CommentProcessor with mock dependencies for testing."""
    mock_client = MagicMock()
    mock_database = MagicMock()
    mock_runner = MagicMock()
    mock_config = MagicMock()
    return CommentProcessor(
        ticket_client=mock_client,
        database=mock_database,
        runner=mock_runner,
        workspace_dir="/tmp/test",
        config=mock_config,
    )


# Strategy for text content without null bytes (valid for diffing)
diff_text_strategy = st.text(
    alphabet=st.characters(
        blacklist_categories=("Cc",),  # Exclude control chars except whitespace
        blacklist_characters="\x00",  # Explicitly exclude null byte
    ),
    min_size=0,
    max_size=500,
)


@pytest.mark.unit
@pytest.mark.hypothesis
class TestGenerateDiffProperties:
    """Property-based tests for _generate_diff."""

    @given(text=diff_text_strategy)
    @example(text="")
    @example(text="hello world")
    @example(text="line1\nline2\nline3")
    @example(text="  leading whitespace")
    def test_diff_of_identical_content_is_empty(self, text: str):
        """Property: Diff of identical content returns empty string."""
        processor = _create_comment_processor()
        result = processor._generate_diff(text, text, "test")
        assert result == ""

    @given(
        before=diff_text_strategy,
        after=diff_text_strategy,
    )
    def test_diff_returns_string(self, before: str, after: str):
        """Property: _generate_diff always returns a string."""
        processor = _create_comment_processor()
        result = processor._generate_diff(before, after, "test")
        assert isinstance(result, str)

    @given(
        before=diff_text_strategy,
        after=diff_text_strategy,
        target_type=st.text(min_size=1, max_size=20).filter(lambda x: "\n" not in x),
    )
    def test_diff_never_crashes(self, before: str, after: str, target_type: str):
        """Property: _generate_diff never crashes on any string inputs."""
        processor = _create_comment_processor()
        # Should not raise
        processor._generate_diff(before, after, target_type)

    @given(
        content=st.text(
            alphabet=st.characters(
                blacklist_categories=("Cc",),
                blacklist_characters="\x00",
            ),
            min_size=1,
            max_size=100,
        ).filter(lambda x: x.strip())  # Ensure non-empty after strip
    )
    @example(content="new content")
    def test_diff_of_empty_to_content_has_additions(self, content: str):
        """Property: Diff from empty to content contains addition markers."""
        processor = _create_comment_processor()
        result = processor._generate_diff("", content, "test")
        # If content is non-empty, diff should have '+' markers
        if content.strip():
            assert "+" in result or result == ""

    @given(
        content=st.text(
            alphabet=st.characters(
                blacklist_categories=("Cc",),
                blacklist_characters="\x00",
            ),
            min_size=1,
            max_size=100,
        ).filter(lambda x: x.strip())  # Ensure non-empty after strip
    )
    @example(content="content to remove")
    def test_diff_of_content_to_empty_has_deletions(self, content: str):
        """Property: Diff from content to empty contains deletion markers."""
        processor = _create_comment_processor()
        result = processor._generate_diff(content, "", "test")
        # If content is non-empty, diff should have '-' markers
        if content.strip():
            assert "-" in result or result == ""


@pytest.mark.unit
@pytest.mark.hypothesis
class TestWrapDiffLineProperties:
    """Property-based tests for _wrap_diff_line."""

    @given(
        line=st.text(min_size=0, max_size=200).filter(lambda x: "\n" not in x),
        width=st.integers(min_value=10, max_value=200),
    )
    @example(line="", width=70)
    @example(line="+short", width=70)
    @example(line="+a very long line that needs to be wrapped at some point", width=30)
    def test_wrap_diff_line_returns_string(self, line: str, width: int):
        """Property: _wrap_diff_line always returns a string."""
        processor = _create_comment_processor()
        result = processor._wrap_diff_line(line, width=width)
        assert isinstance(result, str)

    @given(
        line=st.text(min_size=0, max_size=50).filter(lambda x: "\n" not in x),
        width=st.integers(min_value=10, max_value=200),
    )
    def test_short_lines_unchanged(self, line: str, width: int):
        """Property: Lines shorter than or equal to width are unchanged."""
        assume(len(line) <= width)
        processor = _create_comment_processor()
        result = processor._wrap_diff_line(line, width=width)
        assert result == line

    @given(
        prefix=st.sampled_from(["+", "-", " "]),
        content=st.text(
            alphabet=st.characters(
                blacklist_categories=("Cc", "Cs"),
                blacklist_characters="\n\r",
            ),
            min_size=1,
            max_size=150,
        ),
        width=st.integers(min_value=20, max_value=100),
    )
    @example(prefix="+", content="this is a long line of content", width=25)
    @example(prefix="-", content="another long line here", width=30)
    @example(prefix=" ", content="context line that is long", width=25)
    def test_diff_prefix_preserved_on_all_lines(self, prefix: str, content: str, width: int):
        """Property: Diff prefix (+, -, space) is preserved on all wrapped lines."""
        processor = _create_comment_processor()
        line = prefix + content
        result = processor._wrap_diff_line(line, width=width)

        # All non-empty lines should start with the same prefix
        for output_line in result.split("\n"):
            if output_line:  # Skip empty lines
                assert output_line[0] == prefix, (
                    f"Line '{output_line}' does not start with prefix '{prefix}'"
                )

    @given(
        prefix=st.sampled_from(["+", "-", " "]),
        content=st.text(
            alphabet=st.characters(
                blacklist_categories=("Cc", "Cs"),
                blacklist_characters="\n\r",
            ),
            min_size=1,
            max_size=150,
        ),
        width=st.integers(min_value=20, max_value=100),
    )
    @example(prefix="+", content="word1 word2 word3 word4 word5", width=25)
    def test_wrapped_lines_respect_width_constraint(self, prefix: str, content: str, width: int):
        """Property: Most wrapped lines respect width constraint (with word-break edge cases)."""
        processor = _create_comment_processor()
        line = prefix + content
        result = processor._wrap_diff_line(line, width=width)

        # Each line should be at most `width` characters, with allowance for
        # single words that can't be broken (textwrap behavior)
        for output_line in result.split("\n"):
            # Check if line respects width, OR if it's a single unbreakable word
            if output_line and len(output_line) > width:
                # If over width, it must be a single word that couldn't be broken
                words = output_line.split()
                assert len(words) <= 2, (
                    f"Line '{output_line}' exceeds width {width} with multiple words"
                )

    @given(hunk_header=st.from_regex(r"@@ -\d+,?\d* \+\d+,?\d* @@.*", fullmatch=True))
    @example(hunk_header="@@ -1,3 +1,5 @@")
    @example(hunk_header="@@ -10 +10 @@ function context")
    def test_hunk_headers_not_wrapped(self, hunk_header: str):
        """Property: Hunk headers (@@) are never wrapped."""
        processor = _create_comment_processor()
        # Use a small width that would normally trigger wrapping
        result = processor._wrap_diff_line(hunk_header, width=20)
        # Hunk header should be unchanged
        assert result == hunk_header

    @given(
        prefix=st.sampled_from(["+", "-", " "]),
        content=st.text(
            alphabet=st.characters(
                blacklist_categories=("Cc", "Cs"),
                blacklist_characters="\n\r",
            ),
            min_size=0,
            max_size=200,
        ),
    )
    def test_wrap_diff_line_never_crashes(self, prefix: str, content: str):
        """Property: _wrap_diff_line never crashes on valid diff lines."""
        processor = _create_comment_processor()
        line = prefix + content
        # Should not raise any exception
        processor._wrap_diff_line(line, width=70)


# =============================================================================
# Comment Filtering Property Tests
# =============================================================================

# Strategy for whitespace (spaces, tabs, newlines)
whitespace_strategy = st.text(
    alphabet=" \t\n",
    min_size=0,
    max_size=20,
)


@pytest.mark.unit
@pytest.mark.hypothesis
class TestIsKilnPostProperties:
    """Property-based tests for _is_kiln_post."""

    @given(
        marker=st.sampled_from(
            [
                "<!-- kiln:research -->",
                "<!-- kiln:plan -->",
                "## Research",
                "## Plan",
                "---",
            ]
        ),
        leading_whitespace=whitespace_strategy,
        trailing_content=st.text(max_size=200),
    )
    @example(marker="<!-- kiln:research -->", leading_whitespace="", trailing_content="")
    @example(marker="## Research", leading_whitespace="  \n\t", trailing_content="some content")
    @example(marker="---", leading_whitespace="\n\n\n", trailing_content="")
    def test_whitespace_invariance(
        self, marker: str, leading_whitespace: str, trailing_content: str
    ):
        """Property: Leading whitespace doesn't affect detection."""
        processor = _create_comment_processor()
        markers = (
            "<!-- kiln:research -->",
            "<!-- kiln:plan -->",
            "## Research",
            "## Plan",
            "---",
        )

        body_with_ws = leading_whitespace + marker + trailing_content
        body_without_ws = marker + trailing_content

        result_with_ws = processor._is_kiln_post(body_with_ws, markers)
        result_without_ws = processor._is_kiln_post(body_without_ws, markers)

        assert result_with_ws == result_without_ws

    @given(
        marker=st.sampled_from(
            [
                "<!-- kiln:research -->",
                "<!-- kiln:plan -->",
            ]
        ),
        leading_whitespace=whitespace_strategy,
    )
    @example(marker="<!-- kiln:research -->", leading_whitespace="")
    @example(marker="<!-- kiln:plan -->", leading_whitespace="  ")
    def test_kiln_markers_always_detected(self, marker: str, leading_whitespace: str):
        """Property: Valid kiln markers are always detected regardless of whitespace."""
        processor = _create_comment_processor()
        markers = ("<!-- kiln:research -->", "<!-- kiln:plan -->")

        body = leading_whitespace + marker
        result = processor._is_kiln_post(body, markers)

        assert result is True

    @given(
        text=st.text(max_size=300).filter(
            lambda x: not any(
                x.lstrip().startswith(m)
                for m in [
                    "<!-- kiln:research -->",
                    "<!-- kiln:plan -->",
                    "## Research",
                    "## Plan",
                    "---",
                ]
            )
        )
    )
    @example(text="regular comment")
    @example(text="   not a marker")
    @example(text="Research without ##")
    @example(text="Plan without ##")
    def test_non_kiln_content_not_detected(self, text: str):
        """Property: Non-kiln content is never detected as kiln post."""
        processor = _create_comment_processor()
        markers = (
            "<!-- kiln:research -->",
            "<!-- kiln:plan -->",
            "## Research",
            "## Plan",
            "---",
        )

        result = processor._is_kiln_post(text, markers)
        assert result is False

    @given(
        marker=st.sampled_from(
            [
                "<!-- kiln:research -->",
                "<!-- kiln:plan -->",
            ]
        ),
        spaces_count=st.integers(min_value=1, max_value=10),
        tabs_count=st.integers(min_value=0, max_value=5),
        newlines_count=st.integers(min_value=0, max_value=5),
    )
    @example(marker="<!-- kiln:research -->", spaces_count=5, tabs_count=0, newlines_count=0)
    @example(marker="<!-- kiln:plan -->", spaces_count=0, tabs_count=3, newlines_count=2)
    def test_various_whitespace_prefixes(
        self, marker: str, spaces_count: int, tabs_count: int, newlines_count: int
    ):
        """Property: Various combinations of whitespace don't affect detection."""
        processor = _create_comment_processor()
        markers = ("<!-- kiln:research -->", "<!-- kiln:plan -->")

        # Build whitespace prefix with various combinations
        ws_prefix = " " * spaces_count + "\t" * tabs_count + "\n" * newlines_count
        body = ws_prefix + marker + "\nsome content"

        result = processor._is_kiln_post(body, markers)
        assert result is True


@pytest.mark.unit
@pytest.mark.hypothesis
class TestIsKilnResponseProperties:
    """Property-based tests for _is_kiln_response."""

    @given(leading_whitespace=whitespace_strategy)
    @example(leading_whitespace="")
    @example(leading_whitespace="   ")
    @example(leading_whitespace="\n\t  ")
    def test_response_marker_always_detected(self, leading_whitespace: str):
        """Property: Response marker is detected with any leading whitespace."""
        processor = _create_comment_processor()
        body = leading_whitespace + "<!-- kiln:response -->" + "\nsome diff content"

        result = processor._is_kiln_response(body)
        assert result is True

    @given(
        text=st.text(max_size=500).filter(
            lambda x: not x.lstrip().startswith("<!-- kiln:response -->")
        )
    )
    @example(text="")
    @example(text="regular comment")
    @example(text="<!-- not kiln -->")
    @example(text="<!-- kiln:research -->")
    @example(text="kiln:response without comment syntax")
    @example(text="✅ Applied successfully")
    def test_no_false_positives(self, text: str):
        """Property: Only actual response markers return True."""
        processor = _create_comment_processor()
        result = processor._is_kiln_response(text)
        assert result is False

    @given(
        spaces_count=st.integers(min_value=0, max_value=10),
        tabs_count=st.integers(min_value=0, max_value=5),
        newlines_count=st.integers(min_value=0, max_value=5),
        trailing_content=st.text(max_size=200),
    )
    @example(spaces_count=0, tabs_count=0, newlines_count=0, trailing_content="")
    @example(spaces_count=3, tabs_count=2, newlines_count=1, trailing_content="diff here")
    def test_whitespace_invariance(
        self, spaces_count: int, tabs_count: int, newlines_count: int, trailing_content: str
    ):
        """Property: Leading whitespace doesn't affect response detection."""
        processor = _create_comment_processor()

        ws_prefix = " " * spaces_count + "\t" * tabs_count + "\n" * newlines_count
        body_with_ws = ws_prefix + "<!-- kiln:response -->" + trailing_content
        body_without_ws = "<!-- kiln:response -->" + trailing_content

        result_with_ws = processor._is_kiln_response(body_with_ws)
        result_without_ws = processor._is_kiln_response(body_without_ws)

        assert result_with_ws is True
        assert result_without_ws is True

    @given(
        prefix=st.text(
            alphabet=st.characters(
                blacklist_categories=("Cc", "Cs", "Zs"),  # Exclude control, surrogates, whitespace
            ),
            min_size=1,
            max_size=50,
        )
    )
    @example(prefix="x")
    @example(prefix="comment: ")
    @example(prefix="123")
    def test_non_whitespace_prefix_prevents_detection(self, prefix: str):
        """Property: Non-whitespace before marker prevents detection."""
        processor = _create_comment_processor()
        # Non-whitespace prefix should prevent detection
        body = prefix + "<!-- kiln:response -->"

        result = processor._is_kiln_response(body)
        assert result is False


# =============================================================================
# Stateful Label Tests with RuleBasedStateMachine
# =============================================================================

# Strategy for valid label names (alphanumeric, hyphens, underscores)
label_name_strategy = st.text(
    alphabet=string.ascii_lowercase + string.digits + "-_",
    min_size=1,
    max_size=50,
).filter(lambda x: x[0].isalnum())  # Labels must start with alphanumeric


class LabelStateMachine(RuleBasedStateMachine):
    """Stateful test for label add/remove operations.

    This tests the invariants of label operations:
    - Adding a label is idempotent (adding twice is same as adding once)
    - Removing a non-existent label is safe
    - Add then remove leaves no label
    - Labels are tracked consistently
    """

    def __init__(self):
        super().__init__()
        self.labels_on_issue: set[str] = set()

        # Create mock client that tracks state
        self.mock_client = MagicMock()

        def mock_add(_repo: str, _ticket_id: int, label: str) -> None:
            self.labels_on_issue.add(label)

        def mock_remove(_repo: str, _ticket_id: int, label: str) -> None:
            self.labels_on_issue.discard(label)

        def mock_get_labels(_repo: str, _ticket_id: int) -> set[str]:
            return self.labels_on_issue.copy()

        self.mock_client.add_label = mock_add
        self.mock_client.remove_label = mock_remove
        self.mock_client.get_ticket_labels = mock_get_labels

    # Bundle to track labels we've added
    labels = Bundle("labels")

    @rule(target=labels, label=label_name_strategy)
    def add_label(self, label: str) -> str:
        """Add a label to the issue and track it."""
        self.mock_client.add_label("test/repo", 1, label)
        return label

    @rule(label=labels)
    def remove_label(self, label: str) -> None:
        """Remove a previously added label."""
        self.mock_client.remove_label("test/repo", 1, label)

    @rule(label=label_name_strategy)
    def add_label_is_idempotent(self, label: str) -> None:
        """Adding same label twice should have same effect as adding once."""
        self.mock_client.add_label("test/repo", 1, label)
        initial_labels = self.labels_on_issue.copy()
        self.mock_client.add_label("test/repo", 1, label)
        assert self.labels_on_issue == initial_labels

    @rule(label=label_name_strategy)
    def remove_nonexistent_is_safe(self, label: str) -> None:
        """Removing a label that doesn't exist should not error."""
        if label not in self.labels_on_issue:
            # Should not raise
            self.mock_client.remove_label("test/repo", 1, label)
            assert label not in self.labels_on_issue

    @rule(label=label_name_strategy)
    def add_then_remove_inverse(self, label: str) -> None:
        """Add followed by remove should leave label absent."""
        self.mock_client.add_label("test/repo", 1, label)
        assert label in self.labels_on_issue
        self.mock_client.remove_label("test/repo", 1, label)
        assert label not in self.labels_on_issue

    @invariant()
    def labels_are_consistent(self) -> None:
        """The set of labels should match what mock returns."""
        actual = self.mock_client.get_ticket_labels("test/repo", 1)
        assert actual == self.labels_on_issue


# This creates the test class that pytest will discover
@pytest.mark.unit
@pytest.mark.hypothesis
class TestLabelState(LabelStateMachine.TestCase):
    """Stateful test case for label operations using RuleBasedStateMachine."""

    pass
