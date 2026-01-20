"""Main daemon/poller module for agentic-metallurgy.

This module provides the orchestrator that ties together all components:
- Polls GitHub project boards for changes
- Manages workspace creation and cleanup
- Triggers appropriate workflows based on status changes
- Runs Claude workflows with proper error handling
"""

import re
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from tenacity import wait_exponential

from src.claude_runner import run_claude
from src.comment_processor import CommentProcessor
from src.config import Config, load_config
from src.database import Database, ProjectMetadata
from src.interfaces import TicketItem
from src.labels import REQUIRED_LABELS, Labels
from src.logger import clear_issue_context, get_logger, log_message, set_issue_context, setup_logging
from src.security import check_actor_allowed
from src.telemetry import get_git_version, get_tracer, init_telemetry, record_llm_metrics
from src.ticket_clients.github import GitHubTicketClient
from src.workflows import (
    ImplementWorkflow,
    PlanWorkflow,
    PrepareWorkflow,
    ResearchWorkflow,
    Workflow,
    WorkflowContext,
)
from src.workspace import WorkspaceError, WorkspaceManager

logger = get_logger(__name__)


class _BackoffState:
    """Minimal state object for tenacity's wait_exponential.

    Tenacity's wait functions expect a RetryCallState with an attempt_number.
    This provides a lightweight alternative to avoid importing the full class.
    """

    def __init__(self, attempt_number: int):
        self.attempt_number = attempt_number


class WorkflowRunner:
    """Executes workflows by running prompts through Claude CLI."""

    def __init__(self, config: Config, version: str | None = None) -> None:
        """Initialize the workflow runner.

        Args:
            config: Application configuration
            version: Git version string for metrics attribution
        """
        self.config = config
        self.version = version
        logger.debug(f"WorkflowRunner initialized (version={version})")

    def run(
        self,
        workflow: Workflow,
        ctx: WorkflowContext,
        workflow_name: str,
        resume_session: str | None = None,
    ) -> str | None:
        """Run a workflow by executing its prompts sequentially.

        Args:
            workflow: The workflow to execute
            ctx: Context information for the workflow
            workflow_name: Name of the workflow stage for model selection
            resume_session: Optional session ID to resume from

        Returns:
            The session ID from the last prompt execution, or None if not available

        Raises:
            Exception: If any prompt execution fails
        """
        tracer = get_tracer()
        with tracer.start_as_current_span(
            f"workflow.{workflow.name}",
            attributes={
                "repo": ctx.repo,
                "issue.number": ctx.issue_number,
                "workflow": workflow_name,
                "resumed_session": resume_session or "",
            },
        ):
            logger.debug(f"Starting workflow '{workflow.name}' for issue #{ctx.issue_number}")
            logger.debug(f"Workspace: {ctx.workspace_path}")
            logger.debug(
                f"Resume session: {resume_session[:8] + '...' if resume_session else 'None'}"
            )

            # Get prompts from workflow
            prompts = workflow.init(ctx)
            logger.debug(f"Workflow has {len(prompts)} prompts to execute")

            session_id: str | None = None

            # Execute each prompt
            for i, prompt in enumerate(prompts, 1):
                with tracer.start_as_current_span(f"prompt.{i}"):
                    logger.debug(
                        f"Executing prompt {i}/{len(prompts)} for workflow '{workflow.name}'"
                    )
                    log_message(logger, "Prompt", prompt)

                    try:
                        model = self.config.stage_models.get(workflow_name)
                        issue_context = f"{ctx.repo}#{ctx.issue_number}"
                        result = run_claude(
                            prompt,
                            ctx.workspace_path,
                            model=model,
                            issue_context=issue_context,
                            resume_session=resume_session,
                            enable_telemetry=self.config.claude_code_enable_telemetry,
                            execution_stage=workflow_name.lower(),
                        )
                        logger.debug(f"Prompt {i}/{len(prompts)} completed successfully")
                        logger.debug(f"Response length: {len(result.response)} characters")

                        # Record LLM metrics
                        if result.metrics:
                            record_llm_metrics(
                                result.metrics,
                                ctx.repo,
                                ctx.issue_number,
                                workflow_name,
                                model,
                                version=self.version,
                            )
                            # Capture session ID for subsequent prompts and return
                            if result.metrics.session_id:
                                session_id = result.metrics.session_id
                                # Use this session for remaining prompts in this workflow
                                resume_session = session_id

                    except Exception as e:
                        logger.error(f"Failed to execute prompt {i}/{len(prompts)}: {e}")
                        raise

            logger.info(f"Workflow '{workflow.name}' completed successfully")
            return session_id


