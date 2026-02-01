"""Unit tests for the Azure OAuth module."""

import threading
import time
from unittest.mock import MagicMock, patch

import pytest
import requests

from src.integrations.azure_oauth import (
    DEFAULT_SCOPE,
    EXPIRY_BUFFER_SECONDS,
    TOKEN_ENDPOINT,
    AzureOAuthClient,
    AzureOAuthError,
    AzureTokenRequestError,
    TokenResponse,
)


@pytest.mark.unit
class TestTokenResponse:
    """Tests for TokenResponse dataclass."""

    def test_token_response_creation(self):
        """Test creating a TokenResponse instance."""
        response = TokenResponse(
            access_token="test_token",
            expires_in=3600,
            token_type="Bearer",
            expires_at=1234567890.0,
        )

        assert response.access_token == "test_token"
        assert response.expires_in == 3600
        assert response.token_type == "Bearer"
        assert response.expires_at == 1234567890.0


@pytest.mark.unit
class TestAzureOAuthClient:
    """Tests for AzureOAuthClient class."""

    def test_client_initialization(self):
        """Test client initialization with required parameters."""
        client = AzureOAuthClient(
            tenant_id="tenant-123",
            client_id="client-456",
            username="user@example.com",
            password="secret",
        )

        assert client.tenant_id == "tenant-123"
        assert client.client_id == "client-456"
        assert client.username == "user@example.com"
        assert client.password == "secret"
        assert client.scope == DEFAULT_SCOPE

    def test_client_initialization_custom_scope(self):
        """Test client initialization with custom scope."""
        client = AzureOAuthClient(
            tenant_id="tenant-123",
            client_id="client-456",
            username="user@example.com",
            password="secret",
            scope="https://custom.api/.default",
        )

        assert client.scope == "https://custom.api/.default"

    def test_client_initialization_none_scope_uses_default(self):
        """Test None scope falls back to default."""
        client = AzureOAuthClient(
            tenant_id="tenant-123",
            client_id="client-456",
            username="user@example.com",
            password="secret",
            scope=None,
        )

        assert client.scope == DEFAULT_SCOPE

    def test_has_token_initially_false(self):
        """Test has_token is False when no token is cached."""
        client = AzureOAuthClient(
            tenant_id="tenant-123",
            client_id="client-456",
            username="user@example.com",
            password="secret",
        )

        assert client.has_token is False

    def test_token_expires_at_initially_none(self):
        """Test token_expires_at is None when no token is cached."""
        client = AzureOAuthClient(
            tenant_id="tenant-123",
            client_id="client-456",
            username="user@example.com",
            password="secret",
        )

        assert client.token_expires_at is None


