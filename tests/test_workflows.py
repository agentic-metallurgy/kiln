"""Unit tests for the workflows module."""

import pytest

from src.workflows.base import WorkflowContext
from src.workflows.implement import ImplementWorkflow, count_checkboxes, count_tasks
from src.workflows.plan import PlanWorkflow
from src.workflows.prepare import PrepareWorkflow
from src.workflows.process_comments import ProcessCommentsWorkflow
from src.workflows.research import ResearchWorkflow


@pytest.fixture
def workflow_context():
    """Fixture providing a sample WorkflowContext for tests."""
    return WorkflowContext(
        repo="github.com/owner/test-repo",
        issue_number=42,
        issue_title="Add feature X to improve performance",
        workspace_path="/tmp/workspaces/owner-test-repo-42",
    )


@pytest.mark.unit
class TestWorkflowContext:
    """Tests for WorkflowContext dataclass."""

    def test_workflow_context_creation(self):
        """Test creating a WorkflowContext instance."""
        ctx = WorkflowContext(
            repo="owner/repo",
            issue_number=123,
            issue_title="Test Issue",
            workspace_path="/path/to/workspace",
        )

        assert ctx.repo == "owner/repo"
        assert ctx.issue_number == 123
        assert ctx.issue_title == "Test Issue"
        assert ctx.workspace_path == "/path/to/workspace"


    def test_workflow_context_issue_body_can_be_set(self):
        """Test that issue_body can be set during creation."""
        ctx = WorkflowContext(
            repo="owner/repo",
            issue_number=42,
            issue_title="Test",
            workspace_path="/tmp/workspace",
            issue_body="This is the issue body content.",
        )
        assert ctx.issue_body == "This is the issue body content."

    def test_workflow_context_username_self_can_be_set(self):
        """Test that username_self can be set during creation."""
        ctx = WorkflowContext(
            repo="owner/repo",
            issue_number=42,
            issue_title="Test",
            workspace_path="/tmp/workspace",
            username_self="user1",
        )
        assert ctx.username_self == "user1"


@pytest.mark.unit
class TestResearchWorkflow:
    """Tests for ResearchWorkflow."""

    def test_research_workflow_init_returns_list(self, workflow_context):
        """Test that init() returns a list of prompts."""
        workflow = ResearchWorkflow()
        prompts = workflow.init(workflow_context)

        assert isinstance(prompts, list)
        assert len(prompts) > 0
        assert all(isinstance(prompt, str) for prompt in prompts)

    def test_research_workflow_init_returns_one_prompt(self, workflow_context):
        """Test that ResearchWorkflow returns exactly 1 prompt."""
        workflow = ResearchWorkflow()
        prompts = workflow.init(workflow_context)

        assert len(prompts) == 1

    def test_research_workflow_prompts_contain_issue_number(self, workflow_context):
        """Test that prompts contain the issue number in URL format."""
        workflow = ResearchWorkflow()
        prompts = workflow.init(workflow_context)

        assert str(workflow_context.issue_number) in prompts[0]
        # Issue number appears in URL format: /issues/42
        assert f"/issues/{workflow_context.issue_number}" in prompts[0]

    def test_research_workflow_prompt_uses_slash_command(self, workflow_context):
        """Test that the prompt uses the research slash command."""
        workflow = ResearchWorkflow()
        prompts = workflow.init(workflow_context)

        assert "/kiln-research_codebase_github" in prompts[0]


@pytest.mark.unit
class TestPlanWorkflow:
    """Tests for PlanWorkflow."""

    def test_plan_workflow_init_returns_list(self, workflow_context):
        """Test that init() returns a list of prompts."""
        workflow = PlanWorkflow()
        prompts = workflow.init(workflow_context)

        assert isinstance(prompts, list)
        assert len(prompts) > 0
        assert all(isinstance(prompt, str) for prompt in prompts)

    def test_plan_workflow_init_returns_one_prompt(self, workflow_context):
        """Test that PlanWorkflow returns exactly 1 prompt."""
        workflow = PlanWorkflow()
        prompts = workflow.init(workflow_context)

        assert len(prompts) == 1

    def test_plan_workflow_prompts_contain_issue_number(self, workflow_context):
        """Test that prompts contain the issue number in URL format."""
        workflow = PlanWorkflow()
        prompts = workflow.init(workflow_context)

        assert str(workflow_context.issue_number) in prompts[0]
        # Issue number appears in URL format: /issues/42
        assert f"/issues/{workflow_context.issue_number}" in prompts[0]

    def test_plan_workflow_prompts_contain_repo(self, workflow_context):
        """Test that prompts contain the repository name."""
        workflow = PlanWorkflow()
        prompts = workflow.init(workflow_context)

        assert workflow_context.repo in prompts[0]

    def test_plan_workflow_prompt_uses_slash_command(self, workflow_context):
        """Test that the prompt uses the create_plan slash command."""
        workflow = PlanWorkflow()
        prompts = workflow.init(workflow_context)

        assert "/kiln-create_plan" in prompts[0]


@pytest.mark.unit
class TestProcessCommentsWorkflow:
    """Tests for ProcessCommentsWorkflow."""

    def test_process_comments_workflow_returns_one_prompt(self):
        """Test that workflow returns exactly one prompt."""
        ctx = WorkflowContext(
            repo="owner/repo",
            issue_number=42,
            issue_title="Test Issue",
            workspace_path="/tmp/workspace",
            comment_body="Please add more detail",
            target_type="research",
        )
        workflow = ProcessCommentsWorkflow()
        prompts = workflow.init(ctx)

        assert len(prompts) == 1

    def test_process_comments_workflow_includes_comment_body(self):
        """Test that the prompt includes the user's comment."""
        comment_text = "Please expand on option B with more examples"
        ctx = WorkflowContext(
            repo="owner/repo",
            issue_number=42,
            issue_title="Test Issue",
            workspace_path="/tmp/workspace",
            comment_body=comment_text,
            target_type="research",
        )
        workflow = ProcessCommentsWorkflow()
        prompts = workflow.init(ctx)

        assert comment_text in prompts[0]

    def test_process_comments_workflow_includes_target_type(self):
        """Test that the prompt includes the target type."""
        ctx = WorkflowContext(
            repo="owner/repo",
            issue_number=42,
            issue_title="Test Issue",
            workspace_path="/tmp/workspace",
            comment_body="Feedback",
            target_type="plan",
        )
        workflow = ProcessCommentsWorkflow()
        prompts = workflow.init(ctx)

        assert "plan" in prompts[0]
        assert "Implementation Plan section" in prompts[0]
        assert "issue description" in prompts[0]

    def test_process_comments_workflow_includes_issue_reference(self):
        """Test that the prompt includes repo and issue number."""
        ctx = WorkflowContext(
            repo="myorg/myrepo",
            issue_number=123,
            issue_title="Test Issue",
            workspace_path="/tmp/workspace",
            comment_body="Feedback",
            target_type="description",
        )
        workflow = ProcessCommentsWorkflow()
        prompts = workflow.init(ctx)

        assert "myorg/myrepo" in prompts[0]
        assert "123" in prompts[0]

    def test_process_comments_workflow_defaults_to_description(self):
        """Test that target defaults to description when not specified."""
        ctx = WorkflowContext(
            repo="owner/repo",
            issue_number=42,
            issue_title="Test Issue",
            workspace_path="/tmp/workspace",
            comment_body="Feedback",
            target_type=None,  # Not specified
        )
        workflow = ProcessCommentsWorkflow()
        prompts = workflow.init(ctx)

        assert "description" in prompts[0]

    def test_process_comments_workflow_research_target(self):
        """Test prompt generation for research target."""
        ctx = WorkflowContext(
            repo="owner/repo",
            issue_number=42,
            issue_title="Test Issue",
            workspace_path="/tmp/workspace",
            comment_body="Add more options",
            target_type="research",
        )
        workflow = ProcessCommentsWorkflow()
        prompts = workflow.init(ctx)

        assert "Research Findings section" in prompts[0]
        assert "issue description" in prompts[0]
        assert "research" in prompts[0]

    def test_process_comments_workflow_instructs_in_place_edit(self):
        """Test that the prompt instructs to edit in-place, not create new comments."""
        ctx = WorkflowContext(
            repo="owner/repo",
            issue_number=42,
            issue_title="Test Issue",
            workspace_path="/tmp/workspace",
            comment_body="Feedback",
            target_type="plan",
        )
        workflow = ProcessCommentsWorkflow()
        prompts = workflow.init(ctx)

        assert "IN-PLACE" in prompts[0]
        assert "NOT create new comments" in prompts[0]


