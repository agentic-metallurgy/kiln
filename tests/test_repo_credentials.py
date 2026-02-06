"""Unit tests for the repository credentials module."""

import tempfile
from pathlib import Path

import pytest
import yaml

from src.integrations.repo_credentials import (
    CREDENTIALS_CONFIG_PATH,
    DEFAULT_DESTINATION,
    RepoCredentialEntry,
    RepoCredentialsError,
    RepoCredentialsLoadError,
    RepoCredentialsManager,
    parse_repo_url,
)


@pytest.mark.unit
class TestParseRepoUrl:
    """Tests for parse_repo_url helper."""

    def test_full_https_url(self):
        """Test parsing a full https URL."""
        host, owner, repo = parse_repo_url("https://github.com/my-org/api-service")
        assert host == "github.com"
        assert owner == "my-org"
        assert repo == "api-service"

    def test_url_with_trailing_slash(self):
        """Test parsing a URL with trailing slash."""
        host, owner, repo = parse_repo_url("https://github.com/my-org/api-service/")
        assert host == "github.com"
        assert owner == "my-org"
        assert repo == "api-service"

    def test_url_with_extra_path(self):
        """Test parsing a URL with extra path segments (tree/main etc)."""
        host, owner, repo = parse_repo_url(
            "https://github.com/agentic-metallurgy/kiln/tree/main"
        )
        assert host == "github.com"
        assert owner == "agentic-metallurgy"
        assert repo == "kiln"

    def test_url_without_scheme(self):
        """Test parsing a URL without https:// prefix."""
        host, owner, repo = parse_repo_url("github.com/my-org/api-service")
        assert host == "github.com"
        assert owner == "my-org"
        assert repo == "api-service"

    def test_url_without_scheme_with_extra_path(self):
        """Test parsing a schemeless URL with extra path."""
        host, owner, repo = parse_repo_url(
            "github.com/agentic-metallurgy/kiln/tree/main"
        )
        assert host == "github.com"
        assert owner == "agentic-metallurgy"
        assert repo == "kiln"

    def test_ghes_url(self):
        """Test parsing a GitHub Enterprise Server URL."""
        host, owner, repo = parse_repo_url("https://ghes.example.com/org/repo")
        assert host == "ghes.example.com"
        assert owner == "org"
        assert repo == "repo"

    def test_ghes_url_without_scheme(self):
        """Test parsing a GHES URL without scheme."""
        host, owner, repo = parse_repo_url("ghes.example.com/org/repo")
        assert host == "ghes.example.com"
        assert owner == "org"
        assert repo == "repo"

    def test_url_with_dot_git_suffix(self):
        """Test parsing a URL with .git suffix."""
        host, owner, repo = parse_repo_url("https://github.com/my-org/api-service.git")
        assert host == "github.com"
        assert owner == "my-org"
        assert repo == "api-service"

    def test_http_url(self):
        """Test parsing an http:// URL."""
        host, owner, repo = parse_repo_url("http://github.com/my-org/api-service")
        assert host == "github.com"
        assert owner == "my-org"
        assert repo == "api-service"

    def test_empty_string_raises(self):
        """Test that empty string raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            parse_repo_url("")

    def test_whitespace_only_raises(self):
        """Test that whitespace-only string raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            parse_repo_url("   ")

    def test_host_only_raises(self):
        """Test that a URL with only hostname raises ValueError."""
        with pytest.raises(ValueError, match="at least owner/repo"):
            parse_repo_url("https://github.com")

    def test_host_with_one_segment_raises(self):
        """Test that a URL with only one path segment raises ValueError."""
        with pytest.raises(ValueError, match="at least owner/repo"):
            parse_repo_url("https://github.com/only-owner")

    def test_strips_whitespace(self):
        """Test that leading/trailing whitespace is stripped."""
        host, owner, repo = parse_repo_url("  github.com/my-org/api-service  ")
        assert host == "github.com"
        assert owner == "my-org"
        assert repo == "api-service"


