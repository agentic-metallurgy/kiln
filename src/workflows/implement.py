"""Implementation workflow for executing the implementation plan."""

import json
import re
import subprocess
from typing import TYPE_CHECKING

from src.claude_runner import run_claude
from src.logger import get_logger, log_message
from src.workflows.base import WorkflowContext

if TYPE_CHECKING:
    from src.config import Config

logger = get_logger(__name__)

# Constants for the implementation loop
DEFAULT_MAX_ITERATIONS = 8  # Fallback if no TASKs detected
MAX_STALL_COUNT = 2  # Stop after 2 iterations with no progress


def count_tasks(markdown_text: str) -> int:
    """Count the number of TASK blocks in markdown text.

    Looks for patterns like:
    - ## TASK 1: Description
    - ### TASK 2: Description
    - **TASK 3**: Description

    Args:
        markdown_text: Markdown content to parse

    Returns:
        Number of TASK blocks found
    """
    # Match TASK headers in various formats
    task_pattern = re.compile(r"^#+\s*TASK\s+\d+|^\*\*TASK\s+\d+\*\*", re.MULTILINE | re.IGNORECASE)
    return len(task_pattern.findall(markdown_text))


def count_checkboxes(markdown_text: str) -> tuple[int, int]:
    """Count total and completed checkboxes in markdown text.

    Args:
        markdown_text: Markdown content to parse

    Returns:
        Tuple of (total_tasks, completed_tasks)
    """
    checked = len(re.findall(r"- \[x\]", markdown_text, re.IGNORECASE))
    unchecked = len(re.findall(r"- \[ \]", markdown_text))
    return checked + unchecked, checked