@pytest.mark.unit
class TestPrepareWorkflow:
    """Tests for PrepareWorkflow."""

    def test_prepare_workflow_returns_two_prompts(self):
        """Test that PrepareWorkflow returns exactly 2 prompts."""
        ctx = WorkflowContext(
            repo="owner/repo",
            issue_number=42,
            issue_title="Test Issue",
            workspace_path="/tmp/workspaces",
        )
        workflow = PrepareWorkflow()
        prompts = workflow.init(ctx)

        assert len(prompts) == 2

    def test_prepare_workflow_first_prompt_clones_repo(self):
        """Test that first prompt handles cloning/updating the repo."""
        ctx = WorkflowContext(
            repo="owner/repo",
            issue_number=42,
            issue_title="Test Issue",
            workspace_path="/tmp/workspaces",
        )
        workflow = PrepareWorkflow()
        prompts = workflow.init(ctx)

        assert "Clone https://github.com/owner/repo.git" in prompts[0]
        assert "to /tmp/workspaces/repo if missing" in prompts[0]

    def test_prepare_workflow_with_issue_body_includes_body_directly(self):
        """Test that with issue_body, prompt includes the body directly."""
        issue_body = "## Summary\n\nThis is the issue description."
        ctx = WorkflowContext(
            repo="owner/repo",
            issue_number=42,
            issue_title="Test Issue Title",
            workspace_path="/tmp/workspaces",
            issue_body=issue_body,
        )
        workflow = PrepareWorkflow()
        prompts = workflow.init(ctx)

        # Should include the issue body directly
        assert issue_body in prompts[1]
        assert "Issue title: Test Issue Title" in prompts[1]
        assert "Issue description:" in prompts[1]
        # Should NOT ask Claude to read the issue
        assert "Read github issue" not in prompts[1]

    def test_prepare_workflow_with_issue_body_includes_issue_number(self):
        """Test that with issue_body, prompt still references issue number."""
        ctx = WorkflowContext(
            repo="owner/repo",
            issue_number=123,
            issue_title="Test Issue",
            workspace_path="/tmp/workspaces",
            issue_body="Issue body content",
        )
        workflow = PrepareWorkflow()
        prompts = workflow.init(ctx)

        # Issue number appears in the worktree path and branch instructions
        assert "repo-issue-123" in prompts[1]
        assert "(123-)" in prompts[1]

    def test_prepare_workflow_worktree_path_correct(self):
        """Test that worktree path is constructed correctly."""
        ctx = WorkflowContext(
            repo="myorg/myrepo",
            issue_number=99,
            issue_title="Test Issue",
            workspace_path="/home/user/workspaces",
            issue_body="Body text",
        )
        workflow = PrepareWorkflow()
        prompts = workflow.init(ctx)

        assert "myrepo-issue-99" in prompts[1]

    def test_prepare_workflow_empty_issue_body_treated_as_provided(self):
        """Test that empty string issue_body is treated as provided (not None)."""
        ctx = WorkflowContext(
            repo="owner/repo",
            issue_number=42,
            issue_title="Test Issue",
            workspace_path="/tmp/workspaces",
            issue_body="",  # Empty string, not None
        )
        workflow = PrepareWorkflow()
        prompts = workflow.init(ctx)

        # Should NOT ask Claude to read the issue (empty body is still "provided")
        assert "Read github issue" not in prompts[1]
        assert "Issue description:" in prompts[1]

    def test_prepare_workflow_with_parent_branch_creates_from_parent(self):
        """Test that workflow uses parent branch when provided."""
        ctx = WorkflowContext(
            repo="github.com/owner/repo",
            issue_number=42,
            issue_title="Child Issue",
            workspace_path="/tmp/workspaces",
            issue_body="Child issue body",
            parent_issue_number=10,
            parent_branch="10-parent-feature",
        )
        workflow = PrepareWorkflow()
        prompts = workflow.init(ctx)

        # Should instruct to create from parent branch
        assert "10-parent-feature" in prompts[1]
        assert "parent branch" in prompts[1]
        assert "parent issue #10" in prompts[1]
        assert "git fetch origin 10-parent-feature" in prompts[1]

    def test_prepare_workflow_without_parent_branch_creates_from_main(self):
        """Test that workflow uses main branch when no parent branch provided."""
        ctx = WorkflowContext(
            repo="github.com/owner/repo",
            issue_number=42,
            issue_title="Standalone Issue",
            workspace_path="/tmp/workspaces",
            issue_body="Issue body",
            parent_issue_number=None,
            parent_branch=None,
        )
        workflow = PrepareWorkflow()
        prompts = workflow.init(ctx)

        # Should instruct to create from main branch
        assert "main branch" in prompts[1]
        # Should NOT mention parent branch
        assert "parent branch" not in prompts[1]

    def test_prepare_workflow_with_parent_number_but_no_branch(self):
        """Test that workflow uses main when parent has no open PR."""
        ctx = WorkflowContext(
            repo="github.com/owner/repo",
            issue_number=42,
            issue_title="Child Issue",
            workspace_path="/tmp/workspaces",
            issue_body="Issue body",
            parent_issue_number=10,  # Has parent but no open PR
            parent_branch=None,
        )
        workflow = PrepareWorkflow()
        prompts = workflow.init(ctx)

        # Should still use main branch since no parent PR exists
        assert "main branch" in prompts[1]
        assert "parent branch" not in prompts[1]

    def test_prepare_workflow_with_explicit_feature_branch_no_parent_issue(self):
        """Test that workflow uses feature_branch messaging when no parent_issue_number.

        When parent_branch is set but parent_issue_number is None, this indicates
        an explicit feature_branch from issue frontmatter, not a parent issue's PR.
        """
        ctx = WorkflowContext(
            repo="github.com/owner/repo",
            issue_number=42,
            issue_title="Feature Issue",
            workspace_path="/tmp/workspaces",
            issue_body="Issue body",
            parent_issue_number=None,  # No parent issue
            parent_branch="my-feature-branch",  # Explicit feature_branch from frontmatter
        )
        workflow = PrepareWorkflow()
        prompts = workflow.init(ctx)

        # Should instruct to create from feature branch with frontmatter messaging
        assert "my-feature-branch" in prompts[1]
        assert "feature branch" in prompts[1]
        assert "specified in issue frontmatter" in prompts[1]
        assert "git fetch origin my-feature-branch" in prompts[1]
        # Should NOT mention parent issue
        assert "parent issue" not in prompts[1]
        assert "parent branch" not in prompts[1]


