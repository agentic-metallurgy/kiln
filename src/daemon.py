"""Main daemon/poller module for agentic-metallurgy.

This module provides the orchestrator that ties together all components:
- Polls GitHub project boards for changes
- Manages workspace creation and cleanup
- Triggers appropriate workflows based on status changes
- Runs Claude workflows with proper error handling
"""

import signal
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from tenacity import wait_exponential

from src.claude_runner import run_claude
from src.comment_processor import CommentProcessor
from src.config import Config, load_config
from src.daemon_utils import get_hostname_from_url
from src.database import Database, ProjectMetadata
from src.hibernation import Hibernation
from src.reset_handler import ResetHandler
from src.state_manager import StateManager
from src.workflow_orchestrator import WorkflowOrchestrator
from src.yolo_controller import YoloController
from src.interfaces import TicketItem
from src.labels import REQUIRED_LABELS, Labels
from src.logger import (
    _extract_org_from_url,
    get_logger,
    log_message,
    setup_logging,
)
from src.pagerduty import init_pagerduty
from src.security import ActorCategory, check_actor_allowed
from src.telemetry import get_git_version, get_tracer, init_telemetry, record_llm_metrics
from src.ticket_clients import get_github_client
from src.workflows import (
    Workflow,
    WorkflowContext,
)
from src.workspace import WorkspaceManager

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

    # Hibernation interval in seconds (5 minutes)
    HIBERNATION_INTERVAL = 300

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

        # Track issues with running workflow labels for cleanup on shutdown
        # Maps "repo#issue_number" -> running_label (e.g., "implementing")
        self._running_labels: dict[str, str] = {}
        self._running_labels_lock = threading.Lock()

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

        # Create the appropriate GitHub client based on version
        self.ticket_client = get_github_client(
            tokens=tokens,
            enterprise_version=config.github_enterprise_version,
        )
        logger.info(f"Ticket client initialized: {self.ticket_client.client_description}")

        # Log feature availability for the selected client
        self._log_client_features()

        # Initialize hibernation manager
        self.hibernation = Hibernation(
            ticket_client=self.ticket_client,
            project_urls=config.project_urls,
            hibernation_interval=self.HIBERNATION_INTERVAL,
        )

        # Initialize YOLO controller (uses WorkflowOrchestrator.WORKFLOW_CONFIG)
        self.yolo_controller = YoloController(
            ticket_client=self.ticket_client,
            username_self=config.username_self,
            team_usernames=config.team_usernames,
            workflow_config=WorkflowOrchestrator.WORKFLOW_CONFIG,
        )

        self.workspace_manager = WorkspaceManager(config.workspace_dir)

        # Initialize reset handler
        self.reset_handler = ResetHandler(
            ticket_client=self.ticket_client,
            workspace_manager=self.workspace_manager,
            username_self=config.username_self,
            team_usernames=config.team_usernames,
            workspace_dir=config.workspace_dir,
        )
        logger.debug(f"Workspace manager initialized with dir: {config.workspace_dir}")

        self.runner = WorkflowRunner(config, version=version)

        self.comment_processor = CommentProcessor(
            self.ticket_client,
            self.database,
            self.runner,
            config.workspace_dir,
            username_self=config.username_self,
            team_usernames=config.team_usernames,
        )

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        # In-memory cache of project metadata (populated on startup)
        self._project_metadata: dict[str, ProjectMetadata] = {}

        # Track repos that have had required labels ensured
        self._repos_with_labels: set[str] = set()

        # Initialize state manager (must be after workspace_manager, ticket_client, and _project_metadata)
        # Note: project_metadata dict is passed by reference, so it will be populated during _initialize_project_metadata()
        self.state_manager = StateManager(
            ticket_client=self.ticket_client,
            workspace_manager=self.workspace_manager,
            project_metadata=self._project_metadata,
            running_labels=self._running_labels,
            running_labels_lock=self._running_labels_lock,
            workspace_dir=config.workspace_dir,
        )

        # Initialize workflow orchestrator
        self.workflow_orchestrator = WorkflowOrchestrator(
            ticket_client=self.ticket_client,
            database=self.database,
            runner=self.runner,
            workspace_manager=self.workspace_manager,
            config=config,
            yolo_controller=self.yolo_controller,
            in_progress=self._in_progress,
            in_progress_lock=self._in_progress_lock,
            running_labels=self._running_labels,
            running_labels_lock=self._running_labels_lock,
        )

        # Validate GitHub connection at startup (fail fast if auth is broken)
        self._validate_github_connections()

        logger.debug("Daemon initialization complete")

    def _log_client_features(self) -> None:
        """Log feature availability for the selected GitHub client.

        This helps users understand which features are available or limited
        based on their GitHub configuration (github.com vs GHES version).
        """
        client = self.ticket_client

        if not client.supports_sub_issues:
            logger.info(
                f"  - Sub-issues (parent/child relationships) are disabled "
                f"({client.client_description} does not support sub-issues API)"
            )

        if not client.supports_status_actor_check:
            logger.warning(
                f"  - Status change actor verification is disabled "
                f"({client.client_description} does not support project timeline events)"
            )
            logger.warning(
                "    Security note: Cannot verify who changed project status. "
                "Ensure only authorized users have project write access."
            )

        # Log any specific notes about linked PR detection
        if hasattr(client, "check_merged_changes_for_issue"):
            # GHES 3.14 uses alternative implementation
            logger.info(
                f"  - Merged PR detection: Using timelineItems + CLOSED_EVENT "
                f"(closedByPullRequestsReferences unavailable in {client.client_description})"
            )

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
                    if repo not in self._repos_with_labels:
                        self._ensure_required_labels(repo)
                        self._repos_with_labels.add(repo)

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

    @property
    def _hibernating(self) -> bool:
        """Delegate hibernation state to Hibernation manager."""
        return self.hibernation.is_hibernating

    def _enter_hibernation(self, reason: str) -> None:
        """Enter hibernation mode. Delegates to Hibernation manager."""
        self.hibernation.enter_hibernation(reason)

    def _exit_hibernation(self) -> None:
        """Exit hibernation mode. Delegates to Hibernation manager."""
        self.hibernation.exit_hibernation()

    def _check_github_connectivity(self) -> bool:
        """Check GitHub connectivity. Delegates to Hibernation manager."""
        return self.hibernation.check_connectivity()

    def run(self) -> None:
        """Start the polling loop with hibernation mode support.

        This method runs continuously, polling the GitHub project board
        at regular intervals until stopped or a shutdown signal is received.

        Before each poll cycle, a health check validates GitHub API connectivity.
        If the health check fails, the daemon enters hibernation mode and re-checks
        connectivity every HIBERNATION_INTERVAL seconds until restored.

        Uses tenacity's wait_exponential for calculating backoff times on non-network
        failures.
        """
        # Import here to avoid circular imports
        from src.ticket_clients.base import NetworkError

        # Configure exponential backoff using tenacity (2, 4, 8, 16... up to 300s)
        # We use tenacity's wait_exponential class to compute backoff durations
        # This is only used for non-network errors; network errors use hibernation
        backoff_strategy = wait_exponential(multiplier=1, min=2, max=300)

        logger.debug("Starting daemon polling loop")
        logger.debug(f"Polling interval: {self.config.poll_interval} seconds")
        logger.debug(f"Hibernation check interval: {self.HIBERNATION_INTERVAL} seconds")
        logger.debug(f"Watching statuses: {self.config.watched_statuses}")

        # Initialize project metadata cache on startup
        self._initialize_project_metadata()

        self._running = True
        consecutive_failures = 0

        try:
            while self._running and not self._shutdown_requested:
                # HEALTH CHECK: Validate GitHub API connectivity before polling
                if not self._check_github_connectivity():
                    # GitHub API unreachable - enter hibernation mode
                    if not self._hibernating:
                        self._enter_hibernation("GitHub API unreachable")

                    logger.info(
                        f"Hibernating for {self.HIBERNATION_INTERVAL}s "
                        f"(re-checking connectivity)..."
                    )

                    # Sleep for hibernation interval, then re-check connectivity
                    if self._shutdown_event.wait(timeout=self.HIBERNATION_INTERVAL):
                        break  # Shutdown requested during hibernation
                    continue  # Loop back to health check

                # Connectivity restored or was never lost
                if self._hibernating:
                    self._exit_hibernation()

                # Reset consecutive failures after successful connectivity check
                # (hibernation handles network issues separately)

                # Health check passed - proceed with normal poll cycle
                try:
                    self._poll()
                    consecutive_failures = 0  # Reset on success
                except NetworkError as e:
                    # Network error during poll - will trigger hibernation on next loop
                    logger.warning(f"Network error during poll: {e}")
                    continue  # Loop back to health check
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
        logger.debug("Stopping daemon")
        self._running = False

        # Clean up running workflow labels before executor shutdown
        self.state_manager.cleanup_running_labels()

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

        logger.debug("Daemon stopped")

    def _cleanup_running_labels(self) -> None:
        """Remove running workflow labels. Delegates to StateManager."""
        self.state_manager.cleanup_running_labels()

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
                    self.state_manager.maybe_cleanup(item)

            # Auto-archive issues closed without completion (won't do, duplicate, manual)
            for item in all_items:
                self.state_manager.maybe_archive_closed(item)

            # Clean up worktrees for all closed issues
            for item in all_items:
                self.state_manager.maybe_cleanup_closed(item)

            # Move Validate issues with merged PR to Done
            for item in all_items:
                self.state_manager.maybe_move_to_done(item)

            # Set issues without status to Backlog
            for item in all_items:
                self.state_manager.maybe_set_backlog(item)

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
                    logger.debug(
                        f"YOLO: Skipping Backlog→Research for {key} - yolo label was removed"
                    )
                    continue

                actor = self.ticket_client.get_label_actor(item.repo, item.ticket_id, Labels.YOLO)
                actor_category = check_actor_allowed(
                    actor, self.config.username_self, key, "YOLO", self.config.team_usernames
                )
                if actor_category != ActorCategory.SELF:
                    continue
                logger.info(
                    f"YOLO: Starting auto-progression for {key} from Backlog "
                    f"(label added by allowed user '{actor}')"
                )
                hostname = get_hostname_from_url(item.board_url)
                self.ticket_client.update_item_status(item.item_id, "Research", hostname=hostname)

            # Handle reset label: clear kiln content and move issue to Backlog
            for item in all_items:
                self.reset_handler.maybe_handle_reset(item)

            # Collect items that need workflow execution
            items_to_process: list[TicketItem] = []
            for item in all_items:
                if self.workflow_orchestrator.should_trigger_workflow(item):
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
                future = self.executor.submit(self.workflow_orchestrator.process_item_workflow, item)
                futures[future] = item

            # Log submission - workflows will run asynchronously
            # Results are logged in _on_workflow_complete via add_done_callback
            for future, item in futures.items():
                future.add_done_callback(lambda f, i=item: self._on_workflow_complete(f, i))

            logger.debug("Poll cycle completed")

        except Exception as e:
            logger.error(f"Error fetching project items: {e}", exc_info=True)
            raise

    def _should_yolo_advance(self, item: TicketItem) -> bool:
        """Check if an item should advance via YOLO. Delegates to YoloController."""
        return self.yolo_controller.should_yolo_advance(item)

    def _yolo_advance(self, item: TicketItem) -> None:
        """Advance an item to the next YOLO status. Delegates to YoloController."""
        self.yolo_controller.yolo_advance(item)

    def _has_yolo_label(self, repo: str, issue_number: int) -> bool:
        """Check if issue currently has yolo label. Delegates to YoloController."""
        return self.yolo_controller.has_yolo_label(repo, issue_number)

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
        """Clean up worktree for Done issues. Delegates to StateManager."""
        self.state_manager.maybe_cleanup(item)

    def _maybe_archive_closed(self, item: TicketItem) -> None:
        """Archive closed issues. Delegates to StateManager."""
        self.state_manager.maybe_archive_closed(item)

    def _maybe_cleanup_closed(self, item: TicketItem) -> None:
        """Clean up worktree for closed issues. Delegates to StateManager."""
        self.state_manager.maybe_cleanup_closed(item)

    def _maybe_move_to_done(self, item: TicketItem) -> None:
        """Move issues with merged PRs to Done. Delegates to StateManager."""
        self.state_manager.maybe_move_to_done(item)

    def _maybe_set_backlog(self, item: TicketItem) -> None:
        """Set issues without status to Backlog. Delegates to StateManager."""
        self.state_manager.maybe_set_backlog(item)

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


def main() -> None:
    """Main entry point for the daemon.

    Sets up logging, loads configuration, and runs the daemon.
    """
    try:
        # Load configuration first (needed for log settings)
        config = load_config()

        # Extract org name from first project URL for log masking
        org_name = None
        if config.project_urls:
            org_name = _extract_org_from_url(config.project_urls[0])

        # Setup logging with config (including GHES masking)
        setup_logging(
            log_file=config.log_file,
            log_size=config.log_size,
            log_backups=config.log_backups,
            ghes_logs_mask=config.ghes_logs_mask,
            ghes_host=config.github_enterprise_host,
            org_name=org_name,
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

        # Initialize PagerDuty if configured
        if config.pagerduty_routing_key:
            init_pagerduty(config.pagerduty_routing_key)

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