class ImplementWorkflow:
    """Workflow for implementing the planned changes.

    This workflow:
    1. Creates a draft PR if one doesn't exist (via /prepare_implementation_github)
    2. Loops through tasks, implementing one per iteration (via /implement_github)
    3. Stops when all tasks complete, max iterations hit, or no progress detected
    """

    @property
    def name(self) -> str:
        """Return workflow name."""
        return "implement"

    def init(self, ctx: WorkflowContext) -> list[str]:
        """Return empty list - this workflow uses execute() instead.

        The init() method is required by the Workflow protocol but ImplementWorkflow
        uses execute() for its custom loop logic.
        """
        return []

    def execute(self, ctx: WorkflowContext, config: "Config") -> None:
        """Execute the implementation workflow with internal loop.

        Args:
            ctx: WorkflowContext with issue and repository information
            config: Application configuration for model selection
        """
        issue_url = f"https://{ctx.repo}/issues/{ctx.issue_number}"
        key = f"{ctx.repo}#{ctx.issue_number}"

        logger.info(f"ImplementWorkflow.execute() starting for {key}")

        # Build common prompt parts
        reviewer_flags = ""
        if ctx.allowed_username:
            reviewer_flags = f" --reviewer {ctx.allowed_username}"

        project_url_context = ""
        if ctx.project_url:
            project_url_context = f" Project URL: {ctx.project_url}"

        # Step 1: Ensure PR exists (with retry)
        pr_info = self._get_pr_for_issue(ctx.repo, ctx.issue_number)
        logger.info(f"PR lookup for {key}: {'found PR #' + str(pr_info.get('number')) if pr_info else 'not found'}")

        if not pr_info:
            for attempt in range(1, 3):  # Try up to 2 times
                logger.info(
                    f"No PR found for {key}, creating via /prepare_implementation_github "
                    f"(attempt {attempt}/2)"
                )
                prepare_prompt = f"/prepare_implementation_github {issue_url}"
                self._run_prompt(prepare_prompt, ctx, config, "prepare_implementation")

                # Check for PR
                pr_info = self._get_pr_for_issue(ctx.repo, ctx.issue_number)
                if pr_info:
                    logger.info(f"PR created for {key}: #{pr_info['number']}")
                    break

            if not pr_info:
                # Failed after 2 attempts - this will be caught by daemon to add failed label
                raise RuntimeError(
                    f"Failed to create PR for {key} after 2 attempts. "
                    "Check /prepare_implementation_github output."
                )

        # Step 2: Implementation loop
        # Set max iterations based on TASK count (each TASK = 1 iteration)
        pr_body = pr_info.get("body", "")
        num_tasks = count_tasks(pr_body)
        max_iterations = num_tasks if num_tasks > 0 else DEFAULT_MAX_ITERATIONS
        logger.info(f"Detected {num_tasks} TASKs for {key}, max_iterations={max_iterations}")

        iteration = 0
        last_completed = -1
        stall_count = 0

        while iteration < max_iterations:
            iteration += 1

            # Get current PR state
            pr_info = self._get_pr_for_issue(ctx.repo, ctx.issue_number)
            if not pr_info:
                raise RuntimeError(f"PR disappeared for {key}")

            pr_body = pr_info.get("body", "")
            total_tasks, completed_tasks = count_checkboxes(pr_body)

            if total_tasks == 0:
                logger.warning(f"No checkbox tasks found in PR for {key}")
                break

            # Check if all tasks complete
            if completed_tasks == total_tasks:
                logger.info(f"All {total_tasks} tasks complete for {key}")
                break

            # Check for stall (no progress)
            if completed_tasks == last_completed:
                stall_count += 1
                if stall_count >= MAX_STALL_COUNT:
                    logger.warning(
                        f"No progress after {MAX_STALL_COUNT} iterations for {key} "
                        f"(stuck at {completed_tasks}/{total_tasks})"
                    )
                    break
            else:
                stall_count = 0

            last_completed = completed_tasks

            logger.info(
                f"Implement iteration {iteration} for {key} "
                f"({completed_tasks}/{total_tasks} tasks complete)"
            )

            # Run implementation for one task
            implement_prompt = (
                f"/implement_github for issue {issue_url}.{reviewer_flags}{project_url_context}"
            )
            self._run_prompt(implement_prompt, ctx, config, "implement")

        if iteration >= max_iterations:
            logger.warning(f"Hit max iterations ({max_iterations}) for {key}")

        # Check final state and mark PR ready if all tasks complete
        pr_info = self._get_pr_for_issue(ctx.repo, ctx.issue_number)
        if pr_info:
            pr_body = pr_info.get("body", "")
            total_tasks, completed_tasks = count_checkboxes(pr_body)
            pr_number = pr_info.get("number")
            if total_tasks > 0 and completed_tasks == total_tasks and pr_number:
                self._mark_pr_ready(ctx.repo, pr_number)

    def _mark_pr_ready(self, repo: str, pr_number: int) -> None:
        """Mark a draft PR as ready for review.

        Args:
            repo: Repository in 'hostname/owner/repo' format
            pr_number: PR number
        """
        try:
            repo_ref = f"https://{repo}"
            cmd = ["gh", "pr", "ready", str(pr_number), "--repo", repo_ref]
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.info(f"Marked PR #{pr_number} as ready for review")
        except subprocess.CalledProcessError as e:
            logger.warning(f"Failed to mark PR #{pr_number} as ready: {e.stderr}")

    def _run_prompt(
        self,
        prompt: str,
        ctx: WorkflowContext,
        config: "Config",
        stage_name: str,
    ) -> None:
        """Run a single prompt through Claude.

        Args:
            prompt: The prompt to execute
            ctx: WorkflowContext with workspace path
            config: Application configuration
            stage_name: Stage name for model selection and logging
        """
        model = config.stage_models.get(stage_name) or config.stage_models.get("Implement")
        issue_context = f"{ctx.repo}#{ctx.issue_number}"

        logger.info(f"Running prompt (model={model}, workspace={ctx.workspace_path})")
        log_message(logger, "Prompt", prompt)

        run_claude(
            prompt,
            ctx.workspace_path,
            model=model,
            issue_context=issue_context,
            enable_telemetry=config.claude_code_enable_telemetry,
            execution_stage=stage_name,
        )

        logger.info(f"Prompt completed: {stage_name}")

    def _get_pr_for_issue(self, repo: str, issue_number: int) -> dict | None:
        """Get the open PR that closes a specific issue.

        Args:
            repo: Repository in 'hostname/owner/repo' format
            issue_number: Issue number

        Returns:
            Dict with PR info (number, body) or None if no PR found
        """
        try:
            # Build repo reference URL
            repo_ref = f"https://{repo}"

            # Use gh CLI to find PRs - search is loose, so we filter in Python
            cmd = [
                "gh",
                "pr",
                "list",
                "--repo",
                repo_ref,
                "--state",
                "open",
                "--search",
                f"closes #{issue_number}",
                "--json",
                "number,body",
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            output = result.stdout.strip()

            if not output or output == "[]":
                return None

            prs = json.loads(output)

            # Filter for PRs that actually link to this issue
            # GitHub linking keywords: closes, fixes, resolves (case-insensitive)
            link_pattern = re.compile(
                rf"\b(closes|fixes|resolves)\s+#?{issue_number}\b", re.IGNORECASE
            )

            for pr in prs:
                body = pr.get("body", "") or ""
                if link_pattern.search(body):
                    logger.debug(f"Found PR #{pr['number']} linking to issue #{issue_number}")
                    return pr

            return None

        except subprocess.CalledProcessError as e:
            logger.warning(f"Failed to get PR for issue #{issue_number}: {e.stderr}")
            return None
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse PR response: {e}")
            return None