@pytest.mark.unit
class TestAzureOAuthClientTokenRequest:
    """Tests for AzureOAuthClient token request functionality."""

    @patch("src.integrations.azure_oauth.requests.post")
    def test_get_token_success(self, mock_post):
        """Test successful token retrieval."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "test_access_token",
            "expires_in": 3600,
            "token_type": "Bearer",
        }
        mock_post.return_value = mock_response

        client = AzureOAuthClient(
            tenant_id="tenant-123",
            client_id="client-456",
            username="user@example.com",
            password="secret",
        )

        token = client.get_token()

        assert token == "test_access_token"
        assert client.has_token is True
        mock_post.assert_called_once()

    @patch("src.integrations.azure_oauth.requests.post")
    def test_get_token_uses_correct_endpoint(self, mock_post):
        """Test token request uses correct Azure endpoint."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "test_token",
            "expires_in": 3600,
            "token_type": "Bearer",
        }
        mock_post.return_value = mock_response

        client = AzureOAuthClient(
            tenant_id="my-tenant-id",
            client_id="client-456",
            username="user@example.com",
            password="secret",
        )

        client.get_token()

        expected_url = TOKEN_ENDPOINT.format(tenant_id="my-tenant-id")
        call_args = mock_post.call_args
        assert call_args[0][0] == expected_url

    @patch("src.integrations.azure_oauth.requests.post")
    def test_get_token_sends_correct_data(self, mock_post):
        """Test token request sends correct form data."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "test_token",
            "expires_in": 3600,
            "token_type": "Bearer",
        }
        mock_post.return_value = mock_response

        client = AzureOAuthClient(
            tenant_id="tenant-123",
            client_id="client-456",
            username="user@example.com",
            password="secret-password",
            scope="https://api.example.com/.default",
        )

        client.get_token()

        call_args = mock_post.call_args
        data = call_args[1]["data"]
        assert data["grant_type"] == "password"
        assert data["client_id"] == "client-456"
        assert data["username"] == "user@example.com"
        assert data["password"] == "secret-password"
        assert data["scope"] == "https://api.example.com/.default"

    @patch("src.integrations.azure_oauth.requests.post")
    def test_get_token_caches_token(self, mock_post):
        """Test token is cached and reused."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "cached_token",
            "expires_in": 3600,
            "token_type": "Bearer",
        }
        mock_post.return_value = mock_response

        client = AzureOAuthClient(
            tenant_id="tenant-123",
            client_id="client-456",
            username="user@example.com",
            password="secret",
        )

        # First call - should make request
        token1 = client.get_token()
        # Second call - should use cache
        token2 = client.get_token()

        assert token1 == "cached_token"
        assert token2 == "cached_token"
        assert mock_post.call_count == 1  # Only one HTTP request

    @patch("src.integrations.azure_oauth.requests.post")
    @patch("src.integrations.azure_oauth.time.time")
    def test_get_token_refreshes_when_expired(self, mock_time, mock_post):
        """Test token is refreshed when expired."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new_token",
            "expires_in": 3600,
            "token_type": "Bearer",
        }
        mock_post.return_value = mock_response

        client = AzureOAuthClient(
            tenant_id="tenant-123",
            client_id="client-456",
            username="user@example.com",
            password="secret",
        )

        # First call at time 1000
        mock_time.return_value = 1000
        token1 = client.get_token()

        # Second call when token is about to expire (within buffer)
        # Token expires at 1000 + 3600 = 4600
        # Buffer is 300 seconds, so 4600 - 300 = 4300
        mock_time.return_value = 4301  # Just past the buffer threshold
        token2 = client.get_token()

        assert token1 == "new_token"
        assert token2 == "new_token"
        assert mock_post.call_count == 2  # Two HTTP requests

    @patch("src.integrations.azure_oauth.requests.post")
    @patch("src.integrations.azure_oauth.time.time")
    def test_get_token_uses_cache_within_buffer(self, mock_time, mock_post):
        """Test token uses cache when not yet within expiry buffer."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "cached_token",
            "expires_in": 3600,
            "token_type": "Bearer",
        }
        mock_post.return_value = mock_response

        client = AzureOAuthClient(
            tenant_id="tenant-123",
            client_id="client-456",
            username="user@example.com",
            password="secret",
        )

        # First call at time 1000
        mock_time.return_value = 1000
        token1 = client.get_token()

        # Second call still within valid period
        # Token expires at 1000 + 3600 = 4600
        # Buffer is 300 seconds, so 4600 - 300 = 4300
        mock_time.return_value = 4299  # Just before buffer threshold
        token2 = client.get_token()

        assert token1 == "cached_token"
        assert token2 == "cached_token"
        assert mock_post.call_count == 1  # Only one HTTP request


