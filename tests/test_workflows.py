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

    def test_workflow_context_attributes_are_accessible(self, workflow_context):
        """Test that all WorkflowContext attributes are accessible."""
        assert hasattr(workflow_context, "repo")
        assert hasattr(workflow_context, "issue_number")
        assert hasattr(workflow_context, "issue_title")
        assert hasattr(workflow_context, "workspace_path")

    def test_workflow_context_issue_body_optional(self):
        """Test that issue_body is optional and defaults to None."""
        ctx = WorkflowContext(
            repo="owner/repo",
            issue_number=42,
            issue_title="Test",
            workspace_path="/tmp/workspace",
        )
        assert ctx.issue_body is None

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

    def test_workflow_context_allowed_username_optional(self):
        """Test that allowed_username is optional and defaults to None."""
        ctx = WorkflowContext(
            repo="owner/repo",
            issue_number=42,
            issue_title="Test",
            workspace_path="/tmp/workspace",
        )
        assert ctx.allowed_username is None

    def test_workflow_context_allowed_username_can_be_set(self):
        """Test that allowed_username can be set during creation."""
        ctx = WorkflowContext(
            repo="owner/repo",
            issue_number=42,
            issue_title="Test",
            workspace_path="/tmp/workspace",
            allowed_username="user1",
        )
        assert ctx.allowed_username == "user1"


@pytest.mark.unit
class TestResearchWorkflow:
    """Tests for ResearchWorkflow."""

    def test_research_workflow_name(self):
        """Test that ResearchWorkflow has the correct name."""
        workflow = ResearchWorkflow()
        assert workflow.name == "research"

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

        assert "/research_codebase_github" in prompts[0]


@pytest.mark.unit
class TestPlanWorkflow:
    """Tests for PlanWorkflow."""

    def test_plan_workflow_name(self):
        """Test that PlanWorkflow has the correct name."""
        workflow = PlanWorkflow()
        assert workflow.name == "plan"

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

        assert "/create_plan" in prompts[0]


@pytest.mark.unit
class TestProcessCommentsWorkflow:
    """Tests for ProcessCommentsWorkflow."""

    def test_process_comments_workflow_name(self):
        """Test that workflow has correct name."""
        workflow = ProcessCommentsWorkflow()
        assert workflow.name == "process_comments"

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

    def test_prepare_workflow_name(self):
        """Test that PrepareWorkflow has the correct name."""
        workflow = PrepareWorkflow()
        assert workflow.name == "prepare"

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