@pytest.mark.unit
class TestRepoCredentialEntry:
    """Tests for RepoCredentialEntry dataclass."""

    def test_entry_creation_all_fields(self):
        """Test creating an entry with all fields."""
        entry = RepoCredentialEntry(
            title="My API Service",
            host="github.com",
            owner="my-org",
            repo="api-service",
            credential_path="/home/user/.env",
            destination=".env",
        )
        assert entry.title == "My API Service"
        assert entry.host == "github.com"
        assert entry.owner == "my-org"
        assert entry.repo == "api-service"
        assert entry.credential_path == "/home/user/.env"
        assert entry.destination == ".env"

    def test_entry_creation_custom_destination(self):
        """Test creating an entry with a custom destination."""
        entry = RepoCredentialEntry(
            title="Frontend App",
            host="github.com",
            owner="my-org",
            repo="frontend",
            credential_path="/home/user/frontend/.env.local",
            destination="docker/.env",
        )
        assert entry.destination == "docker/.env"


@pytest.mark.unit
class TestRepoCredentialsManager:
    """Tests for RepoCredentialsManager initialization."""

    def test_manager_initialization_defaults(self):
        """Test manager uses default config path."""
        manager = RepoCredentialsManager()
        assert manager.config_path == CREDENTIALS_CONFIG_PATH
        assert manager._cached_entries is None

    def test_manager_initialization_custom_path(self):
        """Test manager with custom config path."""
        manager = RepoCredentialsManager(config_path="/custom/path.yaml")
        assert manager.config_path == "/custom/path.yaml"