@pytest.mark.unit
class TestAzureOAuthClientErrorHandling:
    """Tests for AzureOAuthClient error handling."""

    @patch("src.integrations.azure_oauth.requests.post")
    def test_get_token_network_error(self, mock_post):
        """Test handling of network errors."""
        mock_post.side_effect = requests.RequestException("Connection failed")

        client = AzureOAuthClient(
            tenant_id="tenant-123",
            client_id="client-456",
            username="user@example.com",
            password="secret",
        )

        with pytest.raises(AzureTokenRequestError) as exc_info:
            client.get_token()

        assert "Network error" in str(exc_info.value)

    @patch("src.integrations.azure_oauth.requests.post")
    def test_get_token_http_error(self, mock_post):
        """Test handling of HTTP error responses."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "error": "invalid_grant",
            "error_description": "Invalid credentials",
        }
        mock_post.return_value = mock_response

        client = AzureOAuthClient(
            tenant_id="tenant-123",
            client_id="client-456",
            username="user@example.com",
            password="secret",
        )

        with pytest.raises(AzureTokenRequestError) as exc_info:
            client.get_token()

        assert exc_info.value.status_code == 400
        assert exc_info.value.error_code == "invalid_grant"
        assert "Invalid credentials" in str(exc_info.value)

    @patch("src.integrations.azure_oauth.requests.post")
    def test_get_token_http_error_non_json_response(self, mock_post):
        """Test handling of HTTP error with non-JSON response."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.side_effect = ValueError("No JSON")
        mock_post.return_value = mock_response

        client = AzureOAuthClient(
            tenant_id="tenant-123",
            client_id="client-456",
            username="user@example.com",
            password="secret",
        )

        with pytest.raises(AzureTokenRequestError) as exc_info:
            client.get_token()

        assert exc_info.value.status_code == 500
        assert exc_info.value.error_code == "unknown_error"

    @patch("src.integrations.azure_oauth.requests.post")
    def test_get_token_invalid_json_response(self, mock_post):
        """Test handling of invalid JSON in success response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_post.return_value = mock_response

        client = AzureOAuthClient(
            tenant_id="tenant-123",
            client_id="client-456",
            username="user@example.com",
            password="secret",
        )

        with pytest.raises(AzureTokenRequestError) as exc_info:
            client.get_token()

        assert "Invalid JSON" in str(exc_info.value)

    @patch("src.integrations.azure_oauth.requests.post")
    def test_get_token_missing_access_token(self, mock_post):
        """Test handling of response missing access_token."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "expires_in": 3600,
            "token_type": "Bearer",
            # Missing access_token
        }
        mock_post.return_value = mock_response

        client = AzureOAuthClient(
            tenant_id="tenant-123",
            client_id="client-456",
            username="user@example.com",
            password="secret",
        )

        with pytest.raises(AzureTokenRequestError) as exc_info:
            client.get_token()

        assert "No access_token" in str(exc_info.value)

    @patch("src.integrations.azure_oauth.requests.post")
    def test_get_token_default_expires_in(self, mock_post):
        """Test default expires_in when not in response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "test_token",
            # Missing expires_in - should default to 3600
        }
        mock_post.return_value = mock_response

        client = AzureOAuthClient(
            tenant_id="tenant-123",
            client_id="client-456",
            username="user@example.com",
            password="secret",
        )

        token = client.get_token()

        assert token == "test_token"
        # Token should still be cached successfully
        assert client.has_token is True


@pytest.mark.unit
class TestAzureOAuthClientClearToken:
    """Tests for AzureOAuthClient clear_token functionality."""

    @patch("src.integrations.azure_oauth.requests.post")
    def test_clear_token(self, mock_post):
        """Test clear_token removes cached token."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "test_token",
            "expires_in": 3600,
            "token_type": "Bearer",
        }
        mock_post.return_value = mock_response

        client = AzureOAuthClient(
            tenant_id="tenant-123",
            client_id="client-456",
            username="user@example.com",
            password="secret",
        )

        # Get token first
        client.get_token()
        assert client.has_token is True

        # Clear token
        client.clear_token()
        assert client.has_token is False
        assert client.token_expires_at is None

    @patch("src.integrations.azure_oauth.requests.post")
    def test_clear_token_forces_refresh(self, mock_post):
        """Test clear_token forces a new token request on next get_token."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new_token",
            "expires_in": 3600,
            "token_type": "Bearer",
        }
        mock_post.return_value = mock_response

        client = AzureOAuthClient(
            tenant_id="tenant-123",
            client_id="client-456",
            username="user@example.com",
            password="secret",
        )

        # Get token twice without clearing - should only make one request
        client.get_token()
        client.get_token()
        assert mock_post.call_count == 1

        # Clear token and get again - should make a new request
        client.clear_token()
        client.get_token()
        assert mock_post.call_count == 2


@pytest.mark.unit
class TestAzureOAuthClientThreadSafety:
    """Tests for AzureOAuthClient thread safety."""

    @patch("src.integrations.azure_oauth.requests.post")
    def test_concurrent_get_token_calls(self, mock_post):
        """Test concurrent get_token calls are thread-safe."""
        call_count = 0
        call_lock = threading.Lock()

        def mock_request(*args, **kwargs):
            nonlocal call_count
            with call_lock:
                call_count += 1
            # Simulate network delay
            time.sleep(0.01)
            response = MagicMock()
            response.status_code = 200
            response.json.return_value = {
                "access_token": "concurrent_token",
                "expires_in": 3600,
                "token_type": "Bearer",
            }
            return response

        mock_post.side_effect = mock_request

        client = AzureOAuthClient(
            tenant_id="tenant-123",
            client_id="client-456",
            username="user@example.com",
            password="secret",
        )

        results = []
        errors = []

        def get_token_thread():
            try:
                token = client.get_token()
                results.append(token)
            except Exception as e:
                errors.append(e)

        # Start multiple threads simultaneously
        threads = [threading.Thread(target=get_token_thread) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All threads should get the same token
        assert len(errors) == 0
        assert len(results) == 10
        assert all(token == "concurrent_token" for token in results)

        # Due to thread safety, only a small number of requests should be made
        # (ideally 1, but race conditions might cause a few more)
        assert call_count <= 3  # Allow some slack for race conditions


@pytest.mark.unit
class TestAzureOAuthExceptions:
    """Tests for Azure OAuth exception classes."""

    def test_azure_oauth_error_base(self):
        """Test AzureOAuthError is base exception."""
        error = AzureOAuthError("Test error")
        assert str(error) == "Test error"
        assert isinstance(error, Exception)

    def test_azure_token_request_error(self):
        """Test AzureTokenRequestError with all attributes."""
        error = AzureTokenRequestError(
            "Request failed",
            status_code=401,
            error_code="invalid_client",
        )

        assert str(error) == "Request failed"
        assert error.status_code == 401
        assert error.error_code == "invalid_client"

    def test_azure_token_request_error_minimal(self):
        """Test AzureTokenRequestError with only message."""
        error = AzureTokenRequestError("Simple error")

        assert str(error) == "Simple error"
        assert error.status_code is None
        assert error.error_code is None

    def test_azure_token_request_error_is_azure_oauth_error(self):
        """Test AzureTokenRequestError inherits from AzureOAuthError."""
        error = AzureTokenRequestError("Test")
        assert isinstance(error, AzureOAuthError)


@pytest.mark.unit
class TestConstants:
    """Tests for module constants."""

    def test_token_endpoint_template(self):
        """Test TOKEN_ENDPOINT is valid template."""
        endpoint = TOKEN_ENDPOINT.format(tenant_id="test-tenant")
        assert endpoint == "https://login.microsoftonline.com/test-tenant/oauth2/v2.0/token"

    def test_default_scope(self):
        """Test DEFAULT_SCOPE value."""
        assert DEFAULT_SCOPE == "https://graph.microsoft.com/.default"

    def test_expiry_buffer_seconds(self):
        """Test EXPIRY_BUFFER_SECONDS is 5 minutes."""
        assert EXPIRY_BUFFER_SECONDS == 300