@pytest.mark.unit
class TestCountTasks:
    """Tests for the count_tasks() helper function."""

    def test_count_tasks_h2_header_format(self):
        """Test counting tasks with ## TASK N: format."""
        markdown = """
## TASK 1: First task
Some description here.

## TASK 2: Second task
Another description.
"""
        assert count_tasks(markdown) == 2

    def test_count_tasks_h3_header_format(self):
        """Test counting tasks with ### TASK N: format."""
        markdown = """
### TASK 1: First task
Some description here.

### TASK 2: Second task
Another description.

### TASK 3: Third task
More description.
"""
        assert count_tasks(markdown) == 3

    def test_count_tasks_bold_format(self):
        """Test counting tasks with **TASK N**: format."""
        markdown = """
**TASK 1**: First task description.

**TASK 2**: Second task description.
"""
        assert count_tasks(markdown) == 2

    def test_count_tasks_case_insensitivity(self):
        """Test that task matching is case insensitive."""
        markdown = """
## task 1: lowercase
## Task 2: titlecase
## TASK 3: uppercase
**task 4**: bold lowercase
"""
        assert count_tasks(markdown) == 4

    def test_count_tasks_empty_string(self):
        """Test that empty string returns 0."""
        assert count_tasks("") == 0

    def test_count_tasks_no_tasks_present(self):
        """Test text without any TASK blocks returns 0."""
        markdown = """
## Overview
This is a document without any tasks.

### Section 1
Some content.

- [ ] A checkbox but not a TASK
"""
        assert count_tasks(markdown) == 0

    def test_count_tasks_multiple_formats_mixed(self):
        """Test counting tasks with mixed header and bold formats."""
        markdown = """
## TASK 1: Header format
Description.

**TASK 2**: Bold format
Description.

### TASK 3: H3 header format
Description.
"""
        assert count_tasks(markdown) == 3

    def test_count_tasks_with_surrounding_content(self):
        """Test tasks embedded in a larger document."""
        markdown = """
# Implementation Plan

## Overview
This plan outlines the work to be done.

## TASK 1: Set up infrastructure
- [ ] Create database
- [ ] Configure server

## TASK 2: Implement features
- [ ] Add login
- [ ] Add logout

## Appendix
Additional notes here.
"""
        assert count_tasks(markdown) == 2


@pytest.mark.unit
class TestCountCheckboxes:
    """Tests for the count_checkboxes() helper function."""

    def test_count_checkboxes_mixed_checked_unchecked(self):
        """Test counting a mix of checked and unchecked checkboxes."""
        markdown = """
- [x] Completed task 1
- [ ] Pending task 2
- [x] Completed task 3
- [ ] Pending task 4
"""
        total, completed = count_checkboxes(markdown)
        assert total == 4
        assert completed == 2

    def test_count_checkboxes_all_checked(self):
        """Test when all checkboxes are checked."""
        markdown = """
- [x] Task 1
- [x] Task 2
- [x] Task 3
"""
        total, completed = count_checkboxes(markdown)
        assert total == 3
        assert completed == 3

    def test_count_checkboxes_all_unchecked(self):
        """Test when all checkboxes are unchecked."""
        markdown = """
- [ ] Task 1
- [ ] Task 2
- [ ] Task 3
- [ ] Task 4
"""
        total, completed = count_checkboxes(markdown)
        assert total == 4
        assert completed == 0

    def test_count_checkboxes_empty_string(self):
        """Test that empty string returns (0, 0)."""
        total, completed = count_checkboxes("")
        assert total == 0
        assert completed == 0

    def test_count_checkboxes_uppercase_x(self):
        """Test that [X] uppercase is counted as checked."""
        markdown = """
- [X] Uppercase checked
- [x] Lowercase checked
- [ ] Unchecked
"""
        total, completed = count_checkboxes(markdown)
        assert total == 3
        assert completed == 2

    def test_count_checkboxes_malformed_not_counted(self):
        """Test that malformed checkboxes without proper space are not counted."""
        markdown = """
- [x] Valid checked
- [ ] Valid unchecked
- [] Malformed - no space inside brackets
- [  ] Malformed - double space
-[ ] Malformed - no space after dash
"""
        total, completed = count_checkboxes(markdown)
        # Only the two valid checkboxes should be counted
        assert total == 2
        assert completed == 1