@pytest.mark.unit
class TestRepoCredentialsManagerLoadConfig:
    """Tests for RepoCredentialsManager.load_config()."""

    def test_load_config_file_not_found(self):
        """Test loading when config file doesn't exist."""
        manager = RepoCredentialsManager(config_path="/nonexistent/credentials.yaml")

        result = manager.load_config()

        assert result is None

    def test_load_config_valid_yaml_all_fields(self):
        """Test successfully loading a valid YAML config with all fields."""
        config_data = {
            "repositories": [
                {
                    "title": "My API Service",
                    "repo_url": "https://github.com/my-org/api-service",
                    "credential_path": "/home/user/.env",
                    "destination": "docker/.env",
                }
            ]
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(config_data, f)
            config_path = f.name

        try:
            manager = RepoCredentialsManager(config_path=config_path)
            result = manager.load_config()

            assert result is not None
            assert len(result) == 1
            entry = result[0]
            assert entry.title == "My API Service"
            assert entry.host == "github.com"
            assert entry.owner == "my-org"
            assert entry.repo == "api-service"
            assert entry.credential_path == "/home/user/.env"
            assert entry.destination == "docker/.env"
        finally:
            Path(config_path).unlink()

    def test_load_config_repo_url_without_scheme(self):
        """Test loading config where repo_url has no scheme."""
        config_data = {
            "repositories": [
                {
                    "title": "My API",
                    "repo_url": "github.com/my-org/api",
                    "credential_path": "/home/user/.env",
                }
            ]
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(config_data, f)
            config_path = f.name

        try:
            manager = RepoCredentialsManager(config_path=config_path)
            result = manager.load_config()

            assert result is not None
            assert len(result) == 1
            assert result[0].host == "github.com"
            assert result[0].owner == "my-org"
            assert result[0].repo == "api"
        finally:
            Path(config_path).unlink()

    def test_load_config_repo_url_with_extra_path(self):
        """Test loading config where repo_url has extra path like /tree/main."""
        config_data = {
            "repositories": [
                {
                    "title": "My API",
                    "repo_url": "github.com/my-org/api/tree/main",
                    "credential_path": "/home/user/.env",
                }
            ]
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(config_data, f)
            config_path = f.name

        try:
            manager = RepoCredentialsManager(config_path=config_path)
            result = manager.load_config()

            assert result is not None
            assert result[0].host == "github.com"
            assert result[0].owner == "my-org"
            assert result[0].repo == "api"
        finally:
            Path(config_path).unlink()

    def test_load_config_ghes_repo_url(self):
        """Test loading config with a GHES repo_url."""
        config_data = {
            "repositories": [
                {
                    "title": "GHES Service",
                    "repo_url": "https://ghes.example.com/org/service",
                    "credential_path": "/home/user/.env",
                }
            ]
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(config_data, f)
            config_path = f.name

        try:
            manager = RepoCredentialsManager(config_path=config_path)
            result = manager.load_config()

            assert result is not None
            assert result[0].host == "ghes.example.com"
            assert result[0].owner == "org"
            assert result[0].repo == "service"
        finally:
            Path(config_path).unlink()

    def test_load_config_valid_yaml_default_destination(self):
        """Test loading config where destination defaults to .env."""
        config_data = {
            "repositories": [
                {
                    "title": "My API",
                    "repo_url": "https://github.com/my-org/api",
                    "credential_path": "/home/user/.env",
                }
            ]
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(config_data, f)
            config_path = f.name

        try:
            manager = RepoCredentialsManager(config_path=config_path)
            result = manager.load_config()

            assert result is not None
            assert len(result) == 1
            assert result[0].destination == DEFAULT_DESTINATION
        finally:
            Path(config_path).unlink()

    def test_load_config_multiple_entries(self):
        """Test loading config with multiple repository entries."""
        config_data = {
            "repositories": [
                {
                    "title": "Service A",
                    "repo_url": "https://github.com/org/service-a",
                    "credential_path": "/path/a/.env",
                },
                {
                    "title": "Service B",
                    "repo_url": "https://github.com/org/service-b",
                    "credential_path": "/path/b/.env",
                    "destination": "config/.env",
                },
            ]
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(config_data, f)
            config_path = f.name

        try:
            manager = RepoCredentialsManager(config_path=config_path)
            result = manager.load_config()

            assert result is not None
            assert len(result) == 2
            assert result[0].repo == "service-a"
            assert result[1].repo == "service-b"
            assert result[1].destination == "config/.env"
        finally:
            Path(config_path).unlink()

    def test_load_config_invalid_yaml(self):
        """Test loading an invalid YAML file raises RepoCredentialsLoadError."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("not: valid: yaml: [unclosed")
            config_path = f.name

        try:
            manager = RepoCredentialsManager(config_path=config_path)

            with pytest.raises(RepoCredentialsLoadError) as exc_info:
                manager.load_config()

            assert "Invalid YAML" in str(exc_info.value)
        finally:
            Path(config_path).unlink()

    def test_load_config_not_a_mapping(self):
        """Test loading a YAML file that is a list instead of mapping."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(["item1", "item2"], f)
            config_path = f.name

        try:
            manager = RepoCredentialsManager(config_path=config_path)

            with pytest.raises(RepoCredentialsLoadError) as exc_info:
                manager.load_config()

            assert "must be a YAML mapping" in str(exc_info.value)
        finally:
            Path(config_path).unlink()

    def test_load_config_missing_required_field(self):
        """Test loading config with missing required fields raises error."""
        config_data = {
            "repositories": [
                {
                    "title": "My API",
                    # missing "repo_url" and "credential_path"
                }
            ]
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(config_data, f)
            config_path = f.name

        try:
            manager = RepoCredentialsManager(config_path=config_path)

            with pytest.raises(RepoCredentialsLoadError) as exc_info:
                manager.load_config()

            assert "missing required field" in str(exc_info.value)
        finally:
            Path(config_path).unlink()

    def test_load_config_invalid_repo_url(self):
        """Test loading config with invalid repo_url raises error."""
        config_data = {
            "repositories": [
                {
                    "title": "My API",
                    "repo_url": "https://github.com",
                    "credential_path": "/home/user/.env",
                }
            ]
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(config_data, f)
            config_path = f.name

        try:
            manager = RepoCredentialsManager(config_path=config_path)

            with pytest.raises(RepoCredentialsLoadError) as exc_info:
                manager.load_config()

            assert "invalid repo_url" in str(exc_info.value)
        finally:
            Path(config_path).unlink()

    def test_load_config_non_absolute_credential_path(self):
        """Test loading config with relative credential_path raises error."""
        config_data = {
            "repositories": [
                {
                    "title": "My API",
                    "repo_url": "https://github.com/my-org/api",
                    "credential_path": "relative/path/.env",
                }
            ]
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(config_data, f)
            config_path = f.name

        try:
            manager = RepoCredentialsManager(config_path=config_path)

            with pytest.raises(RepoCredentialsLoadError) as exc_info:
                manager.load_config()

            assert "must be absolute" in str(exc_info.value)
        finally:
            Path(config_path).unlink()

    def test_load_config_empty_file(self):
        """Test loading an empty YAML file returns None."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("")
            config_path = f.name

        try:
            manager = RepoCredentialsManager(config_path=config_path)
            result = manager.load_config()

            assert result is None
        finally:
            Path(config_path).unlink()

    def test_load_config_no_repositories_key(self):
        """Test loading config with no 'repositories' key returns None."""
        config_data = {"other_key": "value"}

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(config_data, f)
            config_path = f.name

        try:
            manager = RepoCredentialsManager(config_path=config_path)
            result = manager.load_config()

            assert result is None
        finally:
            Path(config_path).unlink()

    def test_load_config_repositories_not_a_list(self):
        """Test loading config where 'repositories' is not a list raises error."""
        config_data = {"repositories": "not-a-list"}

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(config_data, f)
            config_path = f.name

        try:
            manager = RepoCredentialsManager(config_path=config_path)

            with pytest.raises(RepoCredentialsLoadError) as exc_info:
                manager.load_config()

            assert "'repositories' must be a list" in str(exc_info.value)
        finally:
            Path(config_path).unlink()

    def test_load_config_entry_not_a_mapping(self):
        """Test loading config where a repository entry is not a dict."""
        config_data = {"repositories": ["not-a-dict"]}

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(config_data, f)
            config_path = f.name

        try:
            manager = RepoCredentialsManager(config_path=config_path)

            with pytest.raises(RepoCredentialsLoadError) as exc_info:
                manager.load_config()

            assert "must be a mapping" in str(exc_info.value)
        finally:
            Path(config_path).unlink()

    def test_load_config_caches_entries(self):
        """Test that load_config caches the result."""
        config_data = {
            "repositories": [
                {
                    "title": "My API",
                    "repo_url": "https://github.com/my-org/api",
                    "credential_path": "/home/user/.env",
                }
            ]
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(config_data, f)
            config_path = f.name

        try:
            manager = RepoCredentialsManager(config_path=config_path)
            result = manager.load_config()

            assert result is not None
            assert manager._cached_entries is result
        finally:
            Path(config_path).unlink()


@pytest.mark.unit
class TestRepoCredentialsManagerHasConfig:
    """Tests for RepoCredentialsManager.has_config()."""

    def test_has_config_no_file(self):
        """Test has_config returns False when file doesn't exist."""
        manager = RepoCredentialsManager(config_path="/nonexistent/credentials.yaml")

        assert manager.has_config() is False

    def test_has_config_valid_config(self):
        """Test has_config returns True when valid config with entries exists."""
        config_data = {
            "repositories": [
                {
                    "title": "My API",
                    "repo_url": "https://github.com/my-org/api",
                    "credential_path": "/home/user/.env",
                }
            ]
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(config_data, f)
            config_path = f.name

        try:
            manager = RepoCredentialsManager(config_path=config_path)
            assert manager.has_config() is True
        finally:
            Path(config_path).unlink()

    def test_has_config_empty_repositories(self):
        """Test has_config returns False when repositories list is empty."""
        config_data = {"repositories": []}

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(config_data, f)
            config_path = f.name

        try:
            manager = RepoCredentialsManager(config_path=config_path)
            # Empty list is falsy, so has_config should return False
            # since load_config returns [] which is falsy
            result = manager.has_config()
            # load_config returns the list; len([]) > 0 is False
            # has_config checks: entries is not None and len(entries) > 0
            assert result is False
        finally:
            Path(config_path).unlink()

    def test_has_config_invalid_yaml(self):
        """Test has_config returns False when YAML is invalid."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("not: valid: yaml: [unclosed")
            config_path = f.name

        try:
            manager = RepoCredentialsManager(config_path=config_path)
            assert manager.has_config() is False
        finally:
            Path(config_path).unlink()


@pytest.mark.unit
class TestRepoCredentialsManagerCopyToWorktree:
    """Tests for RepoCredentialsManager.copy_to_worktree()."""

    def test_copy_to_worktree_successful(self):
        """Test successful copy with matching repo."""
        with tempfile.TemporaryDirectory() as worktree_path:
            # Create a source credential file
            source_dir = Path(worktree_path) / "source"
            source_dir.mkdir()
            source_file = source_dir / ".env"
            source_file.write_text("API_KEY=secret123\nDB_HOST=localhost\n")

            config_data = {
                "repositories": [
                    {
                        "title": "My API",
                        "repo_url": "https://github.com/my-org/api-service",
                        "credential_path": str(source_file),
                    }
                ]
            }

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".yaml", delete=False
            ) as f:
                yaml.dump(config_data, f)
                config_path = f.name

            try:
                manager = RepoCredentialsManager(config_path=config_path)

                dest_dir = Path(worktree_path) / "dest_worktree"
                dest_dir.mkdir()

                result = manager.copy_to_worktree(
                    str(dest_dir), "github.com/my-org/api-service"
                )

                assert result is not None
                dest_file = dest_dir / ".env"
                assert dest_file.exists()
                assert dest_file.read_text() == "API_KEY=secret123\nDB_HOST=localhost\n"
            finally:
                Path(config_path).unlink()

    def test_copy_to_worktree_no_matching_entry(self):
        """Test copy returns None when no matching repo entry exists."""
        config_data = {
            "repositories": [
                {
                    "title": "Other Service",
                    "repo_url": "https://github.com/other-org/other-service",
                    "credential_path": "/home/user/.env",
                }
            ]
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(config_data, f)
            config_path = f.name

        try:
            manager = RepoCredentialsManager(config_path=config_path)

            with tempfile.TemporaryDirectory() as worktree_path:
                result = manager.copy_to_worktree(
                    worktree_path, "github.com/my-org/api-service"
                )

                assert result is None
        finally:
            Path(config_path).unlink()

    def test_copy_to_worktree_source_not_found(self):
        """Test copy returns None when source credential file doesn't exist."""
        config_data = {
            "repositories": [
                {
                    "title": "My API",
                    "repo_url": "https://github.com/my-org/api-service",
                    "credential_path": "/nonexistent/path/.env",
                }
            ]
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(config_data, f)
            config_path = f.name

        try:
            manager = RepoCredentialsManager(config_path=config_path)

            with tempfile.TemporaryDirectory() as worktree_path:
                result = manager.copy_to_worktree(
                    worktree_path, "github.com/my-org/api-service"
                )

                assert result is None
        finally:
            Path(config_path).unlink()

    def test_copy_to_worktree_subdirectory_destination(self):
        """Test copy creates parent directories for subdirectory destinations."""
        with tempfile.TemporaryDirectory() as worktree_path:
            # Create source file
            source_dir = Path(worktree_path) / "source"
            source_dir.mkdir()
            source_file = source_dir / ".env"
            source_file.write_text("SECRET=value\n")

            config_data = {
                "repositories": [
                    {
                        "title": "My API",
                        "repo_url": "https://github.com/my-org/api-service",
                        "credential_path": str(source_file),
                        "destination": "docker/config/.env",
                    }
                ]
            }

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".yaml", delete=False
            ) as f:
                yaml.dump(config_data, f)
                config_path = f.name

            try:
                manager = RepoCredentialsManager(config_path=config_path)

                dest_dir = Path(worktree_path) / "dest_worktree"
                dest_dir.mkdir()

                result = manager.copy_to_worktree(
                    str(dest_dir), "github.com/my-org/api-service"
                )

                assert result is not None
                dest_file = dest_dir / "docker" / "config" / ".env"
                assert dest_file.exists()
                assert dest_file.read_text() == "SECRET=value\n"
            finally:
                Path(config_path).unlink()

    def test_copy_to_worktree_matches_full_host_owner_repo(self):
        """Test repo matching uses full host/owner/repo for deterministic matching."""
        with tempfile.TemporaryDirectory() as worktree_path:
            source_dir = Path(worktree_path) / "source"
            source_dir.mkdir()
            source_file = source_dir / ".env"
            source_file.write_text("KEY=value\n")

            config_data = {
                "repositories": [
                    {
                        "title": "My API",
                        "repo_url": "https://github.com/my-org/api-service",
                        "credential_path": str(source_file),
                    }
                ]
            }

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".yaml", delete=False
            ) as f:
                yaml.dump(config_data, f)
                config_path = f.name

            try:
                manager = RepoCredentialsManager(config_path=config_path)

                dest_dir = Path(worktree_path) / "dest_worktree"
                dest_dir.mkdir()

                # Should match with full host/owner/repo format
                result = manager.copy_to_worktree(
                    str(dest_dir), "github.com/my-org/api-service"
                )
                assert result is not None
            finally:
                Path(config_path).unlink()

    def test_copy_to_worktree_ghes_does_not_match_github_com(self):
        """Test that a GHES entry does not match a github.com repo identifier."""
        config_data = {
            "repositories": [
                {
                    "title": "GHES Service",
                    "repo_url": "https://ghes.example.com/my-org/api-service",
                    "credential_path": "/home/user/.env",
                }
            ]
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(config_data, f)
            config_path = f.name

        try:
            manager = RepoCredentialsManager(config_path=config_path)

            with tempfile.TemporaryDirectory() as worktree_path:
                # Same owner/repo but different host — should NOT match
                result = manager.copy_to_worktree(
                    worktree_path, "github.com/my-org/api-service"
                )
                assert result is None
        finally:
            Path(config_path).unlink()

    def test_copy_to_worktree_no_config(self):
        """Test copy returns None when no config exists."""
        manager = RepoCredentialsManager(config_path="/nonexistent/credentials.yaml")

        with tempfile.TemporaryDirectory() as worktree_path:
            result = manager.copy_to_worktree(
                worktree_path, "github.com/my-org/api-service"
            )

            assert result is None

    def test_copy_to_worktree_uses_cache(self):
        """Test that copy_to_worktree uses cached entries on second call."""
        with tempfile.TemporaryDirectory() as worktree_path:
            source_dir = Path(worktree_path) / "source"
            source_dir.mkdir()
            source_file = source_dir / ".env"
            source_file.write_text("KEY=value\n")

            config_data = {
                "repositories": [
                    {
                        "title": "My API",
                        "repo_url": "https://github.com/my-org/api-service",
                        "credential_path": str(source_file),
                    }
                ]
            }

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".yaml", delete=False
            ) as f:
                yaml.dump(config_data, f)
                config_path = f.name

            try:
                manager = RepoCredentialsManager(config_path=config_path)

                # First call loads and caches
                dest1 = Path(worktree_path) / "dest1"
                dest1.mkdir()
                result1 = manager.copy_to_worktree(
                    str(dest1), "github.com/my-org/api-service"
                )
                assert result1 is not None

                # Delete config file — second call should still work from cache
                Path(config_path).unlink()

                dest2 = Path(worktree_path) / "dest2"
                dest2.mkdir()
                result2 = manager.copy_to_worktree(
                    str(dest2), "github.com/my-org/api-service"
                )
                assert result2 is not None
            except Exception:
                # Ensure cleanup even if test fails
                if Path(config_path).exists():
                    Path(config_path).unlink()
                raise


@pytest.mark.unit
class TestRepoCredentialsManagerClearCache:
    """Tests for RepoCredentialsManager.clear_cache()."""

    def test_clear_cache_resets_entries(self):
        """Test that clear_cache resets the cached entries to None."""
        config_data = {
            "repositories": [
                {
                    "title": "My API",
                    "repo_url": "https://github.com/my-org/api",
                    "credential_path": "/home/user/.env",
                }
            ]
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(config_data, f)
            config_path = f.name

        try:
            manager = RepoCredentialsManager(config_path=config_path)
            manager.load_config()

            assert manager._cached_entries is not None

            manager.clear_cache()

            assert manager._cached_entries is None
        finally:
            Path(config_path).unlink()

    def test_clear_cache_when_already_none(self):
        """Test that clear_cache works even when cache is already None."""
        manager = RepoCredentialsManager(config_path="/nonexistent/path.yaml")
        assert manager._cached_entries is None

        # Should not raise
        manager.clear_cache()
        assert manager._cached_entries is None


@pytest.mark.unit
class TestRepoCredentialsExceptions:
    """Tests for repo credentials exception classes."""

    def test_repo_credentials_error_is_exception(self):
        """Test RepoCredentialsError is an Exception."""
        assert issubclass(RepoCredentialsError, Exception)

    def test_repo_credentials_load_error_is_credentials_error(self):
        """Test RepoCredentialsLoadError is a RepoCredentialsError."""
        assert issubclass(RepoCredentialsLoadError, RepoCredentialsError)

    def test_repo_credentials_error_message(self):
        """Test RepoCredentialsError stores message."""
        error = RepoCredentialsError("test message")
        assert str(error) == "test message"

    def test_repo_credentials_load_error_message(self):
        """Test RepoCredentialsLoadError stores message."""
        error = RepoCredentialsLoadError("load failed")
        assert str(error) == "load failed"


@pytest.mark.unit
class TestConstants:
    """Tests for module constants."""

    def test_credentials_config_path(self):
        """Test the default credentials config path."""
        assert CREDENTIALS_CONFIG_PATH == ".kiln/credentials.yaml"

    def test_default_destination(self):
        """Test the default destination for credential files."""
        assert DEFAULT_DESTINATION == ".env"
