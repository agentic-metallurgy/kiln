"""Unit tests for the workflows module."""

import pytest

from src.workflows.base import WorkflowContext
from src.workflows.implement import ImplementWorkflow
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

    def test_workflow_context_parent_issue_number_optional(self):
        """Test that parent_issue_number is optional and defaults to None."""
        ctx = WorkflowContext(
            repo="owner/repo",
            issue_number=42,
            issue_title="Test",
            workspace_path="/tmp/workspace",
        )
        assert ctx.parent_issue_number is None

    def test_workflow_context_parent_issue_number_can_be_set(self):
        """Test that parent_issue_number can be set during creation."""
        ctx = WorkflowContext(
            repo="owner/repo",
            issue_number=42,
            issue_title="Test",
            workspace_path="/tmp/workspace",
            parent_issue_number=10,
        )
        assert ctx.parent_issue_number == 10

    def test_workflow_context_parent_branch_optional(self):
        """Test that parent_branch is optional and defaults to None."""
        ctx = WorkflowContext(
            repo="owner/repo",
            issue_number=42,
            issue_title="Test",
            workspace_path="/tmp/workspace",
        )
        assert ctx.parent_branch is None

    def test_workflow_context_parent_branch_can_be_set(self):
        """Test that parent_branch can be set during creation."""
        ctx = WorkflowContext(
            repo="owner/repo",
            issue_number=42,
            issue_title="Test",
            workspace_path="/tmp/workspace",
            parent_branch="10-feature-branch",
        )
        assert ctx.parent_branch == "10-feature-branch"


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
class TestImplementWorkflow:
    """Tests for ImplementWorkflow."""

    def test_implement_workflow_name(self):
        """Test that ImplementWorkflow has the correct name."""
        workflow = ImplementWorkflow()
        assert workflow.name == "implement"

    def test_implement_workflow_init_returns_list(self, workflow_context):
        """Test that init() returns a list of prompts."""
        workflow = ImplementWorkflow()
        prompts = workflow.init(workflow_context)

        assert isinstance(prompts, list)
        assert len(prompts) > 0
        assert all(isinstance(prompt, str) for prompt in prompts)

    def test_implement_workflow_init_returns_one_prompt(self, workflow_context):
        """Test that ImplementWorkflow returns exactly 1 prompt."""
        workflow = ImplementWorkflow()
        prompts = workflow.init(workflow_context)

        assert len(prompts) == 1

    def test_implement_workflow_prompts_contain_issue_number(self, workflow_context):
        """Test that prompts contain the issue number in URL format."""
        workflow = ImplementWorkflow()
        prompts = workflow.init(workflow_context)

        assert str(workflow_context.issue_number) in prompts[0]
        # Issue number appears in URL format: /issues/42
        assert f"/issues/{workflow_context.issue_number}" in prompts[0]

    def test_implement_workflow_prompts_contain_repo(self, workflow_context):
        """Test that prompts contain the repository name."""
        workflow = ImplementWorkflow()
        prompts = workflow.init(workflow_context)

        assert workflow_context.repo in prompts[0]

    def test_implement_workflow_prompt_uses_slash_command(self, workflow_context):
        """Test that the prompt uses the /implement_github slash command."""
        workflow = ImplementWorkflow()
        prompts = workflow.init(workflow_context)

        # The prompt invokes the implement_github command
        assert "/implement_github" in prompts[0]

    def test_implement_workflow_prompt_includes_issue_url(self, workflow_context):
        """Test that the prompt includes the full issue URL."""
        workflow = ImplementWorkflow()
        prompts = workflow.init(workflow_context)

        assert "https://github.com/owner/test-repo/issues/42" in prompts[0]

    def test_implement_workflow_prompt_includes_reviewer(self):
        """Test that prompts include reviewer flag when allowed_username is set."""
        ctx = WorkflowContext(
            repo="github.com/owner/test-repo",
            issue_number=42,
            issue_title="Test Issue",
            workspace_path="/tmp/workspace",
            allowed_username="alice",
        )
        workflow = ImplementWorkflow()
        prompts = workflow.init(ctx)

        assert "--reviewer alice" in prompts[0]

    def test_implement_workflow_prompt_no_reviewer_when_none(self):
        """Test that no reviewer flag when allowed_username is None."""
        ctx = WorkflowContext(
            repo="github.com/owner/test-repo",
            issue_number=42,
            issue_title="Test Issue",
            workspace_path="/tmp/workspace",
            allowed_username=None,
        )
        workflow = ImplementWorkflow()
        prompts = workflow.init(ctx)

        assert "--reviewer" not in prompts[0]

    def test_implement_workflow_prompt_no_reviewer_when_empty(self):
        """Test that no reviewer flag when allowed_username is empty string."""
        ctx = WorkflowContext(
            repo="github.com/owner/test-repo",
            issue_number=42,
            issue_title="Test Issue",
            workspace_path="/tmp/workspace",
            allowed_username="",
        )
        workflow = ImplementWorkflow()
        prompts = workflow.init(ctx)

        assert "--reviewer" not in prompts[0]

    def test_implement_workflow_prompt_includes_parent_branch(self):
        """Test that prompts include parent branch info when set."""
        ctx = WorkflowContext(
            repo="github.com/owner/test-repo",
            issue_number=42,
            issue_title="Test Issue",
            workspace_path="/tmp/workspace",
            parent_issue_number=10,
            parent_branch="10-parent-feature",
        )
        workflow = ImplementWorkflow()
        prompts = workflow.init(ctx)

        assert "Parent branch: 10-parent-feature" in prompts[0]
        assert "PR should target this branch" in prompts[0]

    def test_implement_workflow_prompt_no_parent_branch_when_none(self):
        """Test that no parent branch info when not set."""
        ctx = WorkflowContext(
            repo="github.com/owner/test-repo",
            issue_number=42,
            issue_title="Test Issue",
            workspace_path="/tmp/workspace",
            parent_issue_number=None,
            parent_branch=None,
        )
        workflow = ImplementWorkflow()
        prompts = workflow.init(ctx)

        assert "Parent branch:" not in prompts[0]