class Daemon:
    """Main orchestrator daemon that polls GitHub and triggers workflows."""

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
    def __init__(self, config: Config, version: str | None = None) -> None:
        """Initialize the daemon with configuration.

        Args:
            config: Application configuration
            version: Git version string captured at daemon startup
        """
        logger.debug("Initializing Daemon")
        logger.debug(
            f"Config: poll_interval={config.poll_interval}s, "
            f"watched_statuses={config.watched_statuses}, "
            f"max_concurrent_workflows={config.max_concurrent_workflows}"
        )

        self.config = config
        self.version = version
        self._running = False
        self._shutdown_requested = False
        self._shutdown_event = threading.Event()  # For efficient interruptible sleeps

        # Track in-progress workflows to prevent duplicates
        # Maps "repo#issue_number" -> start timestamp
        self._in_progress: dict[str, float] = {}
        self._in_progress_lock = threading.Lock()

        # Thread pool for parallel workflow execution
        self.executor = ThreadPoolExecutor(
            max_workers=config.max_concurrent_workflows, thread_name_prefix="workflow-"
        )
        logger.debug(
            f"ThreadPoolExecutor initialized with {config.max_concurrent_workflows} workers"
        )

        # Initialize components
        self.database = Database(config.database_path)
        logger.debug(f"Database initialized at {config.database_path}")

        tokens: dict[str, str] = {}
        if config.github_enterprise_host and config.github_enterprise_token:
            tokens[config.github_enterprise_host] = config.github_enterprise_token
        elif config.github_token:
            tokens["github.com"] = config.github_token
        self.ticket_client = GitHubTicketClient(tokens)
        logger.debug("Ticket client initialized")

        self.workspace_manager = WorkspaceManager(config.workspace_dir)
        logger.debug(f"Workspace manager initialized with dir: {config.workspace_dir}")

        self.runner = WorkflowRunner(config, version=version)

        self.comment_processor = CommentProcessor(
            self.ticket_client,
            self.database,
            self.runner,
            config.workspace_dir,
            allowed_username=config.allowed_username,
        )

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        # In-memory cache of project metadata (populated on startup)
        self._project_metadata: dict[str, ProjectMetadata] = {}

        # Validate GitHub connection at startup (fail fast if auth is broken)
        self._validate_github_connections()

        logger.debug("Daemon initialization complete")

    def _validate_github_connections(self) -> None:
        """Validate GitHub connections for all configured project URLs.

        Extracts unique hostnames from project URLs and validates authentication
        for each one. This provides fast failure at startup if credentials are
        misconfigured rather than failing later during the poll loop.

        Raises:
            RuntimeError: If any GitHub connection validation fails
        """
        logger.info("Validating GitHub connections...")

        # Extract unique hostnames from project URLs
        # URL format: https://github.com/orgs/myorg/projects/1 or
        #             https://ghes.company.com/orgs/myorg/projects/1
        hostnames: set[str] = set()
        for url in self.config.project_urls:
            # Parse hostname from URL (e.g., "https://github.com/..." -> "github.com")
            try:
                # URL format: https://HOSTNAME/orgs/ORG/projects/NUMBER
                parts = url.split("/")
                if len(parts) >= 3 and parts[0] in ("http:", "https:") and parts[1] == "":
                    hostname = parts[2]
                    hostnames.add(hostname)
            except (IndexError, ValueError) as e:
                logger.warning(f"Could not parse hostname from project URL {url}: {e}")

        if not hostnames:
            logger.warning("No hostnames found in project URLs, skipping validation")
            return

        # Validate connection for each unique hostname
        for hostname in sorted(hostnames):
            logger.info(f"Validating connection to {hostname}...")
            self.ticket_client.validate_connection(hostname)
            self.ticket_client.validate_scopes(hostname)

        logger.info(f"GitHub connection validation successful for {len(hostnames)} host(s)")

    def _initialize_project_metadata(self) -> None:
        """Fetch and cache project metadata (status options) on startup.

        This method runs once at startup to fetch fresh metadata:
        - Project IDs, status field IDs, and status option IDs

        This also ensures required workflow labels exist in each repository.

        Always fetches from GitHub to ensure freshness after project changes.
        """
        logger.info("Initializing project metadata cache...")

        # Track repos we've already ensured labels for (avoid duplicates)
        repos_with_labels: set[str] = set()

        for project_url in self.config.project_urls:
            try:
                # Fetch project metadata (project ID, status field, options)
                project_meta = self.ticket_client.get_board_metadata(project_url)

                # Get repo from project items
                items = self.ticket_client.get_board_items(project_url)
                if not items:
                    logger.warning(f"No items found in {project_url}, skipping metadata cache")
                    continue

                # Ensure required labels exist in ALL repos that have items in this project
                unique_repos = {item.repo for item in items}
                for repo in unique_repos:
                    if repo not in repos_with_labels:
                        self._ensure_required_labels(repo)
                        repos_with_labels.add(repo)

                # Use first repo for ProjectMetadata (only used for caching reference)
                repo = items[0].repo

                # Build and store metadata
                metadata = ProjectMetadata(
                    project_url=project_url,
                    repo=repo,
                    project_id=project_meta.get("project_id"),
                    status_field_id=project_meta.get("status_field_id"),
                    status_options=project_meta.get("status_options", {}),
                )

                self.database.upsert_project_metadata(metadata)
                self._project_metadata[project_url] = metadata

                logger.info(
                    f"Cached metadata for {project_url}: "
                    f"{len(metadata.status_options)} status options"
                )

            except Exception as e:
                logger.error(f"Failed to initialize metadata for {project_url}: {e}")

    def _ensure_required_labels(self, repo: str) -> None:
        """Ensure all required workflow labels exist in a repository.

        Creates any missing labels with appropriate descriptions and colors.

        Args:
            repo: Repository in 'owner/repo' format
        """
        logger.info(f"Ensuring required labels exist in {repo}...")

        existing_labels = set(self.ticket_client.get_repo_labels(repo))

        # Create any missing labels
        for label_name, label_config in REQUIRED_LABELS.items():
            if label_name not in existing_labels:
                success = self.ticket_client.create_repo_label(
                    repo,
                    label_name,
                    description=label_config["description"],
                    color=label_config["color"],
                )
                if success:
                    logger.info(f"Created label '{label_name}'")
                else:
                    logger.warning(f"Failed to create label '{label_name}'")
            else:
                logger.info(f"Label '{label_name}' already exists")

    def _signal_handler(self, signum, _frame) -> None:
        """Handle shutdown signals gracefully.

        Args:
            signum: Signal number
            frame: Current stack frame
        """
        signal_name = signal.Signals(signum).name
        logger.info(f"Received {signal_name}, initiating graceful shutdown...")
        self._shutdown_requested = True
        self._shutdown_event.set()  # Wake up any waiting sleeps

    def run(self) -> None:
        """Start the polling loop.

        This method runs continuously, polling the GitHub project board
        at regular intervals until stopped or a shutdown signal is received.

        Uses tenacity's wait_exponential for calculating backoff times on failures.
        """
        # Configure exponential backoff using tenacity (2, 4, 8, 16... up to 300s)
        # We use tenacity's wait_exponential class to compute backoff durations
        backoff_strategy = wait_exponential(multiplier=1, min=2, max=300)

        logger.debug("Starting daemon polling loop")
        logger.debug(f"Polling interval: {self.config.poll_interval} seconds")
        logger.debug(f"Watching statuses: {self.config.watched_statuses}")

        # Initialize project metadata cache on startup
        self._initialize_project_metadata()

        self._running = True
        consecutive_failures = 0

        try:
            while self._running and not self._shutdown_requested:
                try:
                    self._poll()
                    consecutive_failures = 0  # Reset on success
                except Exception as e:
                    consecutive_failures += 1
                    # Calculate backoff using tenacity's exponential formula:
                    # multiplier * (exp_base ** (attempt - 1)) clamped to [min, max]
                    # We add 1 to get 2^1, 2^2, 2^3... for failures 1, 2, 3...
                    backoff_seconds = backoff_strategy(_BackoffState(consecutive_failures + 1))

                    logger.error(f"Error during poll cycle: {e}", exc_info=True)
                    logger.info(
                        f"Poll failed ({consecutive_failures} consecutive). "
                        f"Backing off for {backoff_seconds:.0f}s before retry..."
                    )
                    # Efficient interruptible sleep using Event.wait()
                    if self._shutdown_event.wait(timeout=backoff_seconds):
                        break  # Shutdown requested during backoff
                    continue  # Skip the normal poll interval sleep

                # Sleep between polls (interruptible via shutdown event)
                if self._shutdown_event.wait(timeout=self.config.poll_interval):
                    break  # Shutdown requested during poll interval

        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        finally:
            self.stop()

    def stop(self) -> None:
        """Stop the daemon gracefully."""
        from src.cli import cleanup_claude_symlinks

        logger.debug("Stopping daemon")
        self._running = False

        # Shutdown executor and wait for running workflows
        try:
            logger.debug("Shutting down thread pool executor...")
            self.executor.shutdown(wait=True, cancel_futures=False)
            logger.debug("Thread pool executor shut down")
        except Exception as e:
            logger.error(f"Error shutting down executor: {e}")

        # Close database connection
        try:
            self.database.close()
            logger.debug("Database connection closed")
        except Exception as e:
            logger.error(f"Error closing database: {e}")

        # Clean up Claude symlinks
        try:
            cleanup_claude_symlinks()
            logger.debug("Claude symlinks cleaned up")
        except Exception as e:
            logger.warning(f"Error cleaning up Claude symlinks: {e}")

        logger.debug("Daemon stopped")

    def _poll(self) -> None:
        """Poll GitHub for project items and handle status changes.

        This method:
        1. Fetches all project items from all configured GitHub projects
        2. Compares current state to database state
        3. Triggers workflows for items with changed statuses (in parallel)
        """
        logger.debug("Starting poll cycle")

        # Detect and clear stale workflows (likely crashed)
        STALE_THRESHOLD = 3600  # 1 hour
        with self._in_progress_lock:
            now = time.time()
            stale = [(k, v) for k, v in self._in_progress.items() if now - v > STALE_THRESHOLD]
            for key, started_at in stale:
                logger.warning(
                    f"Stale workflow detected: {key} started {now - started_at:.0f}s ago - removing from tracking"
                )
                self._in_progress.pop(key, None)

        all_items: list[TicketItem] = []

        try:
            # Fetch items from all configured projects
            for project_url in self.config.project_urls:
                try:
                    items = self.ticket_client.get_board_items(project_url)
                    logger.debug(f"Fetched {len(items)} items from {project_url}")
                    all_items.extend(items)
                except Exception as e:
                    logger.error(f"Failed to fetch from {project_url}: {e}")
                    continue

            logger.debug(f"Total items from all projects: {len(all_items)}")

            # Check for Done items needing cleanup
            for item in all_items:
                if item.status == "Done":
                    self._maybe_cleanup(item)

            # Auto-archive issues closed without completion (won't do, duplicate, manual)
            for item in all_items:
                self._maybe_archive_closed(item)

            # Clean up worktrees for all closed issues
            for item in all_items:
                self._maybe_cleanup_closed(item)

            # Move Validate issues with merged PR to Done
            for item in all_items:
                self._maybe_move_to_done(item)

            # Set issues without status to Backlog
            for item in all_items:
                self._maybe_set_backlog(item)

            # Process user comments on issues in Backlog, Research, or Plan status
            for item in all_items:
                if self._might_have_new_comments(item):
                    self.executor.submit(self.comment_processor.process, item)

            # YOLO: Move Backlog issues with yolo label to Research
            for item in all_items:
                # Fast path: if not in cached labels, definitely not present
                if Labels.YOLO not in item.labels:
                    continue
                if item.status != "Backlog" or item.state == "CLOSED":
                    continue

                key = f"{item.repo}#{item.ticket_id}"

                # Fresh check: verify yolo label is still present (may have been removed since poll started)
                if not self._has_yolo_label(item.repo, item.ticket_id):
                    logger.debug(f"YOLO: Skipping Backlog→Research for {key} - yolo label was removed")
                    continue

                actor = self.ticket_client.get_label_actor(
                    item.repo, item.ticket_id, Labels.YOLO
                )
                if not check_actor_allowed(actor, self.config.allowed_username, key, "YOLO"):
                    continue
                logger.info(
                    f"YOLO: Starting auto-progression for {key} from Backlog "
                    f"(label added by allowed user '{actor}')"
                )
                self.ticket_client.update_item_status(item.item_id, "Research")

            # Handle reset label: clear kiln content and move issue to Backlog
            for item in all_items:
                self._maybe_handle_reset(item)

            # Collect items that need workflow execution
            items_to_process: list[TicketItem] = []
            for item in all_items:
                if self._should_trigger_workflow(item):
                    items_to_process.append(item)
                elif self._should_yolo_advance(item):
                    # Issue has yolo but isn't eligible for workflow (likely already complete)
                    # Advance to next status
                    self._yolo_advance(item)

            if not items_to_process:
                logger.debug("No workflows to trigger")
                logger.debug("Poll cycle completed")
                return

            logger.debug(f"Submitting {len(items_to_process)} items for parallel processing")

            # Submit workflows to thread pool
            futures = {}
            for item in items_to_process:
                future = self.executor.submit(self._process_item_workflow, item)
                futures[future] = item

            # Log submission - workflows will run asynchronously
            # Results are logged in _on_workflow_complete via add_done_callback
            for future, item in futures.items():
                future.add_done_callback(lambda f, i=item: self._on_workflow_complete(f, i))

            logger.debug("Poll cycle completed")

        except Exception as e:
            logger.error(f"Error fetching project items: {e}", exc_info=True)
            raise

    def _should_trigger_workflow(self, item: TicketItem) -> bool:
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
        with self._in_progress_lock:
            if key in self._in_progress:
                logger.debug(
                    f"Skipping {key} - workflow in progress since {self._in_progress[key]}"
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

        actor = self.ticket_client.get_last_status_actor(item.repo, item.ticket_id)
        if not check_actor_allowed(actor, self.config.allowed_username, key):
            return False

        logger.info(f"Workflow trigger: {key} in '{item.status}' by allowed user '{actor}'")
        return True

    def _should_yolo_advance(self, item: TicketItem) -> bool:
        """Check if an item should advance via YOLO (has yolo label but can't run workflow).

        This handles the case where yolo is added after a workflow stage completes.
        For example, if yolo is added when an issue has research_ready label in Research status,
        it should advance to Plan.

        Args:
            item: TicketItem from GitHub (with cached labels)

        Returns:
            True if item should be advanced to next YOLO status
        """
        # Fast path: if not in cached labels, definitely not present
        if Labels.YOLO not in item.labels:
            return False

        # Skip closed issues
        if item.state == "CLOSED":
            return False

        # Must have a YOLO progression target
        if item.status not in self.YOLO_PROGRESSION:
            return False

        # Skip Backlog - handled separately in _poll() with immediate status change
        if item.status == "Backlog":
            return False

        # Must have the complete label for the current status (indicates stage is done)
        config = self.WORKFLOW_CONFIG.get(item.status)
        if not config:
            return False

        complete_label = config["complete_label"]
        if not (complete_label and complete_label in item.labels):
            return False

        # Fresh check: verify yolo label is still present (may have been removed since poll started)
        if not self._has_yolo_label(item.repo, item.ticket_id):
            key = f"{item.repo}#{item.ticket_id}"
            logger.debug(f"YOLO: Skipping advancement for {key} - yolo label was removed")
            return False

        return True

    def _yolo_advance(self, item: TicketItem) -> None:
        """Advance an item to the next YOLO status.

        Validates that the yolo label was added by an allowed user before advancing.
        Also verifies the label is still present (fresh check) in case it was removed
        after _should_yolo_advance() returned True but before this method runs.

        Args:
            item: TicketItem to advance
        """
        key = f"{item.repo}#{item.ticket_id}"
        yolo_next = self.YOLO_PROGRESSION.get(item.status)

        if not yolo_next:
            return

        # Fresh check: verify yolo label is still present before advancing
        if not self._has_yolo_label(item.repo, item.ticket_id):
            logger.info(f"YOLO: Skipping advancement for {key} - yolo label was removed")
            return

        actor = self.ticket_client.get_label_actor(item.repo, item.ticket_id, Labels.YOLO)
        if not check_actor_allowed(actor, self.config.allowed_username, key, "YOLO"):
            return

        logger.info(
            f"YOLO: Advancing {key} from '{item.status}' to '{yolo_next}' "
            f"(stage complete, label added by allowed user '{actor}')"
        )
        self.ticket_client.update_item_status(item.item_id, yolo_next)

    def _has_yolo_label(self, repo: str, issue_number: int) -> bool:
        """Check if issue currently has yolo label (fresh from GitHub).

        This fetches fresh label data from GitHub to handle the case where
        a user removes the yolo label mid-workflow. Using cached item.labels
        would miss this change.

        Args:
            repo: Repository in 'hostname/owner/repo' format
            issue_number: Issue number

        Returns:
            True if yolo label is currently present, False otherwise.
            Returns False on any error (fail-safe: don't advance if uncertain).
        """
        try:
            current_labels = self.ticket_client.get_issue_labels(repo, issue_number)
            return Labels.YOLO in current_labels
        except Exception as e:
            logger.warning(f"Could not fetch current labels for {repo}#{issue_number}: {e}")
            return False  # Fail safe - don't advance if we can't verify

    def _get_pr_for_issue(self, repo: str, issue_number: int) -> dict | None:
        """Get the open PR that closes a specific issue.

        Args:
            repo: Repository in 'hostname/owner/repo' format
            issue_number: Issue number

        Returns:
            Dict with PR info (number, body) or None if no PR found
        """
        try:
            import json as json_module

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

    def _might_have_new_comments(self, item: TicketItem) -> bool:
        """Quick heuristic to check if item might have new comments.

        Uses only cached data from TicketItem and database - no API calls.

        Args:
            item: TicketItem from GitHub (with cached data)

        Returns:
            True if item should be submitted for comment processing
        """
        # Only process items in comment-eligible statuses
        if item.status not in {"Backlog", "Research", "Plan"}:
            return False

        # Skip closed issues
        if item.state == "CLOSED":
            return False

        # Skip if already being edited
        if Labels.EDITING in item.labels:
            return False

        # Check if comment count changed from last known
        stored = self.database.get_issue_state(item.repo, item.ticket_id)
        return not (stored and item.comment_count == stored.last_known_comment_count)

    def _maybe_cleanup(self, item: TicketItem) -> None:
        """Clean up worktree for Done issues.

        Uses 'cleaned_up' label to externalize cleanup state.
        Uses cached labels from TicketItem to avoid API calls.

        Args:
            item: TicketItem in Done status (with cached labels)
        """
        # Skip if already cleaned up - use cached labels
        if Labels.CLEANED_UP in item.labels:
            return

        # Clean up worktree if it exists
        repo_name = item.repo.split("/")[-1]
        worktree_path = self._get_worktree_path(item.repo, item.ticket_id)
        if Path(worktree_path).exists():
            try:
                self.workspace_manager.cleanup_workspace(repo_name, item.ticket_id)
                logger.info("Cleaned up worktree")
            except Exception as e:
                logger.error(f"Cleanup failed: {e}")

        # Mark as cleaned up (prevents repeated checks)
        self.ticket_client.add_label(item.repo, item.ticket_id, Labels.CLEANED_UP)

    def _maybe_archive_closed(self, item: TicketItem) -> None:
        """Archive project items for issues closed without actual completion.

        Archives issues closed as:
        - NOT_PLANNED (won't do)
        - DUPLICATE
        - null/manual close (no state_reason)
        - COMPLETED but without a merged PR (manual close as "completed")

        Only issues closed as COMPLETED with a merged PR go to Done.
        Uses cached issue state from TicketItem to avoid API calls.

        Args:
            item: TicketItem to check and potentially archive (with cached state)
        """
        # Only process closed issues
        if item.state != "CLOSED":
            return

        # COMPLETED with merged PR goes to Done, not archived
        if item.state_reason == "COMPLETED" and item.has_merged_changes:
            return

        # Get project metadata for the project ID
        metadata = self._project_metadata.get(item.board_url)
        if not metadata or not metadata.project_id:
            logger.warning(f"No project metadata for {item.board_url}, cannot archive")
            return

        # Archive the project item
        reason = item.state_reason or "manual close"
        logger.info(f"Auto-archiving issue (reason: {reason})")
        if self.ticket_client.archive_item(metadata.project_id, item.item_id):
            logger.info("Archived from project board")

    def _maybe_cleanup_closed(self, item: TicketItem) -> None:
        """Clean up worktree for any closed issue.

        This handles closed issues that didn't go through the Done status,
        including manually closed issues and issues closed without merged PRs.
        Non-completed issues are archived by _maybe_archive_closed() before this.

        Uses 'cleaned_up' label to externalize cleanup state and prevent
        repeated processing.

        Args:
            item: TicketItem to check (with cached labels and state)
        """
        # Only process closed issues
        if item.state != "CLOSED":
            return

        # Skip if already cleaned up - use cached labels
        if Labels.CLEANED_UP in item.labels:
            return

        # Clean up worktree if it exists
        repo_name = item.repo.split("/")[-1]
        worktree_path = self._get_worktree_path(item.repo, item.ticket_id)
        if Path(worktree_path).exists():
            try:
                self.workspace_manager.cleanup_workspace(repo_name, item.ticket_id)
                logger.info("Cleaned up worktree for closed issue")
            except Exception as e:
                logger.error(f"Cleanup failed for closed issue: {e}")

        # Mark as cleaned up (prevents repeated checks)
        self.ticket_client.add_label(item.repo, item.ticket_id, Labels.CLEANED_UP)

    def _maybe_move_to_done(self, item: TicketItem) -> None:
        """Move issues to Done when PR is merged and issue is closed as COMPLETED.

        Conditions:
        - Item is not already in "Done" status
        - Item is closed as COMPLETED (others are archived instead)
        - Item has at least one merged PR
        - Item is closed (GitHub auto-closes when PR with "closes #X" merges)

        Args:
            item: TicketItem to check
        """
        # Skip items already in Done
        if item.status == "Done":
            return

        # Only process COMPLETED issues (others are archived by _maybe_archive_closed)
        if item.state_reason != "COMPLETED":
            return

        # Must have merged PR
        if not item.has_merged_changes:
            return

        # Must be closed
        if item.state != "CLOSED":
            return

        # Move to Done
        logger.info(f"Moving {item.repo}#{item.ticket_id} to Done (PR merged, issue closed)")
        try:
            self.ticket_client.update_item_status(item.item_id, "Done")
            logger.info(f"Moved {item.repo}#{item.ticket_id} to Done")
        except Exception as e:
            logger.error(f"Failed to move {item.repo}#{item.ticket_id} to Done: {e}")

    def _maybe_set_backlog(self, item: TicketItem) -> None:
        """Set issues without a status to Backlog.

        When an issue is added to the project board but not assigned a status,
        it shows as "Unknown" in our query. This sets it to Backlog.

        Args:
            item: TicketItem to check
        """
        # Only process items with no status set
        if item.status != "Unknown":
            return

        # Skip closed issues
        if item.state == "CLOSED":
            return

        # Set to Backlog
        logger.info(f"Setting {item.repo}#{item.ticket_id} to Backlog (no status)")
        try:
            self.ticket_client.update_item_status(item.item_id, "Backlog")
            logger.info(f"Set {item.repo}#{item.ticket_id} to Backlog")
        except Exception as e:
            logger.error(f"Failed to set {item.repo}#{item.ticket_id} to Backlog: {e}")

    def _maybe_handle_reset(self, item: TicketItem) -> None:
        """Handle the reset label by clearing kiln content and moving issue to Backlog.

        When a user adds the 'reset' label to an issue, this method:
        1. Validates the label was added by an allowed user
        2. Removes the 'reset' label
        3. Clears kiln-generated content (research/plan sections) from the issue body
        4. Removes workflow-related labels (research_ready, plan_ready, researching, planning)
        5. Moves the issue to Backlog status

        Args:
            item: TicketItem to check (with cached labels)
        """
        # Only process items with the reset label
        if Labels.RESET not in item.labels:
            return

        # Skip closed issues
        if item.state == "CLOSED":
            return

        key = f"{item.repo}#{item.ticket_id}"

        actor = self.ticket_client.get_label_actor(item.repo, item.ticket_id, Labels.RESET)
        if not check_actor_allowed(actor, self.config.allowed_username, key, "RESET"):
            # Only remove reset label when actor is known but not allowed (to prevent repeated warnings)
            # When actor is unknown, keep the label for security logging visibility
            if actor is not None:
                self.ticket_client.remove_label(item.repo, item.ticket_id, Labels.RESET)
            return

        logger.info(
            f"RESET: Processing reset for {key} in '{item.status}' "
            f"(label added by allowed user '{actor}')"
        )

        # Remove the reset label first
        self.ticket_client.remove_label(item.repo, item.ticket_id, Labels.RESET)

        # Clean up worktree if it exists (prevents rebase failures on subsequent Research runs)
        repo_name = item.repo.split("/")[-1]
        worktree_path = self._get_worktree_path(item.repo, item.ticket_id)
        if Path(worktree_path).exists():
            try:
                self.workspace_manager.cleanup_workspace(repo_name, item.ticket_id)
                logger.info(f"RESET: Cleaned up worktree for {key}")
            except Exception as e:
                logger.warning(f"RESET: Failed to cleanup worktree for {key}: {e}")

        # Remove linking keywords from related PRs (severs PR-issue relationship)
        self._remove_pr_issue_links(item)

        # Clear kiln-generated content from issue body
        self._clear_kiln_content(item)

        # Remove ALL labels from the issue
        for label in item.labels:
            try:
                self.ticket_client.remove_label(item.repo, item.ticket_id, label)
                logger.info(f"RESET: Removed '{label}' label from {key}")
            except Exception as e:
                logger.warning(f"RESET: Failed to remove '{label}' from {key}: {e}")

        # Move issue to Backlog
        try:
            self.ticket_client.update_item_status(item.item_id, "Backlog")
            logger.info(f"RESET: Moved {key} to Backlog")
        except Exception as e:
            logger.error(f"RESET: Failed to move {key} to Backlog: {e}")

    def _clear_kiln_content(self, item: TicketItem) -> None:
        """Clear kiln-generated content from an issue's body.

        Removes the research section (between <!-- kiln:research --> and <!-- /kiln:research -->)
        and the plan section (between <!-- kiln:plan --> and <!-- /kiln:plan -->) from the issue body,
        leaving only the original user-created description.

        Args:
            item: TicketItem whose body should be cleared
        """
        key = f"{item.repo}#{item.ticket_id}"

        # Get current issue body
        body = self.ticket_client.get_ticket_body(item.repo, item.ticket_id)
        if body is None:
            logger.warning(f"RESET: Could not get issue body for {key}")
            return

        original_body = body

        # Remove research section (including separator before it)
        # Pattern: optional separator (---) followed by research section
        research_pattern = r"\n*---\n*<!-- kiln:research -->.*?<!-- /kiln:research -->"
        body = re.sub(research_pattern, "", body, flags=re.DOTALL)

        # Remove plan section (including separator before it)
        plan_pattern = r"\n*---\n*<!-- kiln:plan -->.*?<!-- /kiln:plan -->"
        body = re.sub(plan_pattern, "", body, flags=re.DOTALL)

        # Also handle case where sections don't have separator
        research_pattern_no_sep = r"\n*<!-- kiln:research -->.*?<!-- /kiln:research -->"
        body = re.sub(research_pattern_no_sep, "", body, flags=re.DOTALL)

        plan_pattern_no_sep = r"\n*<!-- kiln:plan -->.*?<!-- /kiln:plan -->"
        body = re.sub(plan_pattern_no_sep, "", body, flags=re.DOTALL)

        # Handle legacy end marker (<!-- /kiln -->) for backwards compatibility
        # Research with legacy end marker and separator
        research_pattern_legacy = r"\n*---\n*<!-- kiln:research -->.*?<!-- /kiln -->"
        body = re.sub(research_pattern_legacy, "", body, flags=re.DOTALL)

        # Research with legacy end marker without separator
        research_pattern_legacy_no_sep = r"\n*<!-- kiln:research -->.*?<!-- /kiln -->"
        body = re.sub(research_pattern_legacy_no_sep, "", body, flags=re.DOTALL)

        # Plan with legacy end marker and separator
        plan_pattern_legacy = r"\n*---\n*<!-- kiln:plan -->.*?<!-- /kiln -->"
        body = re.sub(plan_pattern_legacy, "", body, flags=re.DOTALL)

        # Plan with legacy end marker without separator
        plan_pattern_legacy_no_sep = r"\n*<!-- kiln:plan -->.*?<!-- /kiln -->"
        body = re.sub(plan_pattern_legacy_no_sep, "", body, flags=re.DOTALL)

        # Clean up any trailing whitespace
        body = body.rstrip()

        # Only update if body actually changed
        if body == original_body:
            logger.info(f"RESET: No kiln content to clear from {key}")
            return

        # Update the issue body via gh CLI
        try:
            # Extract hostname and owner/repo from item.repo (format: hostname/owner/repo)
            parts = item.repo.split("/", 1)
            if len(parts) == 2:
                hostname, owner_repo = parts
                repo_ref = owner_repo if hostname == "github.com" else f"{hostname}/{owner_repo}"
            else:
                repo_ref = item.repo

            subprocess.run(
                ["gh", "issue", "edit", str(item.ticket_id), "--repo", repo_ref, "--body", body],
                capture_output=True,
                text=True,
                check=True,
            )
            logger.info(f"RESET: Cleared kiln content from {key}")
        except subprocess.CalledProcessError as e:
            logger.error(f"RESET: Failed to clear kiln content from {key}: {e.stderr}")

    def _remove_pr_issue_links(self, item: TicketItem) -> None:
        """Remove linking keywords from PRs that are linked to this issue.

        Finds all PRs that have linking keywords (closes, fixes, resolves, etc.)
        pointing to this issue and edits their bodies to remove the keyword
        while preserving the issue reference as a breadcrumb.

        This severs the automatic PR-issue link so merging the PR won't close
        the issue.

        Args:
            item: TicketItem whose linked PRs should be unlinked
        """
        key = f"{item.repo}#{item.ticket_id}"

        # Get all linked PRs
        try:
            linked_prs = self.ticket_client.get_linked_prs(item.repo, item.ticket_id)
        except Exception as e:
            logger.warning(f"RESET: Failed to get linked PRs for {key}: {e}")
            return

        if not linked_prs:
            logger.debug(f"RESET: No linked PRs found for {key}")
            return

        logger.info(f"RESET: Found {len(linked_prs)} linked PRs for {key}")

        # Remove linking keywords from each PR
        for pr in linked_prs:
            # Skip merged PRs - the link is already broken (issue was closed)
            if pr.merged:
                logger.debug(f"RESET: Skipping merged PR #{pr.number} for {key}")
                continue

            try:
                removed = self.ticket_client.remove_pr_issue_link(
                    item.repo, pr.number, item.ticket_id
                )
                if removed:
                    logger.info(f"RESET: Removed linking keyword from PR #{pr.number} for {key}")
                else:
                    logger.debug(
                        f"RESET: No linking keyword to remove from PR #{pr.number} for {key}"
                    )
            except Exception as e:
                logger.warning(
                    f"RESET: Failed to remove linking keyword from PR #{pr.number} for {key}: {e}"
                )

    def _process_item_workflow(self, item: TicketItem) -> None:
        """Process an item that needs a workflow (runs in thread).

        Uses labels to track workflow state:
        - Adds running_label before starting
        - On success: removes running_label, adds complete_label (or moves status)
        - On failure: removes running_label, stays in current state

        Auto-prepares worktree if it doesn't exist before running the workflow.

        Args:
            item: TicketItem to process
        """
        key = f"{item.repo}#{item.ticket_id}"

        # Mark as in-progress (in-memory)
        with self._in_progress_lock:
            self._in_progress[key] = time.time()

        # Set logging context for this workflow thread
        set_issue_context(item.repo, item.ticket_id)

        # Get workflow config for label management
        config = self.WORKFLOW_CONFIG.get(item.status)
        running_label = config["running_label"] if config else None
        complete_label = config["complete_label"] if config else None
        next_status = config["next_status"] if config else None

        try:
            # Ensure issue state exists before workflow runs (needed for session ID storage)
            self.database.update_issue_state(
                item.repo, item.ticket_id, item.status, project_url=item.board_url
            )

            # Auto-prepare: Create worktree if it doesn't exist (for any workflow)
            worktree_path = self._get_worktree_path(item.repo, item.ticket_id)
            if not Path(worktree_path).exists():
                logger.info("Auto-preparing worktree")
                # Add preparing label during worktree creation
                self.ticket_client.add_label(item.repo, item.ticket_id, Labels.PREPARING)
                try:
                    self._auto_prepare_worktree(item)
                finally:
                    # Remove preparing label after worktree created
                    self.ticket_client.remove_label(item.repo, item.ticket_id, Labels.PREPARING)

            # Add running label before starting workflow (soft lock)
            if running_label:
                self.ticket_client.add_label(item.repo, item.ticket_id, running_label)
                logger.debug(f"Added '{running_label}' label to {key}")

            # Run the workflow
            self._run_workflow(item.status, item)

            # Workflow completed successfully
            # Remove running label
            if running_label:
                self.ticket_client.remove_label(item.repo, item.ticket_id, running_label)
                logger.debug(f"Removed '{running_label}' label from {key}")

            # Validate research block exists after Research workflow
            if item.status == "Research":
                body = self.ticket_client.get_ticket_body(item.repo, item.ticket_id)
                if body is None or "<!-- kiln:research -->" not in body:
                    self.ticket_client.add_label(item.repo, item.ticket_id, Labels.RESEARCH_FAILED)
                    logger.warning(
                        f"Research completed but no research block found for {key}"
                    )
                    # Don't add research_ready, don't advance YOLO
                    return

            # Add complete label or move to next status
            if complete_label:
                self.ticket_client.add_label(item.repo, item.ticket_id, complete_label)
                logger.debug(f"Added '{complete_label}' label to {key}")

            # Check if Implement workflow completed all tasks
            if item.status == "Implement" and next_status:
                from src.workflows.implement import count_checkboxes

                pr_info = self._get_pr_for_issue(item.repo, item.ticket_id)
                if pr_info:
                    pr_body = pr_info.get("body", "")
                    total_tasks, completed_tasks = count_checkboxes(pr_body)
                    if total_tasks > 0 and completed_tasks == total_tasks:
                        self.ticket_client.update_item_status(item.item_id, next_status)
                        logger.info(f"All {total_tasks} tasks complete, moved {key} to '{next_status}'")
                        next_status = None  # Prevent duplicate move below

            if next_status:
                self.ticket_client.update_item_status(item.item_id, next_status)
                logger.info(f"Moved {key} to '{next_status}' status")

            # YOLO mode: auto-advance to next workflow status
            # Re-check yolo label to handle removal during workflow execution
            if Labels.YOLO in item.labels and not next_status:
                yolo_next = self.YOLO_PROGRESSION.get(item.status)
                if yolo_next:
                    # Fresh check - yolo may have been removed while workflow was running
                    if self._has_yolo_label(item.repo, item.ticket_id):
                        self.ticket_client.update_item_status(item.item_id, yolo_next)
                        logger.info(f"YOLO: Auto-advanced {key} from '{item.status}' to '{yolo_next}'")
                    else:
                        logger.info(
                            f"YOLO: Skipping advancement for {key} - yolo label was removed during workflow"
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

            # On failure: remove running label (workflow is no longer running)
            if running_label:
                try:
                    self.ticket_client.remove_label(item.repo, item.ticket_id, running_label)
                    logger.debug(f"Removed '{running_label}' label from {key} after failure")
                except Exception as label_err:
                    logger.warning(f"Could not remove running label after failure: {label_err}")

            # YOLO mode failure: remove yolo label, add yolo_failed
            if Labels.YOLO in item.labels:
                try:
                    self.ticket_client.remove_label(item.repo, item.ticket_id, Labels.YOLO)
                    self.ticket_client.add_label(item.repo, item.ticket_id, Labels.YOLO_FAILED)
                    logger.warning(f"YOLO: Workflow failed for {key}, cancelled auto-progression")
                except Exception as yolo_err:
                    logger.warning(f"Could not update YOLO labels after failure: {yolo_err}")

            raise

        finally:
            # Always remove from in-progress tracking
            with self._in_progress_lock:
                self._in_progress.pop(key, None)
            # Clear logging context
            clear_issue_context()

    def _on_workflow_complete(self, future, _item: TicketItem) -> None:
        """Callback when a workflow completes (success or failure).

        Args:
            future: The completed Future
            item: The TicketItem that was processed
        """
        try:
            future.result()
            logger.info("Completed workflow")
        except Exception as e:
            logger.error(f"Workflow failed: {e}", exc_info=True)

    def _get_worktree_path(self, repo: str, issue_number: int) -> str:
        """Get the worktree path for a repo and issue.

        Args:
            repo: Repository in 'owner/repo' format
            issue_number: Issue number

        Returns:
            Path to the worktree directory
        """
        # Extract just the repo name from 'owner/repo'
        repo_name = repo.split("/")[-1] if "/" in repo else repo
        return f"{self.config.workspace_dir}/{repo_name}-issue-{issue_number}"

    def _get_parent_pr_info(
        self, repo: str, ticket_id: int
    ) -> tuple[int | None, str | None]:
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
        logger.info(
            f"Found parent PR #{parent_pr.get('number')} with branch '{parent_branch}'"
        )
        return parent_issue_number, parent_branch

    def _auto_prepare_worktree(self, item: TicketItem) -> None:
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
        parent_issue_number, parent_branch = self._get_parent_pr_info(
            item.repo, item.ticket_id
        )

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
            allowed_username=self.config.allowed_username,
            parent_issue_number=parent_issue_number,
            parent_branch=parent_branch,
        )
        self.runner.run(workflow, ctx, "Prepare")

        if parent_branch:
            logger.info(f"Auto-prepared worktree (branching from parent branch '{parent_branch}')")
        else:
            logger.info("Auto-prepared worktree")

    def _run_workflow(
        self,
        workflow_name: str,
        item: TicketItem,
    ) -> None:
        """Run a workflow for a project item.

        Args:
            workflow_name: Name of the workflow status (e.g., "Research", "Plan")
            item: TicketItem to process
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
        workspace_path = self._get_worktree_path(item.repo, item.ticket_id)

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
            allowed_username=self.config.allowed_username,
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
        except Exception as e:
            logger.error(f"Workflow '{workflow_name}' failed: {e}", exc_info=True)
            # Add failure label for Implement workflow
            if workflow_name == "Implement":
                self.ticket_client.add_label(item.repo, item.ticket_id, Labels.IMPLEMENTATION_FAILED)
                logger.info(
                    f"Added '{Labels.IMPLEMENTATION_FAILED}' label to "
                    f"{item.repo}#{item.ticket_id}"
                )
            raise


def main() -> None:
    """Main entry point for the daemon.

    Sets up logging, loads configuration, and runs the daemon.
    """
    try:
        # Load configuration first (needed for log settings)
        config = load_config()

        # Setup logging with config
        setup_logging(
            log_file=config.log_file,
            log_size=config.log_size,
            log_backups=config.log_backups,
        )
        logger.info("=== Agentic Metallurgy Daemon Starting ===")
        logger.info(f"Logging to file: {config.log_file}")
        logger.debug("Configuration loaded successfully")

        # Get git version once at startup for consistent attribution
        git_version = get_git_version()
        logger.info(f"Current kiln HEAD SHA: {git_version}")

        # Initialize OpenTelemetry if configured
        if config.otel_endpoint:
            init_telemetry(
                config.otel_endpoint,
                config.otel_service_name,
                service_version=git_version,
            )

        # Create and run daemon with locked version
        daemon = Daemon(config, version=git_version)
        daemon.run()

    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, exiting...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

    logger.info("=== Kiln Daemon Stopped ===")


if __name__ == "__main__":
    main()
