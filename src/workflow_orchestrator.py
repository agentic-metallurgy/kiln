"""Workflow orchestration for the daemon.

This module provides the WorkflowOrchestrator class that manages workflow execution
for issues on the project board. It handles:
- Determining when workflows should be triggered
- Running workflow stages (Research, Plan, Implement)
- Managing workflow state via labels
- Auto-preparing worktrees for new issues
- Handling YOLO mode auto-progression after workflow completion
"""

import json as json_module
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from src.daemon_utils import get_hostname_from_url, get_worktree_path
from src.labels import Labels
from src.logger import (
    MaskingFilter,
    RunLogger,
    _extract_org_from_url,
    clear_issue_context,
    get_logger,
    set_issue_context,
)
from src.security import ActorCategory, check_actor_allowed
from src.workflows import (
    ImplementWorkflow,
    PlanWorkflow,
    PrepareWorkflow,
    ResearchWorkflow,
    WorkflowContext,
)
from src.workflows.implement import ImplementationIncompleteError
from src.workspace import WorkspaceError

logger = get_logger(__name__)


class WorkflowOrchestrator:
    """Orchestrates workflow execution for issues.

    This class handles the lifecycle of workflow execution:
    - Checking if workflows should be triggered based on labels and status
    - Running workflows with proper state tracking (labels, database records)
    - Auto-preparing worktrees before workflow execution
    - Handling YOLO mode auto-progression after completion
    """

    # Map status names to workflow classes
    # Note: PrepareWorkflow runs automatically before other workflows if no worktree exists
    WORKFLOW_MAP = {
        "Research": ResearchWorkflow,
        "Plan": PlanWorkflow,
        "Implement": ImplementWorkflow,
    }

    # Workflow configuration with labels for state tracking
    # Labels act as "soft locks" to prevent duplicate runs and track completion
    WORKFLOW_CONFIG = {
        "Research": {
            "workflow": ResearchWorkflow,
            "running_label": Labels.RESEARCHING,
            "complete_label": Labels.RESEARCH_READY,
            "next_status": None,  # Human decides when to advance
        },
        "Plan": {
            "workflow": PlanWorkflow,
            "running_label": Labels.PLANNING,
            "complete_label": Labels.PLAN_READY,
            "next_status": None,  # Human decides when to advance
        },
        "Implement": {
            "workflow": ImplementWorkflow,
            "running_label": Labels.IMPLEMENTING,
            "complete_label": None,  # Moves to Validate instead
            "next_status": "Validate",
        },
    }

    # YOLO mode auto-progression: maps current status to next status
    # When YOLO label is present, workflow completion advances to next status
    YOLO_PROGRESSION = {
        "Backlog": "Research",
        "Research": "Plan",
        "Plan": "Implement",
        # Implement → Validate is handled by existing WORKFLOW_CONFIG.next_status
    }

    def __init__(
        self,
        ticket_client,
        database,
        runner,
        workspace_manager,
        config,
        yolo_controller,
        in_progress: dict[str, float],
        in_progress_lock: threading.Lock,
        running_labels: dict[str, str],
        running_labels_lock: threading.Lock,
    ) -> None:
        """Initialize workflow orchestrator.

        Args:
            ticket_client: GitHub ticket client for API operations
            database: Database for issue state and run records
            runner: WorkflowRunner for executing workflows
            workspace_manager: Workspace manager for worktree operations
            config: Application configuration
            yolo_controller: YoloController for YOLO label checks
            in_progress: Dict tracking in-progress workflows (key -> start timestamp)
            in_progress_lock: Lock for thread-safe access to in_progress
            running_labels: Dict tracking issues with running workflow labels
            running_labels_lock: Lock for thread-safe access to running_labels
        """
        self.ticket_client = ticket_client
        self.database = database
        self.runner = runner
        self.workspace_manager = workspace_manager
        self.config = config
        self.yolo_controller = yolo_controller
        self.in_progress = in_progress
        self.in_progress_lock = in_progress_lock
        self.running_labels = running_labels
        self.running_labels_lock = running_labels_lock
        logger.debug(
            f"WorkflowOrchestrator initialized (workspace_dir={config.workspace_dir})"
        )

    def should_trigger_workflow(self, item) -> bool:
        """Check if an item needs a workflow triggered.

        Uses labels as the sole source of truth for workflow state:
        - running_label: Indicates workflow is currently running
        - complete_label: Indicates workflow has finished

        Args:
            item: TicketItem from GitHub (with cached labels from enriched query)

        Returns:
            True if workflow should be triggered
        """
        # Skip closed issues entirely
        if item.state == "CLOSED":
            return False

        # Only process items in watched statuses
        if item.status not in self.config.watched_statuses:
            return False

        # Check if we have a workflow for this status
        if item.status not in self.WORKFLOW_MAP:
            return False

        # Skip if workflow already running for this item (in-memory lock)
        key = f"{item.repo}#{item.ticket_id}"
        with self.in_progress_lock:
            if key in self.in_progress:
                logger.debug(
                    f"Skipping {key} - workflow in progress since {self.in_progress[key]}"
                )
                return False

        # For label-tracked workflows (Research, Plan, Implement)
        config = self.WORKFLOW_CONFIG.get(item.status)
        if not config:
            return False

        running_label = config["running_label"]
        complete_label = config["complete_label"]

        # Skip if already running (has running_label) - use cached labels
        if running_label in item.labels:
            logger.debug(f"Skipping {key} - has '{running_label}' label (workflow running)")
            return False

        # Skip if already complete (has complete_label)
        if complete_label and complete_label in item.labels:
            logger.debug(f"Skipping {key} - has '{complete_label}' label (workflow complete)")
            return False

        # Skip if implementation failed (requires manual intervention)
        if Labels.IMPLEMENTATION_FAILED in item.labels:
            logger.debug(f"Skipping {key} - has '{Labels.IMPLEMENTATION_FAILED}' label")
            return False

        # Skip if research previously failed (requires manual intervention)
        if item.status == "Research" and Labels.RESEARCH_FAILED in item.labels:
            logger.debug(f"Skipping {key} - has '{Labels.RESEARCH_FAILED}' label")
            return False

        # Check actor authorization if supported by the client
        if self.ticket_client.supports_status_actor_check:
            actor = self.ticket_client.get_last_status_actor(item.repo, item.ticket_id)
            actor_category = check_actor_allowed(
                actor, self.config.username_self, key, "", self.config.team_usernames
            )
            if actor_category != ActorCategory.SELF:
                return False
            logger.info(f"Workflow trigger: {key} in '{item.status}' by allowed user '{actor}'")
        else:
            # GHES 3.14 doesn't support project status timeline events
            # Log the limitation and allow the workflow to proceed
            logger.warning(
                f"Workflow trigger: {key} in '{item.status}' - "
                f"actor check unavailable ({self.ticket_client.client_description})"
            )
            logger.warning(
                "  Security note: Cannot verify who changed status. "
                "Ensure only authorized users have project write access."
            )
        return True

    def get_pr_for_issue(self, repo: str, issue_number: int) -> dict | None:
        """Get the open PR that closes a specific issue.

        Args:
            repo: Repository in 'hostname/owner/repo' format
            issue_number: Issue number

        Returns:
            Dict with PR info (number, body) or None if no PR found
        """
        try:
            # Extract owner/repo from hostname/owner/repo format
            parts = repo.split("/", 1)
            if len(parts) == 2:
                hostname, owner_repo = parts
                repo_arg = owner_repo if hostname == "github.com" else f"{hostname}/{owner_repo}"
            else:
                repo_arg = repo

            result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "list",
                    "--repo",
                    repo_arg,
                    "--state",
                    "open",
                    "--search",
                    f"closes #{issue_number}",
                    "--json",
                    "number,body",
                    "--jq",
                    ".[0]",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            if result.stdout.strip():
                return json_module.loads(result.stdout)
        except Exception as e:
            logger.warning(f"Failed to get PR for issue #{issue_number}: {e}")
        return None

    def get_parent_pr_info(self, repo: str, ticket_id: int) -> tuple[int | None, str | None]:
        """Get parent issue number and its open PR branch name.

        Combines get_parent_issue and get_pr_for_issue to find the parent's
        open PR branch that child issues should branch from.

        Args:
            repo: Repository in 'hostname/owner/repo' format
            ticket_id: Issue number to check for parent

        Returns:
            Tuple of (parent_issue_number, parent_branch_name).
            Both are None if no parent or no open PR for parent.
        """
        # Check if this issue has a parent
        parent_issue_number = self.ticket_client.get_parent_issue(repo, ticket_id)
        if parent_issue_number is None:
            logger.debug(f"Issue #{ticket_id} has no parent")
            return None, None

        logger.info(f"Issue #{ticket_id} has parent issue #{parent_issue_number}")

        # Find the parent's open PR
        parent_pr = self.ticket_client.get_pr_for_issue(repo, parent_issue_number)
        if parent_pr is None:
            logger.info(f"Parent issue #{parent_issue_number} has no open PR")
            return parent_issue_number, None

        parent_branch = str(parent_pr.get("branch_name")) if parent_pr.get("branch_name") else None
        logger.info(f"Found parent PR #{parent_pr.get('number')} with branch '{parent_branch}'")
        return parent_issue_number, parent_branch

    def auto_prepare_worktree(self, item) -> None:
        """Create worktree for an issue using PrepareWorkflow.

        This runs the prepare workflow to create the worktree automatically
        when an issue enters Research/Plan/Implement without an existing worktree.

        Pre-fetches the issue body so PrepareWorkflow can include it directly
        in the prompt without requiring Claude to make an API call.

        Also checks if the issue has a parent with an open PR, and if so,
        passes the parent branch information so the child issue branches
        from the parent's PR branch instead of main.

        Args:
            item: TicketItem to prepare worktree for
        """
        # Pre-fetch issue body for PrepareWorkflow
        issue_body = self.ticket_client.get_ticket_body(item.repo, item.ticket_id)

        # Check for parent issue with open PR
        parent_issue_number, parent_branch = self.get_parent_pr_info(item.repo, item.ticket_id)

        workflow = PrepareWorkflow()
        # Use absolute path so Claude knows exactly where to create things
        abs_workspace_path = str(Path(self.config.workspace_dir).resolve())
        ctx = WorkflowContext(
            repo=item.repo,
            issue_number=item.ticket_id,
            issue_title=item.title,
            workspace_path=abs_workspace_path,  # Prepare runs in workspace root
            project_url=item.board_url,
            issue_body=issue_body,
            username_self=self.config.username_self,
            parent_issue_number=parent_issue_number,
            parent_branch=parent_branch,
        )
        self.runner.run(workflow, ctx, "Prepare")

        if parent_branch:
            logger.info(f"Auto-prepared worktree (branching from parent branch '{parent_branch}')")
        else:
            logger.info("Auto-prepared worktree")

    def run_workflow(
        self,
        workflow_name: str,
        item,
    ) -> str | None:
        """Run a workflow for a project item.

        Args:
            workflow_name: Name of the workflow status (e.g., "Research", "Plan")
            item: TicketItem to process

        Returns:
            The Claude session ID from the workflow, or None if not available.
        """
        logger.debug(f"Running workflow '{workflow_name}'")

        # Get workflow class
        workflow_class = self.WORKFLOW_MAP.get(workflow_name)
        if not workflow_class:
            logger.error(f"No workflow class found for '{workflow_name}'")
            return

        # Create workflow instance
        workflow = workflow_class()

        # Determine workspace path based on workflow
        workspace_path = get_worktree_path(self.config.workspace_dir, item.repo, item.ticket_id)

        # Rebase on first Research run (no research_ready label yet) - use cached labels
        if workflow_name == "Research":
            research_complete_label = self.WORKFLOW_CONFIG["Research"]["complete_label"]
            if research_complete_label not in item.labels:
                logger.info("Rebasing worktree from origin/main (first Research run)")
                if not self.workspace_manager.rebase_from_main(workspace_path):
                    raise WorkspaceError(
                        f"Rebase failed due to conflicts. Resolve manually in {workspace_path}"
                    )

        logger.debug(f"Workflow cwd: {workspace_path}")

        # Main workflows always start fresh sessions
        # (Comment processing resumes sessions for applying user feedback)
        resume_session = None
        logger.info(f"Starting fresh {workflow_name} session")

        # Create context
        ctx = WorkflowContext(
            repo=item.repo,
            issue_number=item.ticket_id,
            issue_title=item.title,
            workspace_path=workspace_path,
            project_url=item.board_url,
            username_self=self.config.username_self,
        )

        # Run workflow
        try:
            # ImplementWorkflow has its own execute() method with internal loop
            if workflow_name == "Implement" and hasattr(workflow, "execute"):
                workflow.execute(ctx, self.config)
                session_id = None  # No session resumption for implement workflow
            else:
                session_id = self.runner.run(workflow, ctx, workflow_name, resume_session)
            logger.info(f"Successfully completed workflow '{workflow_name}'")

            # Store the session ID for future resumption (must be a proper string)
            if session_id and isinstance(session_id, str):
                self.database.set_workflow_session_id(
                    item.repo, item.ticket_id, workflow_name, session_id
                )
                logger.info(
                    f"Saved {workflow_name} session for future resumption: {session_id[:8]}..."
                )

            return session_id
        except ImplementationIncompleteError as e:
            logger.warning(
                f"Implementation incomplete for {workflow_name}: {e} (reason: {e.reason})"
            )
            if workflow_name == "Implement":
                self.ticket_client.add_label(
                    item.repo, item.ticket_id, Labels.IMPLEMENTATION_FAILED
                )
                logger.info(
                    f"Added '{Labels.IMPLEMENTATION_FAILED}' label to "
                    f"{item.repo}#{item.ticket_id} (reason: {e.reason})"
                )
            raise
        except Exception as e:
            logger.error(f"Workflow '{workflow_name}' failed: {e}", exc_info=True)
            # Add failure label for Implement workflow
            if workflow_name == "Implement":
                self.ticket_client.add_label(
                    item.repo, item.ticket_id, Labels.IMPLEMENTATION_FAILED
                )
                logger.info(
                    f"Added '{Labels.IMPLEMENTATION_FAILED}' label to {item.repo}#{item.ticket_id}"
                )
            raise

    def process_item_workflow(self, item) -> None:
        """Process an item that needs a workflow (runs in thread).

        Uses labels to track workflow state:
        - Adds running_label before starting
        - On success: removes running_label, adds complete_label (or moves status)
        - On failure: removes running_label, stays in current state

        Auto-prepares worktree if it doesn't exist before running the workflow.

        Also creates per-run log files and database records for tracking run history.

        Args:
            item: TicketItem to process
        """
        key = f"{item.repo}#{item.ticket_id}"

        # Mark as in-progress (in-memory)
        with self.in_progress_lock:
            self.in_progress[key] = time.time()

        # Set logging context for this workflow thread
        set_issue_context(item.repo, item.ticket_id)

        # Get workflow config for label management
        config = self.WORKFLOW_CONFIG.get(item.status)
        running_label = config["running_label"] if config else None
        complete_label = config["complete_label"] if config else None
        next_status = config["next_status"] if config else None

        # Initialize run tracking variables
        run_id: int | None = None
        run_logger: RunLogger | None = None

        try:
            # Ensure issue state exists before workflow runs (needed for session ID storage)
            self.database.update_issue_state(
                item.repo, item.ticket_id, item.status, project_url=item.board_url
            )

            # Auto-prepare: Create worktree if it doesn't exist (for any workflow)
            worktree_path = get_worktree_path(self.config.workspace_dir, item.repo, item.ticket_id)
            if not Path(worktree_path).exists():
                logger.info("Auto-preparing worktree")
                # Add preparing label during worktree creation
                self.ticket_client.add_label(item.repo, item.ticket_id, Labels.PREPARING)
                try:
                    self.auto_prepare_worktree(item)
                finally:
                    # Remove preparing label after worktree created
                    self.ticket_client.remove_label(item.repo, item.ticket_id, Labels.PREPARING)

            # Add running label before starting workflow (soft lock)
            if running_label:
                self.ticket_client.add_label(item.repo, item.ticket_id, running_label)
                # Track for cleanup on shutdown
                with self.running_labels_lock:
                    self.running_labels[key] = running_label
                logger.debug(f"Added '{running_label}' label to {key}")

            # Create masking filter if configured
            masking_filter: MaskingFilter | None = None
            if self.config.ghes_logs_mask and self.config.github_enterprise_host:
                org_name = (
                    _extract_org_from_url(self.config.project_urls[0])
                    if self.config.project_urls
                    else None
                )
                masking_filter = MaskingFilter(self.config.github_enterprise_host, org_name)

            # Import here to avoid circular imports
            from src.database import RunRecord

            # Create RunRecord at workflow start
            run_record = RunRecord(
                repo=item.repo,
                issue_number=item.ticket_id,
                workflow=item.status,
                started_at=datetime.now(),
            )

            # Create RunLogger for per-run logging
            run_logger = RunLogger(
                repo=item.repo,
                issue_number=item.ticket_id,
                workflow=item.status,
                base_log_dir=".kiln/logs",
                masking_filter=masking_filter,
            )

            # Enter RunLogger context and run workflow
            with run_logger:
                # Set log_path on record now that RunLogger has generated it
                run_record.log_path = run_logger.log_path

                # Insert run record into database
                run_id = self.database.insert_run_record(run_record)
                logger.debug(f"Created run record {run_id} for {key}")

                # Run the workflow
                session_id = self.run_workflow(item.status, item)

                # Workflow completed successfully - update run record
                self.database.update_run_record(
                    run_id,
                    completed_at=datetime.now(),
                    outcome="success",
                    session_id=session_id,
                )

                # Pass session_id to RunLogger and write session file
                if session_id:
                    run_logger.set_session_id(session_id)
                    run_logger.write_session_file()
                    logger.debug(f"Wrote session file for run {run_id}")

            # Workflow completed successfully
            # Remove running label
            if running_label:
                self.ticket_client.remove_label(item.repo, item.ticket_id, running_label)
                # Remove from cleanup tracking
                with self.running_labels_lock:
                    self.running_labels.pop(key, None)
                logger.debug(f"Removed '{running_label}' label from {key}")

            # Validate research block exists after Research workflow
            if item.status == "Research":
                body = self.ticket_client.get_ticket_body(item.repo, item.ticket_id)
                if body is None or "<!-- kiln:research -->" not in body:
                    self.ticket_client.add_label(item.repo, item.ticket_id, Labels.RESEARCH_FAILED)
                    logger.warning(f"Research completed but no research block found for {key}")
                    # Update run record to reflect stalled state
                    if run_id:
                        self.database.update_run_record(run_id, outcome="stalled")
                    # Don't add research_ready, don't advance YOLO
                    return

            # Add complete label or move to next status
            if complete_label:
                self.ticket_client.add_label(item.repo, item.ticket_id, complete_label)
                logger.debug(f"Added '{complete_label}' label to {key}")

            # Check if Implement workflow completed all tasks
            if item.status == "Implement" and next_status:
                from src.workflows.implement import count_checkboxes

                pr_info = self.get_pr_for_issue(item.repo, item.ticket_id)
                if pr_info:
                    pr_body = pr_info.get("body", "")
                    total_tasks, completed_tasks = count_checkboxes(pr_body)
                    if total_tasks > 0 and completed_tasks == total_tasks:
                        hostname = get_hostname_from_url(item.board_url)
                        self.ticket_client.update_item_status(
                            item.item_id, next_status, hostname=hostname
                        )
                        logger.info(
                            f"All {total_tasks} tasks complete, moved {key} to '{next_status}'"
                        )
                        next_status = None  # Prevent duplicate move below

            if next_status:
                hostname = get_hostname_from_url(item.board_url)
                self.ticket_client.update_item_status(item.item_id, next_status, hostname=hostname)
                logger.info(f"Moved {key} to '{next_status}' status")

            # YOLO mode: auto-advance to next workflow status
            # Re-check yolo label to handle removal during workflow execution
            if Labels.YOLO in item.labels and not next_status:
                yolo_next = self.YOLO_PROGRESSION.get(item.status)
                if yolo_next:
                    # Fresh check - yolo may have been removed while workflow was running
                    if self.yolo_controller.has_yolo_label(item.repo, item.ticket_id):
                        hostname = get_hostname_from_url(item.board_url)
                        self.ticket_client.update_item_status(
                            item.item_id, yolo_next, hostname=hostname
                        )
                        logger.info(
                            f"YOLO: Auto-advanced {key} from '{item.status}' to '{yolo_next}'"
                        )
                    else:
                        logger.info(
                            f"YOLO: Cancelled auto-advance for {key}, label removed during workflow"
                        )

            # After workflow completes, update last_processed_comment timestamp to skip
            # any comments posted during the workflow (prevents daemon from treating
            # its own research/plan posts as user feedback)
            latest_comments = self.ticket_client.get_comments(item.repo, item.ticket_id)
            latest_comment_timestamp = (
                latest_comments[-1].created_at.isoformat() if latest_comments else None
            )

            # Save state after successful workflow completion
            self.database.update_issue_state(
                item.repo,
                item.ticket_id,
                item.status,
                project_url=item.board_url,
                last_processed_comment_timestamp=latest_comment_timestamp,
            )

        except Exception as e:
            logger.error(f"Error in workflow: {e}", exc_info=True)

            # Update run record with failure outcome
            if run_id:
                self.database.update_run_record(
                    run_id,
                    completed_at=datetime.now(),
                    outcome="failed",
                )

            # On failure: remove running label (workflow is no longer running)
            if running_label:
                try:
                    self.ticket_client.remove_label(item.repo, item.ticket_id, running_label)
                    # Remove from cleanup tracking
                    with self.running_labels_lock:
                        self.running_labels.pop(key, None)
                    logger.debug(f"Removed '{running_label}' label from {key} after failure")
                except Exception as label_err:
                    logger.warning(f"Could not remove running label after failure: {label_err}")

            # YOLO mode failure: remove yolo label, add yolo_failed
            # Fetch fresh labels to detect if YOLO was removed during workflow
            if Labels.YOLO in item.labels:
                try:
                    fresh_labels = self.ticket_client.get_ticket_labels(item.repo, item.ticket_id)
                    if Labels.YOLO in fresh_labels:
                        self.ticket_client.remove_label(item.repo, item.ticket_id, Labels.YOLO)
                        self.ticket_client.add_label(item.repo, item.ticket_id, Labels.YOLO_FAILED)
                        logger.warning(
                            f"YOLO: Workflow failed for {key}, cancelled auto-progression"
                        )
                    else:
                        # YOLO label was removed during workflow, skip failure handling
                        logger.info(
                            f"YOLO: Skipped failure handling for {key}, label removed during workflow"
                        )
                except Exception as yolo_err:
                    logger.warning(f"Could not update YOLO labels after failure: {yolo_err}")

            raise

        finally:
            # Always remove from in-progress tracking
            with self.in_progress_lock:
                self.in_progress.pop(key, None)
            # Clear logging context
            clear_issue_context()
