"""Azure OAuth 2.0 ROPC authentication module.

This module provides Azure Entra ID (formerly Azure AD) authentication
using the Resource Owner Password Credentials (ROPC) flow for service-to-service
communication with MCP servers.
"""

import contextlib
import logging
import threading
import time
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

# Token endpoint template for Azure Entra ID
TOKEN_ENDPOINT = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"

# Default scope for Microsoft Graph API
DEFAULT_SCOPE = "https://graph.microsoft.com/.default"

# Refresh buffer: proactively refresh tokens 5 minutes before expiry
EXPIRY_BUFFER_SECONDS = 300


class AzureOAuthError(Exception):
    """Base exception for Azure OAuth errors."""

    pass


class AzureTokenRequestError(AzureOAuthError):
    """Error during token request to Azure."""

    def __init__(self, message: str, status_code: int | None = None, error_code: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


@dataclass
class TokenResponse:
    """Represents an Azure OAuth token response."""

    access_token: str
    expires_in: int  # Seconds until expiration
    token_type: str
    expires_at: float  # Unix timestamp when token expires


class AzureOAuthClient:
    """Azure OAuth 2.0 client using ROPC flow.

    This client handles token retrieval and caching for Azure Entra ID
    authentication using the Resource Owner Password Credentials flow.

    Thread-safe: Multiple threads can safely call get_token() concurrently.

    Attributes:
        tenant_id: Azure tenant ID (directory ID)
        client_id: Azure application (client) ID
        username: Service account username (email)
        password: Service account password
        scope: OAuth scope (defaults to Microsoft Graph)
    """

    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        username: str,
        password: str,
        scope: str | None = None,
    ):
        """Initialize the Azure OAuth client.

        Args:
            tenant_id: Azure tenant ID (directory ID)
            client_id: Azure application (client) ID
            username: Service account username (email)
            password: Service account password
            scope: OAuth scope (defaults to Microsoft Graph if not specified)
        """
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.username = username
        self.password = password
        self.scope = scope or DEFAULT_SCOPE

        self._token: TokenResponse | None = None
        self._lock = threading.Lock()

    def get_token(self) -> str:
        """Get a valid bearer token, refreshing if needed.

        This method is thread-safe. Multiple threads can call this method
        concurrently and will receive valid tokens.

        Returns:
            A valid bearer token string.

        Raises:
            AzureTokenRequestError: If token request fails.
        """
        with self._lock:
            if self._is_token_valid() and self._token is not None:
                return self._token.access_token

            # Token is missing, expired, or about to expire - refresh it
            logger.debug("Refreshing Azure OAuth token")
            self._token = self._request_token()
            return self._token.access_token

    def _is_token_valid(self) -> bool:
        """Check if the current token is valid and not near expiry.

        Returns:
            True if token exists and won't expire within the buffer period.
        """
        if self._token is None:
            return False

        # Check if token will expire within the buffer period
        time_until_expiry = self._token.expires_at - time.time()
        return time_until_expiry > EXPIRY_BUFFER_SECONDS

    def _request_token(self) -> TokenResponse:
        """Request a new token from Azure.

        Returns:
            TokenResponse with the new token and expiry info.

        Raises:
            AzureTokenRequestError: If the token request fails.
        """
        url = TOKEN_ENDPOINT.format(tenant_id=self.tenant_id)

        data = {
            "grant_type": "password",
            "client_id": self.client_id,
            "username": self.username,
            "password": self.password,
            "scope": self.scope,
        }

        try:
            response = requests.post(
                url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )
        except requests.RequestException as e:
            logger.error(f"Azure OAuth token request failed: {e}")
            raise AzureTokenRequestError(f"Network error during token request: {e}") from e

        if response.status_code != 200:
            error_data = {}
            with contextlib.suppress(ValueError):
                error_data = response.json()

            error_code = error_data.get("error", "unknown_error")
            error_description = error_data.get("error_description", f"HTTP {response.status_code}")

            # Log without including sensitive details
            logger.error(
                f"Azure OAuth token request failed: {error_code} - Status: {response.status_code}"
            )

            raise AzureTokenRequestError(
                f"Token request failed: {error_description}",
                status_code=response.status_code,
                error_code=error_code,
            )

        try:
            token_data = response.json()
        except ValueError as e:
            raise AzureTokenRequestError("Invalid JSON in token response") from e

        access_token = token_data.get("access_token")
        if not access_token:
            raise AzureTokenRequestError("No access_token in response")

        expires_in = token_data.get("expires_in", 3600)  # Default 1 hour
        token_type = token_data.get("token_type", "Bearer")

        # Calculate absolute expiry time
        expires_at = time.time() + expires_in

        logger.info(f"Azure OAuth token acquired, expires in {expires_in} seconds")

        return TokenResponse(
            access_token=access_token,
            expires_in=expires_in,
            token_type=token_type,
            expires_at=expires_at,
        )

    def clear_token(self) -> None:
        """Clear the cached token.

        This forces the next get_token() call to request a new token.
        Useful for handling token invalidation scenarios.
        """
        with self._lock:
            self._token = None
            logger.debug("Azure OAuth token cache cleared")

    @property
    def has_token(self) -> bool:
        """Check if a token is currently cached (regardless of validity).

        Returns:
            True if a token is cached.
        """
        return self._token is not None

    @property
    def token_expires_at(self) -> float | None:
        """Get the expiry timestamp of the current token.

        Returns:
            Unix timestamp when the token expires, or None if no token.
        """
        return self._token.expires_at if self._token else None
