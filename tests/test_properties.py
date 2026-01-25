"""Property-based tests using Hypothesis.

This module contains property-based tests that complement the existing example-based
tests by generating random inputs to find edge cases and verify invariants.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st
from hypothesis.stateful import Bundle, RuleBasedStateMachine, initialize, invariant, rule

from src.cli import parse_issue_arg
from src.comment_processor import CommentProcessor
from src.config import parse_config_file
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


@pytest.mark.unit
class TestConfigParsingProperties:
    """Property-based tests for config file parsing.

    Tests the parse_config_file function which reads KEY=value format config files.
    Uses tempfile.TemporaryDirectory instead of pytest's tmp_path fixture to avoid
    Hypothesis health check issues with function-scoped fixtures.
    """

    @given(
        key=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd"),
                whitelist_characters="_",
            ),
        ),
        value=st.text(
            min_size=0,
            max_size=100,
            # Exclude newlines and quote characters to avoid quote-stripping edge cases
            alphabet=st.characters(blacklist_characters="\n\r\"'"),
        ),
    )
    @example(key="KEY", value="value")
    @example(key="MY_VAR", value="some_value_123")
    @example(key="EMPTY", value="")
    def test_parse_config_file_handles_arbitrary_key_value(
        self, key: str, value: str
    ):
        """Test that parse_config_file handles arbitrary key-value content.

        The function should correctly parse KEY=value pairs from a config file.
        Values without quotes should be returned as-is (stripped).
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_file = Path(tmp_dir) / "config"
            config_file.write_text(f"{key}={value}")

            result = parse_config_file(config_file)

            # Key should be in result with the value (possibly stripped)
            assert key.strip() in result
            # Value should match (with surrounding whitespace stripped)
            assert result[key.strip()] == value.strip()

    @given(
        key=st.text(
            min_size=1,
            max_size=20,
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
        ),
        value=st.text(
            min_size=0,
            max_size=50,
            alphabet=st.characters(blacklist_characters='\n\r"\''),
        ),
    )
    @example(key="KEY", value="value with spaces")
    @example(key="VAR", value="")
    def test_double_quote_stripping(self, key: str, value: str):
        """Test that double quotes are stripped from values."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_file = Path(tmp_dir) / "config"
            config_file.write_text(f'{key}="{value}"')

            result = parse_config_file(config_file)

            assert key in result
            # Value should have quotes stripped
            assert result[key] == value

    @given(
        key=st.text(
            min_size=1,
            max_size=20,
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
        ),
        value=st.text(
            min_size=0,
            max_size=50,
            alphabet=st.characters(blacklist_characters="\n\r\"'"),
        ),
    )
    @example(key="KEY", value="value with spaces")
    @example(key="VAR", value="")
    def test_single_quote_stripping(self, key: str, value: str):
        """Test that single quotes are stripped from values."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_file = Path(tmp_dir) / "config"
            config_file.write_text(f"{key}='{value}'")

            result = parse_config_file(config_file)

            assert key in result
            # Value should have quotes stripped
            assert result[key] == value

    @given(
        leading_ws=st.text(
            max_size=5, alphabet=st.sampled_from(" \t")
        ),
        key=st.text(
            min_size=1,
            max_size=20,
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
        ),
        trailing_ws=st.text(
            max_size=5, alphabet=st.sampled_from(" \t")
        ),
        value=st.text(
            min_size=1,
            max_size=30,
            # Exclude quotes to avoid quote-stripping behavior
            alphabet=st.characters(blacklist_characters="\n\r\"'"),
        ),
    )
    @example(leading_ws="  ", key="KEY", trailing_ws="  ", value="value")
    @example(leading_ws="\t", key="VAR", trailing_ws=" ", value="  test  ")
    def test_whitespace_handling_around_keys_and_values(
        self, leading_ws: str, key: str, trailing_ws: str, value: str
    ):
        """Test that whitespace around keys and values is handled correctly.

        Leading/trailing whitespace on the line is stripped.
        Whitespace around the = sign is stripped from both key and value.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_file = Path(tmp_dir) / "config"
            # Format: "  KEY  =  value  " with various whitespace
            config_file.write_text(f"{leading_ws}{key}{trailing_ws}={trailing_ws}{value}{leading_ws}")

            result = parse_config_file(config_file)

            # Key should be stripped
            assert key in result
            # Value should be stripped
            assert result[key] == value.strip()

    @given(
        comment=st.text(
            min_size=0,
            max_size=100,
            alphabet=st.characters(blacklist_characters="\n\r"),
        ),
        key=st.text(
            min_size=1,
            max_size=20,
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
        ),
        value=st.text(
            min_size=1,
            max_size=30,
            # Exclude quotes to avoid quote-stripping behavior
            alphabet=st.characters(blacklist_characters="\n\r\"'"),
        ),
    )
    @example(comment="This is a comment", key="KEY", value="value")
    @example(comment="", key="VAR", value="test")
    def test_comments_are_ignored(
        self, comment: str, key: str, value: str
    ):
        """Test that comment lines (starting with #) are ignored."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_file = Path(tmp_dir) / "config"
            config_file.write_text(f"# {comment}\n{key}={value}")

            result = parse_config_file(config_file)

            # Only the key=value line should be parsed
            assert len(result) == 1
            assert key in result
            assert result[key] == value.strip()

    @given(
        num_empty_lines=st.integers(min_value=1, max_value=5),
        key=st.text(
            min_size=1,
            max_size=20,
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
        ),
        value=st.text(
            min_size=1,
            max_size=30,
            alphabet=st.characters(
                blacklist_characters="\n\r",
                blacklist_categories=("Cs",),  # Exclude surrogates (not UTF-8 encodable)
            ),
        ),
    )
    @example(num_empty_lines=1, key="KEY", value="value")
    @example(num_empty_lines=3, key="VAR", value="test")
    def test_empty_lines_are_skipped(
        self, num_empty_lines: int, key: str, value: str
    ):
        """Test that empty lines are skipped during parsing."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_file = Path(tmp_dir) / "config"
            empty_lines = "\n" * num_empty_lines
            config_file.write_text(f"{empty_lines}{key}={value}\n{empty_lines}")

            result = parse_config_file(config_file)

            # Only the key=value line should be parsed
            assert len(result) == 1
            assert key in result
            assert result[key] == value.strip()

    @given(
        keys=st.lists(
            st.text(
                min_size=1,
                max_size=20,
                alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
            ),
            min_size=1,
            max_size=5,
            unique=True,
        ),
        values=st.lists(
            st.text(
                min_size=1,
                max_size=30,
                alphabet=st.characters(blacklist_characters="\n\r"),
            ),
            min_size=1,
            max_size=5,
        ),
    )
    @example(keys=["KEY1", "KEY2"], values=["val1", "val2"])
    def test_multiple_key_value_pairs(
        self, keys: list[str], values: list[str]
    ):
        """Test that multiple KEY=value pairs are parsed correctly."""
        # Match lengths
        min_len = min(len(keys), len(values))
        keys = keys[:min_len]
        values = values[:min_len]

        with tempfile.TemporaryDirectory() as tmp_dir:
            config_file = Path(tmp_dir) / "config"
            lines = [f"{k}={v}" for k, v in zip(keys, values)]
            config_file.write_text("\n".join(lines))

            result = parse_config_file(config_file)

            # All keys should be present
            for key, value in zip(keys, values):
                assert key in result
                assert result[key] == value.strip()


@pytest.mark.unit
class TestCommentFilteringProperties:
    """Property-based tests for comment filtering marker detection.

    Tests the marker detection functions that identify kiln-generated posts
    and responses. These functions filter out kiln content when processing
    user comments.
    """

    @given(
        leading_ws=st.text(max_size=10, alphabet=st.sampled_from(" \t\n\r")),
        marker=st.sampled_from(
            list(CommentProcessor.KILN_POST_MARKERS.values())
            + list(CommentProcessor.KILN_POST_LEGACY_MARKERS.values())
        ),
        trailing_content=st.text(max_size=100),
    )
    @example(leading_ws="", marker="<!-- kiln:research -->", trailing_content="content")
    @example(leading_ws="  ", marker="<!-- kiln:plan -->", trailing_content="")
    @example(leading_ws="\n\n", marker="## Research Findings", trailing_content="stuff")
    @example(leading_ws="\t ", marker="## Implementation Plan", trailing_content="")
    def test_is_kiln_post_whitespace_invariance(
        self, leading_ws: str, marker: str, trailing_content: str
    ):
        """Test that _is_kiln_post correctly detects markers regardless of leading whitespace.

        The function strips leading whitespace before checking for markers,
        so leading whitespace should not affect detection.
        """
        processor = _make_comment_processor()
        all_markers = tuple(CommentProcessor.KILN_POST_MARKERS.values()) + tuple(
            CommentProcessor.KILN_POST_LEGACY_MARKERS.values()
        )

        # Body with leading whitespace + marker should be detected
        body = f"{leading_ws}{marker}{trailing_content}"
        result = processor._is_kiln_post(body, all_markers)

        assert result is True, (
            f"Expected _is_kiln_post to return True for body starting with "
            f"whitespace + marker: {body!r}"
        )

    @given(
        leading_ws=st.text(max_size=10, alphabet=st.sampled_from(" \t\n\r")),
        trailing_content=st.text(max_size=100),
    )
    @example(leading_ws="", trailing_content="Applied changes to **research**:")
    @example(leading_ws="  \n", trailing_content="")
    @example(leading_ws="\t", trailing_content="some content here")
    def test_is_kiln_response_whitespace_invariance(
        self, leading_ws: str, trailing_content: str
    ):
        """Test that _is_kiln_response correctly detects marker regardless of leading whitespace.

        The function strips leading whitespace before checking for the response marker,
        so leading whitespace should not affect detection.
        """
        processor = _make_comment_processor()
        marker = CommentProcessor.KILN_RESPONSE_MARKER

        # Body with leading whitespace + marker should be detected
        body = f"{leading_ws}{marker}{trailing_content}"
        result = processor._is_kiln_response(body)

        assert result is True, (
            f"Expected _is_kiln_response to return True for body starting with "
            f"whitespace + marker: {body!r}"
        )

    @given(
        content=st.text(
            min_size=1,
            max_size=200,
            alphabet=st.characters(blacklist_characters="<#"),
        ).filter(lambda x: x.strip()),
    )
    @example(content="This is a user comment")
    @example(content="Please fix the bug in line 42")
    @example(content="LGTM!")
    def test_non_kiln_content_not_detected_as_kiln_post(self, content: str):
        """Test that arbitrary user content is not falsely detected as kiln posts.

        Content that doesn't start with a kiln marker should return False.
        """
        processor = _make_comment_processor()
        all_markers = tuple(CommentProcessor.KILN_POST_MARKERS.values()) + tuple(
            CommentProcessor.KILN_POST_LEGACY_MARKERS.values()
        )

        # Ensure content doesn't start with any marker (after stripping)
        stripped = content.lstrip()
        starts_with_marker = any(stripped.startswith(m) for m in all_markers)

        if not starts_with_marker:
            result = processor._is_kiln_post(content, all_markers)
            assert result is False, (
                f"Expected _is_kiln_post to return False for non-kiln content: {content!r}"
            )

    @given(
        content=st.text(
            min_size=1,
            max_size=200,
            alphabet=st.characters(blacklist_characters="<"),
        ).filter(lambda x: x.strip()),
    )
    @example(content="Thanks for the update!")
    @example(content="Can you add more tests?")
    @example(content="Response looks good")
    def test_non_kiln_content_not_detected_as_kiln_response(self, content: str):
        """Test that arbitrary user content is not falsely detected as kiln responses.

        Content that doesn't start with the response marker should return False.
        """
        processor = _make_comment_processor()
        marker = CommentProcessor.KILN_RESPONSE_MARKER

        # Ensure content doesn't start with the marker (after stripping)
        stripped = content.lstrip()
        starts_with_marker = stripped.startswith(marker)

        if not starts_with_marker:
            result = processor._is_kiln_response(content)
            assert result is False, (
                f"Expected _is_kiln_response to return False for non-kiln content: {content!r}"
            )

    @given(
        marker=st.sampled_from(
            list(CommentProcessor.KILN_POST_MARKERS.values())
            + list(CommentProcessor.KILN_POST_LEGACY_MARKERS.values())
        ),
    )
    @example(marker="<!-- kiln:research -->")
    @example(marker="<!-- kiln:plan -->")
    @example(marker="## Research Findings")
    @example(marker="## Implementation Plan")
    def test_marker_detection_consistency(self, marker: str):
        """Test that marker detection is consistent across calls.

        The same input should always produce the same output (deterministic).
        """
        processor = _make_comment_processor()
        all_markers = tuple(CommentProcessor.KILN_POST_MARKERS.values()) + tuple(
            CommentProcessor.KILN_POST_LEGACY_MARKERS.values()
        )

        body = f"{marker}\nSome content here"

        # Call multiple times to ensure consistency
        result1 = processor._is_kiln_post(body, all_markers)
        result2 = processor._is_kiln_post(body, all_markers)
        result3 = processor._is_kiln_post(body, all_markers)

        assert result1 == result2 == result3 == True, (
            f"Expected consistent True result for marker {marker!r}"
        )

    @given(st.text(max_size=500))
    @example("")
    @example("   ")
    @example("\n\n\n")
    def test_is_kiln_post_never_crashes(self, body: str):
        """Test that _is_kiln_post never crashes on arbitrary input."""
        processor = _make_comment_processor()
        all_markers = tuple(CommentProcessor.KILN_POST_MARKERS.values()) + tuple(
            CommentProcessor.KILN_POST_LEGACY_MARKERS.values()
        )

        # Should never raise an exception
        result = processor._is_kiln_post(body, all_markers)
        assert isinstance(result, bool)

    @given(st.text(max_size=500))
    @example("")
    @example("   ")
    @example("\n\n\n")
    def test_is_kiln_response_never_crashes(self, body: str):
        """Test that _is_kiln_response never crashes on arbitrary input."""
        processor = _make_comment_processor()

        # Should never raise an exception
        result = processor._is_kiln_response(body)
        assert isinstance(result, bool)


class MockLabelClient:
    """A mock label client that simulates GitHub label operations.

    This client tracks label state in memory and provides the same interface
    as the real ticket client for add_label, remove_label, and get_ticket_labels.
    Used for stateful property testing of label operation invariants.
    """

    def __init__(self):
        """Initialize with empty label sets for all tickets."""
        self._labels: dict[tuple[str, int], set[str]] = {}

    def get_ticket_labels(self, repo: str, ticket_id: int) -> set[str]:
        """Get current labels for a ticket."""
        return self._labels.get((repo, ticket_id), set()).copy()

    def add_label(self, repo: str, ticket_id: int, label: str) -> None:
        """Add a label to a ticket (idempotent operation)."""
        key = (repo, ticket_id)
        if key not in self._labels:
            self._labels[key] = set()
        self._labels[key].add(label)

    def remove_label(self, repo: str, ticket_id: int, label: str) -> None:
        """Remove a label from a ticket (safe for non-existent labels)."""
        key = (repo, ticket_id)
        if key in self._labels:
            self._labels[key].discard(label)


@pytest.mark.unit
@settings(max_examples=50, stateful_step_count=20)
class LabelOperationsStateMachine(RuleBasedStateMachine):
    """Stateful property tests for label operations.

    This state machine tests the properties of label add/remove operations:
    - Add/remove inverse property: add then remove returns to original state
    - Add idempotency: adding the same label twice equals adding once
    - Remove idempotency: removing a non-existent label is safe

    Uses a mock client to track label state in memory, verifying that the
    operations maintain expected invariants across arbitrary sequences.
    """

    # Bundle for tracking labels that have been added (for targeted removal)
    added_labels = Bundle("added_labels")

    # Strategy for generating valid label names
    label_strategy = st.text(
        min_size=1,
        max_size=20,
        alphabet=st.characters(
            whitelist_categories=("Lu", "Ll", "Nd"),
            whitelist_characters="-_",
        ),
    ).filter(lambda x: x.strip() == x and len(x.strip()) > 0)

    def __init__(self):
        """Initialize the state machine with a mock client and model state."""
        super().__init__()
        self.client = MockLabelClient()
        self.repo = "github.com/test/repo"
        self.ticket_id = 1
        # Track expected state separately to verify against client
        self.expected_labels: set[str] = set()

    @initialize()
    def init_state(self):
        """Initialize clean state for each test run."""
        self.client = MockLabelClient()
        self.expected_labels = set()

    @rule(target=added_labels, label=label_strategy)
    def add_label(self, label: str) -> str:
        """Add a label and track it in the bundle.

        Returns the label so it can be used for targeted removal.
        """
        self.client.add_label(self.repo, self.ticket_id, label)
        self.expected_labels.add(label)
        return label

    @rule(label=added_labels)
    def remove_known_label(self, label: str):
        """Remove a label that was previously added.

        This tests the add/remove inverse property: after adding and then
        removing a label, the state should be as if the label was never there
        (for that specific label).
        """
        self.client.remove_label(self.repo, self.ticket_id, label)
        self.expected_labels.discard(label)

    @rule(label=label_strategy)
    def remove_arbitrary_label(self, label: str):
        """Remove an arbitrary label (may or may not exist).

        This tests remove idempotency: removing a non-existent label
        should be a no-op and not raise an error.
        """
        self.client.remove_label(self.repo, self.ticket_id, label)
        self.expected_labels.discard(label)

    @rule(label=label_strategy)
    def add_label_twice(self, label: str):
        """Add the same label twice to test idempotency.

        Adding the same label twice should have the same effect as adding once.
        """
        self.client.add_label(self.repo, self.ticket_id, label)
        self.client.add_label(self.repo, self.ticket_id, label)
        self.expected_labels.add(label)

    @rule(label=label_strategy)
    def add_then_remove(self, label: str):
        """Add and immediately remove a label.

        Tests the inverse property: the label should no longer be present.
        """
        self.client.add_label(self.repo, self.ticket_id, label)
        self.client.remove_label(self.repo, self.ticket_id, label)
        # Label was added then removed, so it should not be in expected
        # (unless it was already there from before, but we use discard)
        self.expected_labels.discard(label)

    @invariant()
    def labels_match_expected(self):
        """Verify the client's labels match our expected state.

        This invariant ensures that after any sequence of operations,
        the actual label state matches what we expect based on the
        operations performed.
        """
        actual = self.client.get_ticket_labels(self.repo, self.ticket_id)
        assert actual == self.expected_labels, (
            f"Label mismatch: actual={actual}, expected={self.expected_labels}"
        )

    @invariant()
    def labels_are_strings(self):
        """Verify all labels are non-empty strings."""
        labels = self.client.get_ticket_labels(self.repo, self.ticket_id)
        for label in labels:
            assert isinstance(label, str)
            assert len(label) > 0


# Create pytest test class from state machine
# Settings are configured on the state machine class above
class TestLabelOperationsStateful(LabelOperationsStateMachine.TestCase):
    """Pytest wrapper for the label operations state machine.

    This test class runs the stateful property tests using pytest.
    It inherits from the state machine's TestCase to integrate with pytest.
    """

    pass
