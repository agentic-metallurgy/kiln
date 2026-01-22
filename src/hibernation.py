"""Hibernation mode management for the daemon.

This module provides the Hibernation class that manages network connectivity
monitoring and hibernation state for the daemon. When GitHub API connectivity
fails, the daemon enters hibernation mode and periodically re-checks until
connectivity is restored.
"""

from src.daemon_utils import get_hostname_from_url
from src.logger import get_logger
from src.pagerduty import resolve_hibernation_alert, trigger_hibernation_alert

logger = get_logger(__name__)


class Hibernation:
    """Manages hibernation state and connectivity checking.

    When the daemon cannot reach GitHub APIs due to network issues, it enters
    hibernation mode. This class encapsulates the hibernation state management
    and connectivity verification logic.
    """

    def __init__(
        self,
        ticket_client,
        project_urls: list[str],
        hibernation_interval: int = 300,
    ) -> None:
        """Initialize hibernation manager.

        Args:
            ticket_client: GitHub ticket client for connectivity checks
            project_urls: List of project URLs to extract hostnames from
            hibernation_interval: Seconds to wait between connectivity checks (default 300)
        """
        self.ticket_client = ticket_client
        self.project_urls = project_urls
        self.hibernation_interval = hibernation_interval
        self._hibernating = False
        logger.debug(
            f"Hibernation manager initialized (interval={hibernation_interval}s, "
            f"urls={len(project_urls)})"
        )

    @property
    def is_hibernating(self) -> bool:
        """Return True if currently in hibernation mode."""
        return self._hibernating

    def enter_hibernation(self, reason: str) -> None:
        """Enter hibernation mode due to network connectivity issues.

        When hibernating, the daemon pauses polling and re-checks connectivity
        every hibernation_interval seconds until the connection is restored.

        Args:
            reason: Description of why hibernation was triggered (e.g., network error message)
        """
        if not self._hibernating:
            self._hibernating = True
            logger.warning(f"Entering hibernation mode: {reason}")
            logger.warning(
                f"Daemon will re-check connectivity every {self.hibernation_interval} seconds"
            )
            # Trigger PagerDuty alert if configured
            trigger_hibernation_alert(reason, self.project_urls)

    def exit_hibernation(self) -> None:
        """Exit hibernation mode after connectivity is restored.

        Logs the transition and resets the hibernation flag so normal
        polling can resume.
        """
        if self._hibernating:
            self._hibernating = False
            logger.info("Exiting hibernation mode: connectivity restored")
            # Resolve PagerDuty alert if configured
            resolve_hibernation_alert()

    def check_connectivity(self) -> bool:
        """Check if GitHub API is reachable for all configured project hosts.

        Performs a lightweight connectivity check by calling validate_connection()
        on each unique hostname extracted from configured project URLs. This is
        used at the top of the main polling loop to detect network issues before
        attempting any operations.

        Returns:
            True if all configured GitHub hosts are reachable.
            False if any host is unreachable due to network errors.

        Note:
            This method catches NetworkError exceptions from the ticket client
            and returns False. Other exceptions (auth errors, etc.) are allowed
            to propagate since they indicate configuration issues, not transient
            network problems.
        """
        # Import here to avoid circular imports
        from src.ticket_clients.base import NetworkError

        # Extract unique hostnames from project URLs
        hostnames: set[str] = set()
        for url in self.project_urls:
            hostname = get_hostname_from_url(url)
            hostnames.add(hostname)

        if not hostnames:
            logger.warning("No hostnames found in project URLs, skipping connectivity check")
            return True

        # Check connectivity for each unique hostname
        for hostname in sorted(hostnames):
            try:
                self.ticket_client.validate_connection(hostname)
            except NetworkError as e:
                logger.warning(f"GitHub API unreachable for {hostname}: {e}")
                return False
            except Exception as e:
                # Auth errors and other config issues should be logged but not
                # trigger hibernation - they require manual intervention
                logger.error(f"Connectivity check failed for {hostname}: {e}")
                # Return True to skip hibernation - this isn't a network issue
                return True

        return True