@pytest.mark.unit
class TestWorkflowIntegration:
    """Integration tests for workflow behavior."""

    def test_all_workflows_use_same_context_type(self, workflow_context):
        """Test that all workflows accept the same WorkflowContext type."""
        research = ResearchWorkflow()
        plan = PlanWorkflow()
        implement = ImplementWorkflow()

        # All should accept the same context without error
        research_prompts = research.init(workflow_context)
        plan_prompts = plan.init(workflow_context)
        implement_prompts = implement.init(workflow_context)

        assert isinstance(research_prompts, list)
        assert isinstance(plan_prompts, list)
        assert isinstance(implement_prompts, list)

    def test_workflows_have_unique_names(self):
        """Test that all workflows have unique names."""
        research = ResearchWorkflow()
        plan = PlanWorkflow()
        implement = ImplementWorkflow()

        names = {research.name, plan.name, implement.name}
        assert len(names) == 3
        assert "research" in names
        assert "plan" in names
        assert "implement" in names

    def test_context_values_appear_in_workflow_prompts(self, workflow_context):
        """Test that context values are properly interpolated in workflows."""
        # Plan and Implement workflows use repo
        plan = PlanWorkflow()
        implement = ImplementWorkflow()

        for workflow in [plan, implement]:
            prompts = workflow.init(workflow_context)
            all_prompts_text = " ".join(prompts)
            assert str(workflow_context.issue_number) in all_prompts_text
            assert workflow_context.repo in all_prompts_text

        # Research workflow uses issue number
        research = ResearchWorkflow()
        prompts = research.init(workflow_context)
        all_prompts_text = " ".join(prompts)
        assert str(workflow_context.issue_number) in all_prompts_text

    def test_workflows_return_non_empty_prompts(self, workflow_context):
        """Test that all workflows return non-empty prompt strings."""
        workflows = [ResearchWorkflow(), PlanWorkflow(), ImplementWorkflow()]

        for workflow in workflows:
            prompts = workflow.init(workflow_context)

            for prompt in prompts:
                assert prompt.strip() != ""
                assert len(prompt) > 20  # Prompts should be substantial

    def test_workflow_context_with_special_characters(self):
        """Test that workflows handle special characters in context values."""
        ctx = WorkflowContext(
            repo="owner/repo-with-dashes",
            issue_number=999,
            issue_title='Issue with "quotes" and special chars: <>&',
            workspace_path="/tmp/workspace/path-with-dashes_and_underscores",
        )

        workflows = [ResearchWorkflow(), PlanWorkflow(), ImplementWorkflow()]

        for workflow in workflows:
            prompts = workflow.init(ctx)
            # Should not raise any errors
            assert len(prompts) > 0
            all_text = " ".join(prompts)
            assert str(ctx.issue_number) in all_text


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
        assert "/tmp/workspaces/repo" in prompts[0]

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

        assert "issue #123" in prompts[1]

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

        assert "/home/user/workspaces/myrepo-issue-99" in prompts[1]

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

    def test_prepare_workflow_with_parent_branch(self):
        """Test that prompt includes parent branch info when set."""
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

        # Should reference parent branch
        assert "Base branch: '10-parent-feature'" in prompts[1]
        assert "child of issue #10" in prompts[1]
        assert "instead of main" in prompts[1]

    def test_prepare_workflow_without_parent_uses_main(self):
        """Test that prompt uses main branch when no parent."""
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

        # Should use main branch
        assert "Base branch: 'main'" in prompts[1]
        # Should NOT mention parent
        assert "child of issue" not in prompts[1]

    def test_prepare_workflow_parent_without_pr_falls_back_to_main(self):
        """Test that parent without PR branch still defaults to main."""
        ctx = WorkflowContext(
            repo="github.com/owner/repo",
            issue_number=42,
            issue_title="Child Issue",
            workspace_path="/tmp/workspaces",
            issue_body="Child issue body",
            parent_issue_number=10,
            parent_branch=None,  # Parent has no open PR
        )
        workflow = PrepareWorkflow()
        prompts = workflow.init(ctx)

        # Should use main branch since parent has no PR
        assert "Base branch: 'main'" in prompts[1]
        # Should NOT mention branching from parent
        assert "child of issue" not in prompts[1]