@pytest.mark.unit
class TestImplementWorkflow:
    """Tests for ImplementWorkflow class."""

    def test_implement_workflow_init_returns_empty_list(self, workflow_context):
        """Test that init() returns an empty list.

        ImplementWorkflow uses execute() instead of init() for its custom loop logic,
        so init() should return an empty list.
        """
        workflow = ImplementWorkflow()
        prompts = workflow.init(workflow_context)

        assert isinstance(prompts, list)
        assert len(prompts) == 0

    def test_get_pr_for_issue_closes_keyword(self):
        """Test that _get_pr_for_issue finds PR with 'closes #N' keyword."""
        import json
        from unittest.mock import MagicMock, patch

        workflow = ImplementWorkflow()
        mock_result = MagicMock()
        mock_result.stdout = json.dumps(
            [{"number": 42, "body": "This PR closes #123\n\nSome description"}]
        )

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = workflow._get_pr_for_issue("github.com/owner/repo", 123)

        assert result is not None
        assert result["number"] == 42
        mock_run.assert_called_once()

    def test_get_pr_for_issue_fixes_keyword(self):
        """Test that _get_pr_for_issue finds PR with 'fixes #N' keyword."""
        import json
        from unittest.mock import MagicMock, patch

        workflow = ImplementWorkflow()
        mock_result = MagicMock()
        mock_result.stdout = json.dumps([{"number": 55, "body": "Fixes #99 - bug fix"}])

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = workflow._get_pr_for_issue("github.com/owner/repo", 99)

        assert result is not None
        assert result["number"] == 55
        mock_run.assert_called_once()

    def test_get_pr_for_issue_resolves_keyword(self):
        """Test that _get_pr_for_issue finds PR with 'resolves #N' keyword."""
        import json
        from unittest.mock import MagicMock, patch

        workflow = ImplementWorkflow()
        mock_result = MagicMock()
        mock_result.stdout = json.dumps([{"number": 77, "body": "RESOLVES #200 in uppercase"}])

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = workflow._get_pr_for_issue("github.com/owner/repo", 200)

        assert result is not None
        assert result["number"] == 77
        mock_run.assert_called_once()

    def test_get_pr_for_issue_no_matching_pr(self):
        """Test that _get_pr_for_issue returns None when no PR matches."""
        import json
        from unittest.mock import MagicMock, patch

        workflow = ImplementWorkflow()
        mock_result = MagicMock()
        # PR exists but doesn't link to the issue we're looking for
        mock_result.stdout = json.dumps([{"number": 42, "body": "Closes #999 - different issue"}])

        with patch("subprocess.run", return_value=mock_result):
            result = workflow._get_pr_for_issue("github.com/owner/repo", 123)

        assert result is None

    def test_get_pr_for_issue_subprocess_failure(self):
        """Test that _get_pr_for_issue returns None on subprocess failure."""
        import subprocess
        from unittest.mock import patch

        workflow = ImplementWorkflow()

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                returncode=1, cmd=["gh"], stderr="error"
            )
            result = workflow._get_pr_for_issue("github.com/owner/repo", 123)

        assert result is None

    def test_get_pr_for_issue_json_parse_error(self):
        """Test that _get_pr_for_issue returns None on JSON parse error."""
        from unittest.mock import MagicMock, patch

        workflow = ImplementWorkflow()
        mock_result = MagicMock()
        mock_result.stdout = "not valid json"

        with patch("subprocess.run", return_value=mock_result):
            result = workflow._get_pr_for_issue("github.com/owner/repo", 123)

        assert result is None

    def test_get_pr_for_issue_empty_list_response(self):
        """Test that _get_pr_for_issue returns None for empty PR list."""
        from unittest.mock import MagicMock, patch

        workflow = ImplementWorkflow()
        mock_result = MagicMock()
        mock_result.stdout = "[]"

        with patch("subprocess.run", return_value=mock_result):
            result = workflow._get_pr_for_issue("github.com/owner/repo", 123)

        assert result is None

    def test_mark_pr_ready_success(self):
        """Test that _mark_pr_ready calls gh pr ready with correct arguments."""
        from unittest.mock import MagicMock, patch

        workflow = ImplementWorkflow()
        mock_result = MagicMock()

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            workflow._mark_pr_ready("github.com/owner/repo", 42)

        mock_run.assert_called_once_with(
            ["gh", "pr", "ready", "42", "--repo", "https://github.com/owner/repo"],
            capture_output=True,
            text=True,
            check=True,
        )

    def test_mark_pr_ready_failure_logs_warning_no_raise(self):
        """Test that _mark_pr_ready logs warning on failure but doesn't raise."""
        import subprocess
        from unittest.mock import patch

        workflow = ImplementWorkflow()

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                returncode=1, cmd=["gh"], stderr="PR is already ready"
            )
            # Should not raise - just logs a warning
            workflow._mark_pr_ready("github.com/owner/repo", 42)

    def test_run_prompt_uses_stage_model_from_config(self, workflow_context):
        """Test that _run_prompt selects model from config.stage_models for the stage."""
        from unittest.mock import MagicMock, patch

        from src.config import Config

        workflow = ImplementWorkflow()

        # Create a mock config with specific stage_models
        mock_config = MagicMock(spec=Config)
        mock_config.stage_models = {
            "implement": "sonnet",
            "prepare_implementation": "haiku",
            "Implement": "opus",  # Fallback
        }
        mock_config.claude_code_enable_telemetry = False

        with patch("src.workflows.implement.run_claude") as mock_run_claude:
            workflow._run_prompt(
                prompt="/kiln-implement_github for issue",
                ctx=workflow_context,
                config=mock_config,
                stage_name="implement",
            )

            mock_run_claude.assert_called_once()
            call_kwargs = mock_run_claude.call_args
            # Model should be "sonnet" from stage_models["implement"]
            assert call_kwargs.kwargs["model"] == "sonnet"

    def test_run_prompt_falls_back_to_implement_model(self, workflow_context):
        """Test that _run_prompt falls back to 'Implement' model when stage not in config."""
        from unittest.mock import MagicMock, patch

        from src.config import Config

        workflow = ImplementWorkflow()

        # Create a mock config without the specific stage
        mock_config = MagicMock(spec=Config)
        mock_config.stage_models = {
            "Implement": "opus",  # Only the fallback is defined
        }
        mock_config.claude_code_enable_telemetry = False

        with patch("src.workflows.implement.run_claude") as mock_run_claude:
            workflow._run_prompt(
                prompt="/kiln-implement_github for issue",
                ctx=workflow_context,
                config=mock_config,
                stage_name="unknown_stage",  # Not in stage_models
            )

            mock_run_claude.assert_called_once()
            call_kwargs = mock_run_claude.call_args
            # Model should fall back to "opus" from stage_models["Implement"]
            assert call_kwargs.kwargs["model"] == "opus"

    def test_execute_creates_pr_when_none_exists(self, workflow_context):
        """Test that execute() calls /prepare_implementation_github when no PR exists."""
        from unittest.mock import MagicMock, patch

        from src.config import Config

        workflow = ImplementWorkflow()

        # Mock config
        mock_config = MagicMock(spec=Config)
        mock_config.stage_models = {"prepare_implementation": "sonnet", "implement": "sonnet"}
        mock_config.claude_code_enable_telemetry = False
        mock_config.safety_allow_appended_tasks = 0

        # First call: no PR found
        # Second call: PR found after prepare_implementation_github
        pr_responses = [
            None,  # Initial check - no PR
            {
                "number": 42,
                "body": "Closes #42\n\n## TASK 1: Test\n- [x] Done",
            },  # After prepare
            {
                "number": 42,
                "body": "Closes #42\n\n## TASK 1: Test\n- [x] Done",
            },  # In loop (check state)
        ]
        call_count = {"value": 0}

        def mock_get_pr_create(*_args, **_kwargs):
            result = pr_responses[min(call_count["value"], len(pr_responses) - 1)]
            call_count["value"] += 1
            return result

        with (
            patch.object(workflow, "_get_pr_for_issue", side_effect=mock_get_pr_create),
            patch.object(workflow, "_run_prompt") as mock_run,
        ):
            workflow.execute(workflow_context, mock_config)

        # Verify prepare_implementation was called
        prepare_calls = [c for c in mock_run.call_args_list if "/kiln-prepare_implementation_github" in c[0][0]]
        assert len(prepare_calls) == 1

    def test_execute_fails_after_two_pr_creation_attempts(self, workflow_context):
        """Test that execute() raises RuntimeError after 2 failed PR creation attempts."""
        from unittest.mock import MagicMock, patch

        from src.config import Config

        workflow = ImplementWorkflow()

        # Mock config
        mock_config = MagicMock(spec=Config)
        mock_config.stage_models = {"prepare_implementation": "sonnet"}
        mock_config.claude_code_enable_telemetry = False

        # Always return None (no PR found)
        with (
            patch.object(workflow, "_get_pr_for_issue", return_value=None),
            patch.object(workflow, "_run_prompt") as mock_run,
            pytest.raises(RuntimeError, match="Failed to create PR.*after 2 attempts"),
        ):
            workflow.execute(workflow_context, mock_config)

        # Verify prepare_implementation was called twice
        assert mock_run.call_count == 2

    def test_execute_max_iterations_based_on_task_count(self, workflow_context):
        """Test that execute() sets max_iterations based on TASK count in PR body.

        With no progress made, stall detection raises ImplementationIncompleteError.
        """
        from unittest.mock import MagicMock, patch

        from src.config import Config
        from src.workflows.implement import ImplementationIncompleteError

        workflow = ImplementWorkflow()

        mock_config = MagicMock(spec=Config)
        mock_config.stage_models = {"implement": "sonnet"}
        mock_config.claude_code_enable_telemetry = False
        mock_config.safety_allow_appended_tasks = 0

        # PR with 3 TASKs and always-incomplete checkboxes
        pr_info = {
            "number": 42,
            "body": """Closes #42

## TASK 1: First task
- [ ] Subtask 1

## TASK 2: Second task
- [ ] Subtask 2

## TASK 3: Third task
- [ ] Subtask 3
""",
        }

        iterations_run = {"count": 0}

        def mock_run_prompt(*args, **kwargs):
            iterations_run["count"] += 1

        with (
            patch.object(workflow, "_get_pr_for_issue", return_value=pr_info),
            patch.object(workflow, "_run_prompt", side_effect=mock_run_prompt),
            pytest.raises(ImplementationIncompleteError) as exc_info,
        ):
            workflow.execute(workflow_context, mock_config)

        # With 3 TASKs, loop continues indefinitely until stall detection kicks in
        # Iteration 1: 0/3 complete, last_completed=-1, no stall (stall_count stays 0), run prompt, last_completed=0
        # Iteration 2: 0/3 complete, last_completed=0, stall_count=1, run prompt
        # Iteration 3: 0/3 complete, last_completed=0, stall_count=2 (>=MAX_STALL_COUNT), raises exception BEFORE running
        # So 2 iterations run (stall detected on iteration 3 before running)
        assert iterations_run["count"] == 2
        assert exc_info.value.reason == "stall"

    def test_execute_stall_detection(self, workflow_context):
        """Test that execute() raises ImplementationIncompleteError after MAX_STALL_COUNT iterations with no progress."""
        from unittest.mock import MagicMock, patch

        from src.config import Config
        from src.workflows.implement import (
            MAX_STALL_COUNT,
            ImplementationIncompleteError,
        )

        workflow = ImplementWorkflow()

        mock_config = MagicMock(spec=Config)
        mock_config.stage_models = {"implement": "sonnet"}
        mock_config.claude_code_enable_telemetry = False
        mock_config.safety_allow_appended_tasks = 0

        # PR with 5 TASKs that never makes progress after first task
        pr_info = {
            "number": 42,
            "body": """Closes #42

## TASK 1: Test 1
- [x] Done task

## TASK 2: Test 2
- [ ] Pending task 1

## TASK 3: Test 3
- [ ] Pending task 2

## TASK 4: Test 4
- [ ] Pending task 3

## TASK 5: Test 5
- [ ] Pending task 4
""",
        }

        iterations_run = {"count": 0}

        def mock_run_prompt(*_args, **_kwargs):
            iterations_run["count"] += 1

        with (
            patch.object(workflow, "_get_pr_for_issue", return_value=pr_info),
            patch.object(workflow, "_run_prompt", side_effect=mock_run_prompt),
            pytest.raises(ImplementationIncompleteError) as exc_info,
        ):
            workflow.execute(workflow_context, mock_config)

        # Loop continues indefinitely until stall detection:
        # Iteration 1: completed=1, last_completed=-1, no stall (stall_count stays 0), run prompt, last_completed=1
        # Iteration 2: completed=1, last_completed=1, stall_count=1, run prompt
        # Iteration 3: completed=1, last_completed=1, stall_count=2 (>=MAX_STALL_COUNT), raises exception BEFORE running
        # So MAX_STALL_COUNT iterations run (stall detected on iteration 3 before running)
        assert iterations_run["count"] == MAX_STALL_COUNT
        assert exc_info.value.reason == "stall"

    def test_execute_completion_detection(self, workflow_context):
        """Test that execute() exits and marks PR ready when all checkboxes complete."""
        from unittest.mock import MagicMock, patch

        from src.config import Config

        workflow = ImplementWorkflow()

        mock_config = MagicMock(spec=Config)
        mock_config.stage_models = {"implement": "sonnet"}
        mock_config.claude_code_enable_telemetry = False
        mock_config.safety_allow_appended_tasks = 0

        # PR with 2 TASKs, starts incomplete, then becomes complete after 1 implementation
        pr_responses = [
            {
                "number": 42,
                "body": "Closes #42\n\n## TASK 1: Test 1\n- [ ] Task 1\n\n## TASK 2: Test 2\n- [ ] Task 2",
            },  # Initial check
            {
                "number": 42,
                "body": "Closes #42\n\n## TASK 1: Test 1\n- [ ] Task 1\n\n## TASK 2: Test 2\n- [ ] Task 2",
            },  # Loop iteration 1: get PR state
            {
                "number": 42,
                "body": "Closes #42\n\n## TASK 1: Test 1\n- [x] Task 1\n\n## TASK 2: Test 2\n- [x] Task 2",
            },  # Loop iteration 2: all complete
            {
                "number": 42,
                "body": "Closes #42\n\n## TASK 1: Test 1\n- [x] Task 1\n\n## TASK 2: Test 2\n- [x] Task 2",
            },  # Final check
        ]
        call_count = {"value": 0}

        def mock_get_pr_completion(*_args, **_kwargs):
            result = pr_responses[min(call_count["value"], len(pr_responses) - 1)]
            call_count["value"] += 1
            return result

        with (
            patch.object(workflow, "_get_pr_for_issue", side_effect=mock_get_pr_completion),
            patch.object(workflow, "_run_prompt") as mock_run,
            patch.object(workflow, "_mark_pr_ready") as mock_ready,
        ):
            workflow.execute(workflow_context, mock_config)

        # Implementation should run once, then completion detected on second check
        assert mock_run.call_count == 1
        # PR should be marked ready
        mock_ready.assert_called_once_with(workflow_context.repo, 42)

    def test_execute_pr_disappearance_raises_error(self, workflow_context):
        """Test that execute() raises RuntimeError if PR disappears during execution."""
        from unittest.mock import MagicMock, patch

        from src.config import Config

        workflow = ImplementWorkflow()

        mock_config = MagicMock(spec=Config)
        mock_config.stage_models = {"implement": "sonnet"}
        mock_config.claude_code_enable_telemetry = False
        mock_config.safety_allow_appended_tasks = 0

        # PR exists initially with 2 TASKs, then disappears in loop
        pr_responses = [
            {
                "number": 42,
                "body": "Closes #42\n\n## TASK 1: Test 1\n- [ ] Task 1\n\n## TASK 2: Test 2\n- [ ] Task 2",
            },  # Initial check
            None,  # Disappeared in loop
        ]
        call_count = {"value": 0}

        def mock_get_pr_disappear(*_args, **_kwargs):
            result = pr_responses[min(call_count["value"], len(pr_responses) - 1)]
            call_count["value"] += 1
            return result

        with (
            patch.object(workflow, "_get_pr_for_issue", side_effect=mock_get_pr_disappear),
            patch.object(workflow, "_run_prompt"),
            pytest.raises(RuntimeError, match="PR disappeared"),
        ):
            workflow.execute(workflow_context, mock_config)

    def test_execute_no_tasks_raises_error(self, workflow_context):
        """Test that execute() raises ImplementationIncompleteError when no checkbox tasks found."""
        from unittest.mock import MagicMock, patch

        from src.config import Config
        from src.workflows.implement import ImplementationIncompleteError

        workflow = ImplementWorkflow()

        mock_config = MagicMock(spec=Config)
        mock_config.stage_models = {"implement": "sonnet"}
        mock_config.claude_code_enable_telemetry = False
        mock_config.safety_allow_appended_tasks = 0

        # PR with no checkbox tasks
        pr_info = {
            "number": 42,
            "body": """Closes #42

## TASK 1: Test task
This task has no checkboxes.

Some other content here.
""",
        }

        with (
            patch.object(workflow, "_get_pr_for_issue", return_value=pr_info),
            patch.object(workflow, "_run_prompt"),
            pytest.raises(ImplementationIncompleteError) as exc_info,
        ):
            workflow.execute(workflow_context, mock_config)

        assert exc_info.value.reason == "no_tasks"
        assert "No checkbox tasks found" in str(exc_info.value)

    def test_execute_stall_raises_error(self, workflow_context):
        """Test that execute() raises ImplementationIncompleteError when no progress made.

        With the current implementation, stall detection (reason="stall") triggers before
        max_iterations check when no progress is made, since MAX_STALL_COUNT=2 is reached first.
        """
        from unittest.mock import MagicMock, patch

        from src.config import Config
        from src.workflows.implement import ImplementationIncompleteError

        workflow = ImplementWorkflow()

        mock_config = MagicMock(spec=Config)
        mock_config.stage_models = {"implement": "sonnet"}
        mock_config.claude_code_enable_telemetry = False
        mock_config.safety_allow_appended_tasks = 0

        # PR with 1 TASK that never makes progress
        pr_info = {
            "number": 42,
            "body": "Closes #42\n\n## TASK 1: Test\n- [ ] Task 1",
        }

        with (
            patch.object(workflow, "_get_pr_for_issue", return_value=pr_info),
            patch.object(workflow, "_run_prompt"),
            pytest.raises(ImplementationIncompleteError) as exc_info,
        ):
            workflow.execute(workflow_context, mock_config)

        assert exc_info.value.reason == "stall"
        assert "No progress" in str(exc_info.value)

    def test_execute_continues_past_max_iterations_when_progress_made(self, workflow_context):
        """Test that execute() continues past max_iterations when progress is made."""
        from unittest.mock import MagicMock, patch

        from src.config import Config

        workflow = ImplementWorkflow()

        mock_config = MagicMock(spec=Config)
        mock_config.stage_models = {"implement": "sonnet"}
        mock_config.claude_code_enable_telemetry = False
        mock_config.safety_allow_appended_tasks = 0  # No limit

        # PR with 2 TASKs, progress made on each iteration, completes on iteration 4
        # This tests that the loop continues past max_iterations=2 when progress is made
        # Call sequence: initial check, iter1 check, iter2 check, iter3 check, iter4 check, final check
        pr_responses = [
            {
                "number": 42,
                "body": "Closes #42\n\n## TASK 1\n- [ ] A\n- [ ] B\n\n## TASK 2\n- [ ] C\n- [ ] D",
            },  # Initial check: 0/4
            {
                "number": 42,
                "body": "Closes #42\n\n## TASK 1\n- [ ] A\n- [ ] B\n\n## TASK 2\n- [ ] C\n- [ ] D",
            },  # Iter 1 check: 0/4 -> run prompt
            {
                "number": 42,
                "body": "Closes #42\n\n## TASK 1\n- [x] A\n- [ ] B\n\n## TASK 2\n- [ ] C\n- [ ] D",
            },  # Iter 2 check: 1/4 -> run prompt
            {
                "number": 42,
                "body": "Closes #42\n\n## TASK 1\n- [x] A\n- [x] B\n\n## TASK 2\n- [ ] C\n- [ ] D",
            },  # Iter 3 check: 2/4 -> run prompt
            {
                "number": 42,
                "body": "Closes #42\n\n## TASK 1\n- [x] A\n- [x] B\n\n## TASK 2\n- [x] C\n- [x] D",
            },  # Iter 4 check: 4/4 complete -> exit
            {
                "number": 42,
                "body": "Closes #42\n\n## TASK 1\n- [x] A\n- [x] B\n\n## TASK 2\n- [x] C\n- [x] D",
            },  # Final check
        ]
        call_count = {"value": 0}

        def mock_get_pr(*_args, **_kwargs):
            result = pr_responses[min(call_count["value"], len(pr_responses) - 1)]
            call_count["value"] += 1
            return result

        with (
            patch.object(workflow, "_get_pr_for_issue", side_effect=mock_get_pr),
            patch.object(workflow, "_run_prompt") as mock_run,
            patch.object(workflow, "_mark_pr_ready") as mock_ready,
        ):
            workflow.execute(workflow_context, mock_config)

        # With 2 TASKs, max_iterations_estimate=2, but loop should continue to iteration 3
        # because progress is being made each iteration (checked at iteration 4 it's complete)
        # Iter 1: 0/4 -> run, Iter 2: 1/4 -> run, Iter 3: 2/4 -> run, Iter 4: 4/4 -> done
        assert mock_run.call_count == 3
        mock_ready.assert_called_once()

    def test_execute_stall_detection_with_overrun(self, workflow_context):
        """Test stall detection after continuing past max_iterations (Scenario 1).

        Scenario: PR has 3 TASKs, 2 completed, 1 never completes.
        The loop should continue past max_iterations=3 but eventually stall and raise exception.
        """
        from unittest.mock import MagicMock, patch

        from src.config import Config
        from src.workflows.implement import (
            MAX_STALL_COUNT,
            ImplementationIncompleteError,
        )

        workflow = ImplementWorkflow()

        mock_config = MagicMock(spec=Config)
        mock_config.stage_models = {"implement": "sonnet"}
        mock_config.claude_code_enable_telemetry = False
        mock_config.safety_allow_appended_tasks = 0  # No limit

        # PR with 3 TASKs, 2 completed, 1 never completes (stays at 2/3)
        pr_info = {
            "number": 42,
            "body": """Closes #42

## TASK 1: Test 1
- [x] Done

## TASK 2: Test 2
- [x] Done

## TASK 3: Test 3
- [ ] Never completes
""",
        }

        iterations_run = {"count": 0}

        def mock_run_prompt(*_args, **_kwargs):
            iterations_run["count"] += 1

        with (
            patch.object(workflow, "_get_pr_for_issue", return_value=pr_info),
            patch.object(workflow, "_run_prompt", side_effect=mock_run_prompt),
            pytest.raises(ImplementationIncompleteError) as exc_info,
        ):
            workflow.execute(workflow_context, mock_config)

        # Iteration 1: 2/3 complete, last_completed=-1, no stall (progress!), run prompt, last=2
        # Iteration 2: 2/3 complete, last_completed=2, stall_count=1, run prompt
        # Iteration 3: 2/3 complete, last_completed=2, stall_count=2 (>=MAX_STALL_COUNT), raises exception BEFORE running
        # So MAX_STALL_COUNT iterations run
        assert iterations_run["count"] == MAX_STALL_COUNT
        assert exc_info.value.reason == "stall"

    def test_execute_successful_overrun(self, workflow_context):
        """Test successful completion after continuing past max_iterations (Scenario 2).

        Scenario: PR has 3 TASKs, completes on iteration 4 (past max_iterations=3).
        """
        from unittest.mock import MagicMock, patch

        from src.config import Config

        workflow = ImplementWorkflow()

        mock_config = MagicMock(spec=Config)
        mock_config.stage_models = {"implement": "sonnet"}
        mock_config.claude_code_enable_telemetry = False
        mock_config.safety_allow_appended_tasks = 0  # No limit

        # PR with 3 TASKs, completes on iteration 4 (past max_iterations=3)
        # Call sequence: initial, iter1, iter2, iter3, iter4 (detects completion), final
        pr_responses = [
            {
                "number": 42,
                "body": "Closes #42\n\n## TASK 1\n- [ ] A\n\n## TASK 2\n- [ ] B\n\n## TASK 3\n- [ ] C",
            },  # Initial: 0/3
            {
                "number": 42,
                "body": "Closes #42\n\n## TASK 1\n- [ ] A\n\n## TASK 2\n- [ ] B\n\n## TASK 3\n- [ ] C",
            },  # Iter 1: 0/3 -> run prompt
            {
                "number": 42,
                "body": "Closes #42\n\n## TASK 1\n- [x] A\n\n## TASK 2\n- [ ] B\n\n## TASK 3\n- [ ] C",
            },  # Iter 2: 1/3 -> run prompt
            {
                "number": 42,
                "body": "Closes #42\n\n## TASK 1\n- [x] A\n\n## TASK 2\n- [x] B\n\n## TASK 3\n- [ ] C",
            },  # Iter 3: 2/3 -> run prompt (past max_iterations=3)
            {
                "number": 42,
                "body": "Closes #42\n\n## TASK 1\n- [x] A\n\n## TASK 2\n- [x] B\n\n## TASK 3\n- [x] C",
            },  # Iter 4: 3/3 complete -> exit
            {
                "number": 42,
                "body": "Closes #42\n\n## TASK 1\n- [x] A\n\n## TASK 2\n- [x] B\n\n## TASK 3\n- [x] C",
            },  # Final check
        ]
        call_count = {"value": 0}

        def mock_get_pr(*_args, **_kwargs):
            result = pr_responses[min(call_count["value"], len(pr_responses) - 1)]
            call_count["value"] += 1
            return result

        with (
            patch.object(workflow, "_get_pr_for_issue", side_effect=mock_get_pr),
            patch.object(workflow, "_run_prompt") as mock_run,
            patch.object(workflow, "_mark_pr_ready") as mock_ready,
        ):
            workflow.execute(workflow_context, mock_config)

        # Should run 3 iterations, then detect completion on iteration 4
        # This proves we continued past max_iterations=3
        assert mock_run.call_count == 3
        mock_ready.assert_called_once()

    def test_execute_task_growth_within_limit(self, workflow_context):
        """Test that loop continues when appended TASKs are within safety limit."""
        from unittest.mock import MagicMock, patch

        from src.config import Config

        workflow = ImplementWorkflow()

        mock_config = MagicMock(spec=Config)
        mock_config.stage_models = {"implement": "sonnet"}
        mock_config.claude_code_enable_telemetry = False
        mock_config.safety_allow_appended_tasks = 2  # Allow up to 2 appended TASKs

        # Start with 2 TASKs, add 1 more (within limit of 2)
        # Call sequence: initial, iter1, iter2, iter3 (detects completion), final
        pr_responses = [
            {
                "number": 42,
                "body": "Closes #42\n\n## TASK 1\n- [ ] A\n\n## TASK 2\n- [ ] B",
            },  # Initial: 2 TASKs, 0/2
            {
                "number": 42,
                "body": "Closes #42\n\n## TASK 1\n- [ ] A\n\n## TASK 2\n- [ ] B",
            },  # Iter 1: 2 TASKs, 0/2 -> run prompt
            {
                "number": 42,
                "body": "Closes #42\n\n## TASK 1\n- [x] A\n\n## TASK 2\n- [ ] B\n\n## TASK 3\n- [ ] C",
            },  # Iter 2: 3 TASKs (+1, within limit), 1/3 -> run prompt
            {
                "number": 42,
                "body": "Closes #42\n\n## TASK 1\n- [x] A\n\n## TASK 2\n- [x] B\n\n## TASK 3\n- [x] C",
            },  # Iter 3: 3/3 complete -> exit
            {
                "number": 42,
                "body": "Closes #42\n\n## TASK 1\n- [x] A\n\n## TASK 2\n- [x] B\n\n## TASK 3\n- [x] C",
            },  # Final check
        ]
        call_count = {"value": 0}

        def mock_get_pr(*_args, **_kwargs):
            result = pr_responses[min(call_count["value"], len(pr_responses) - 1)]
            call_count["value"] += 1
            return result

        with (
            patch.object(workflow, "_get_pr_for_issue", side_effect=mock_get_pr),
            patch.object(workflow, "_run_prompt") as mock_run,
            patch.object(workflow, "_mark_pr_ready") as mock_ready,
        ):
            workflow.execute(workflow_context, mock_config)

        # Should run 2 iterations (1 appended TASK is within limit of 2)
        # Then detect completion on iteration 3
        assert mock_run.call_count == 2
        mock_ready.assert_called_once()

    def test_execute_task_growth_exceeds_limit(self, workflow_context):
        """Test that loop exits when appended TASKs exceed safety limit."""
        from unittest.mock import MagicMock, patch

        from src.config import Config

        workflow = ImplementWorkflow()

        mock_config = MagicMock(spec=Config)
        mock_config.stage_models = {"implement": "sonnet"}
        mock_config.claude_code_enable_telemetry = False
        mock_config.safety_allow_appended_tasks = 2  # Allow max 2 appended TASKs

        # Start with 3 TASKs, then add 3 more (exceeds limit of 2)
        pr_responses = [
            {
                "number": 42,
                "body": "Closes #42\n\n## TASK 1\n- [ ] A\n\n## TASK 2\n- [ ] B\n\n## TASK 3\n- [ ] C",
            },  # Initial: 3 TASKs
            {
                "number": 42,
                "body": "Closes #42\n\n## TASK 1\n- [ ] A\n\n## TASK 2\n- [ ] B\n\n## TASK 3\n- [ ] C",
            },  # Iter 1: 3 TASKs
            {
                "number": 42,
                "body": "Closes #42\n\n## TASK 1\n- [x] A\n\n## TASK 2\n- [ ] B\n\n## TASK 3\n- [ ] C\n\n## TASK 4\n- [ ] D\n\n## TASK 5\n- [ ] E\n\n## TASK 6\n- [ ] F",
            },  # Iter 2: 6 TASKs (+3, exceeds limit)
        ]
        call_count = {"value": 0}

        def mock_get_pr(*_args, **_kwargs):
            result = pr_responses[min(call_count["value"], len(pr_responses) - 1)]
            call_count["value"] += 1
            return result

        with (
            patch.object(workflow, "_get_pr_for_issue", side_effect=mock_get_pr),
            patch.object(workflow, "_run_prompt") as mock_run,
            patch.object(workflow, "_mark_pr_ready") as mock_ready,
        ):
            workflow.execute(workflow_context, mock_config)

        # Should run only 1 iteration, then exit on iteration 2 due to safety limit
        assert mock_run.call_count == 1
        # PR should NOT be marked ready (incomplete due to safety exit)
        mock_ready.assert_not_called()

    def test_execute_passes_base_flag_when_parent_branch_set(self, workflow_context):
        """Test that execute() passes --base flag to /prepare_implementation_github when parent_branch is set."""
        from unittest.mock import MagicMock, patch

        from src.config import Config

        workflow = ImplementWorkflow()

        # Mock config
        mock_config = MagicMock(spec=Config)
        mock_config.stage_models = {"prepare_implementation": "sonnet", "implement": "sonnet"}
        mock_config.claude_code_enable_telemetry = False
        mock_config.safety_allow_appended_tasks = 0

        # Create context with parent_branch set
        ctx_with_parent = WorkflowContext(
            repo="github.com/owner/test-repo",
            issue_number=42,
            issue_title="Test Issue",
            workspace_path="/tmp/workspaces/test",
            parent_branch="feature/parent-branch",
        )

        # First call: no PR found
        # Second call: PR found after prepare_implementation_github
        pr_responses = [
            None,  # Initial check - no PR
            {
                "number": 42,
                "body": "Closes #42\n\n## TASK 1: Test\n- [x] Done",
            },  # After prepare
            {
                "number": 42,
                "body": "Closes #42\n\n## TASK 1: Test\n- [x] Done",
            },  # In loop (check state)
        ]
        call_count = {"value": 0}

        def mock_get_pr_create(*_args, **_kwargs):
            result = pr_responses[min(call_count["value"], len(pr_responses) - 1)]
            call_count["value"] += 1
            return result

        with (
            patch.object(workflow, "_get_pr_for_issue", side_effect=mock_get_pr_create),
            patch.object(workflow, "_run_prompt") as mock_run,
        ):
            workflow.execute(ctx_with_parent, mock_config)

        # Verify prepare_implementation was called with --base flag
        prepare_calls = [c for c in mock_run.call_args_list if "/kiln-prepare_implementation_github" in c[0][0]]
        assert len(prepare_calls) == 1
        prepare_prompt = prepare_calls[0][0][0]
        assert "--base feature/parent-branch" in prepare_prompt

    def test_execute_no_base_flag_when_parent_branch_not_set(self, workflow_context):
        """Test that execute() does NOT pass --base flag when parent_branch is not set."""
        from unittest.mock import MagicMock, patch

        from src.config import Config

        workflow = ImplementWorkflow()

        # Mock config
        mock_config = MagicMock(spec=Config)
        mock_config.stage_models = {"prepare_implementation": "sonnet", "implement": "sonnet"}
        mock_config.claude_code_enable_telemetry = False
        mock_config.safety_allow_appended_tasks = 0

        # workflow_context fixture does NOT have parent_branch set

        # First call: no PR found
        # Second call: PR found after prepare_implementation_github
        pr_responses = [
            None,  # Initial check - no PR
            {
                "number": 42,
                "body": "Closes #42\n\n## TASK 1: Test\n- [x] Done",
            },  # After prepare
            {
                "number": 42,
                "body": "Closes #42\n\n## TASK 1: Test\n- [x] Done",
            },  # In loop (check state)
        ]
        call_count = {"value": 0}

        def mock_get_pr_create(*_args, **_kwargs):
            result = pr_responses[min(call_count["value"], len(pr_responses) - 1)]
            call_count["value"] += 1
            return result

        with (
            patch.object(workflow, "_get_pr_for_issue", side_effect=mock_get_pr_create),
            patch.object(workflow, "_run_prompt") as mock_run,
        ):
            workflow.execute(workflow_context, mock_config)

        # Verify prepare_implementation was called without --base flag
        prepare_calls = [c for c in mock_run.call_args_list if "/kiln-prepare_implementation_github" in c[0][0]]
        assert len(prepare_calls) == 1
        prepare_prompt = prepare_calls[0][0][0]
        assert "--base" not in prepare_prompt
