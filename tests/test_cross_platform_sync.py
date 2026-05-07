"""Tests for cross-platform synchronization functionality."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from pipery_tooling.cross_platform_sync import (
    GitLabAPI,
    BitbucketAPI,
    RepositorySynchronizer,
    SyncReport,
)


class GitLabAPITests:
    """Tests for GitLab API client."""

    def test_init_with_token(self):
        """Test initialization with explicit token."""
        api = GitLabAPI(token="test-token")
        assert api.token == "test-token"

    def test_init_without_token_raises(self):
        """Test initialization fails without token."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="GitLab token not provided"):
                GitLabAPI()

    @patch("pipery_tooling.cross_platform_sync.requests.get")
    def test_get_project_found(self, mock_get):
        """Test getting existing project."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": 1, "name": "test-project"}
        mock_get.return_value = mock_response

        api = GitLabAPI(token="test-token")
        result = api.get_project("test-project")

        assert result == {"id": 1, "name": "test-project"}
        mock_get.assert_called_once()

    @patch("pipery_tooling.cross_platform_sync.requests.get")
    def test_get_project_not_found(self, mock_get):
        """Test getting non-existent project."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        api = GitLabAPI(token="test-token")
        result = api.get_project("nonexistent")

        assert result is None

    @patch("pipery_tooling.cross_platform_sync.requests.post")
    def test_create_project(self, mock_post):
        """Test creating project."""
        mock_response = Mock()
        mock_response.json.return_value = {"id": 1, "name": "new-project"}
        mock_post.return_value = mock_response

        api = GitLabAPI(token="test-token")
        result = api.create_project(
            name="new-project",
            description="Test project",
            visibility="public",
        )

        assert result == {"id": 1, "name": "new-project"}
        mock_post.assert_called_once()


class BitbucketAPITests:
    """Tests for Bitbucket API client."""

    def test_init_with_token(self):
        """Test initialization with explicit token."""
        api = BitbucketAPI(workspace="test-workspace", token="test-token")
        assert api.token == "test-token"
        assert api.workspace == "test-workspace"

    def test_init_without_token_raises(self):
        """Test initialization fails without token."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="Bitbucket token not provided"):
                BitbucketAPI(workspace="test-workspace")

    @patch("pipery_tooling.cross_platform_sync.requests.get")
    def test_get_repository_found(self, mock_get):
        """Test getting existing repository."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"name": "test-repo"}
        mock_get.return_value = mock_response

        api = BitbucketAPI(workspace="test-workspace", token="test-token")
        result = api.get_repository("test-repo")

        assert result == {"name": "test-repo"}

    @patch("pipery_tooling.cross_platform_sync.requests.get")
    def test_get_repository_not_found(self, mock_get):
        """Test getting non-existent repository."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        api = BitbucketAPI(workspace="test-workspace", token="test-token")
        result = api.get_repository("nonexistent")

        assert result is None

    @patch("pipery_tooling.cross_platform_sync.requests.post")
    def test_create_repository(self, mock_post):
        """Test creating repository."""
        mock_response = Mock()
        mock_response.json.return_value = {"name": "new-repo"}
        mock_post.return_value = mock_response

        api = BitbucketAPI(workspace="test-workspace", token="test-token")
        result = api.create_repository(
            repo_slug="new-repo",
            description="Test repo",
            is_private=False,
        )

        assert result == {"name": "new-repo"}


class RepositorySynchronizerTests:
    """Tests for repository synchronizer."""

    def test_init(self):
        """Test synchronizer initialization."""
        sync = RepositorySynchronizer()
        assert sync.github_token is None

    def test_exclude_patterns(self):
        """Test that exclude patterns are defined."""
        sync = RepositorySynchronizer()
        assert ".git" in sync.EXCLUDE_PATTERNS
        assert ".github" in sync.EXCLUDE_PATTERNS
        assert "action.yml" in sync.EXCLUDE_PATTERNS

    def test_get_default_repos(self):
        """Test getting default repos list."""
        repos = RepositorySynchronizer._get_default_repos()

        assert len(repos) == 14
        assert "pipery-dev/pipery-cpp-ci" in repos
        assert "pipery-dev/pipery-python-ci" in repos
        assert "pipery-dev/pipery-terraform-cd" in repos

    @patch("pipery_tooling.cross_platform_sync.RepositorySynchronizer.sync_to_platform")
    def test_sync_all_platforms(self, mock_sync):
        """Test syncing all platforms."""
        mock_sync.return_value = {"status": "success"}

        sync = RepositorySynchronizer()
        report = sync.sync_all_platforms(
            repos=["pipery-dev/test-repo"],
            platforms=["gitlab"],
            gitlab_token="test-token",
        )

        assert isinstance(report, SyncReport)
        assert report.platform == "all"
        mock_sync.assert_called()

    def test_sync_report_to_dict(self):
        """Test sync report serialization."""
        report = SyncReport(
            successful=["repo1→gitlab"],
            failed={"repo2→gitlab": "error message"},
            timestamp="2023-01-01T00:00:00",
            platform="all",
        )

        data = report.to_dict()

        assert data["platform"] == "all"
        assert data["summary"]["total"] == 2
        assert data["summary"]["successful"] == 1
        assert data["summary"]["failed"] == 1
        assert "repo1→gitlab" in data["successful"]
        assert "repo2→gitlab" in data["failed"]


class RemoveExcludedFilesTests:
    """Tests for removing excluded files from repository."""

    def test_remove_excluded_files(self):
        """Test removing excluded files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)

            # Create files to be excluded
            (repo_path / ".git").mkdir()
            (repo_path / ".github").mkdir()
            (repo_path / ".github" / "workflows").mkdir()
            (repo_path / "action.yml").touch()

            # Create files to keep
            (repo_path / "README.md").touch()
            (repo_path / "src").mkdir()
            (repo_path / "src" / "main.py").touch()

            sync = RepositorySynchronizer()
            sync._remove_excluded_files(repo_path)

            # Verify excluded files are removed
            assert not (repo_path / ".git").exists()
            assert not (repo_path / ".github").exists()
            assert not (repo_path / "action.yml").exists()

            # Verify other files remain
            assert (repo_path / "README.md").exists()
            assert (repo_path / "src").exists()
            assert (repo_path / "src" / "main.py").exists()


class PlatformAwareFileFilteringTests:
    """Tests for platform-aware file filtering."""

    def test_should_exclude_file_gitlab(self):
        """Test that .gitlab-ci.yml is preserved for GitLab."""
        sync = RepositorySynchronizer()

        # .gitlab-ci.yml should NOT be excluded for GitLab
        assert not sync._should_exclude_file(".gitlab-ci.yml", "gitlab")

        # .gitlab-ci.yml should be excluded for Bitbucket
        assert sync._should_exclude_file(".gitlab-ci.yml", "bitbucket")

    def test_should_exclude_file_bitbucket(self):
        """Test that bitbucket-pipelines.yml is preserved for Bitbucket."""
        sync = RepositorySynchronizer()

        # bitbucket-pipelines.yml should NOT be excluded for Bitbucket
        assert not sync._should_exclude_file("bitbucket-pipelines.yml", "bitbucket")

        # bitbucket-pipelines.yml should be excluded for GitLab
        assert sync._should_exclude_file("bitbucket-pipelines.yml", "gitlab")

    def test_should_exclude_base_patterns(self):
        """Test that base exclude patterns work regardless of platform."""
        sync = RepositorySynchronizer()

        # Base patterns should be excluded for both platforms
        assert sync._should_exclude_file(".git", "gitlab")
        assert sync._should_exclude_file(".git", "bitbucket")
        assert sync._should_exclude_file(".github", "gitlab")
        assert sync._should_exclude_file(".github", "bitbucket")
        assert sync._should_exclude_file("action.yml", "gitlab")
        assert sync._should_exclude_file("action.yml", "bitbucket")

    def test_remove_excluded_files_preserves_gitlab_config(self):
        """Test that .gitlab-ci.yml is preserved when syncing to GitLab."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)

            # Create platform-specific configs
            (repo_path / ".gitlab-ci.yml").write_text("gitlab: true")
            (repo_path / "bitbucket-pipelines.yml").write_text("bitbucket: true")
            (repo_path / "README.md").touch()

            sync = RepositorySynchronizer()
            sync._remove_excluded_files(repo_path, target_platform="gitlab")

            # .gitlab-ci.yml should be preserved
            assert (repo_path / ".gitlab-ci.yml").exists()

            # bitbucket-pipelines.yml should be removed
            assert not (repo_path / "bitbucket-pipelines.yml").exists()

            # Other files should remain
            assert (repo_path / "README.md").exists()

    def test_remove_excluded_files_preserves_bitbucket_config(self):
        """Test that bitbucket-pipelines.yml is preserved when syncing to Bitbucket."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)

            # Create platform-specific configs
            (repo_path / ".gitlab-ci.yml").write_text("gitlab: true")
            (repo_path / "bitbucket-pipelines.yml").write_text("bitbucket: true")
            (repo_path / "README.md").touch()

            sync = RepositorySynchronizer()
            sync._remove_excluded_files(repo_path, target_platform="bitbucket")

            # .gitlab-ci.yml should be removed
            assert not (repo_path / ".gitlab-ci.yml").exists()

            # bitbucket-pipelines.yml should be preserved
            assert (repo_path / "bitbucket-pipelines.yml").exists()

            # Other files should remain
            assert (repo_path / "README.md").exists()


class BackupFileTests:
    """Tests for file backup functionality."""

    def test_backup_file_creates_backup(self):
        """Test that backup file is created before overwrite."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            original_file = repo_path / "test.txt"
            original_file.write_text("original content")

            sync = RepositorySynchronizer()
            backup_path = sync._backup_file(original_file)

            # Backup should be created
            assert backup_path is not None
            assert backup_path.exists()
            assert backup_path.name == "test.txt.backup"
            assert backup_path.read_text() == "original content"

            # Original should still exist
            assert original_file.exists()

    def test_backup_directory_creates_backup(self):
        """Test that backup directory is created before overwrite."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            original_dir = repo_path / "test_dir"
            original_dir.mkdir()
            (original_dir / "file.txt").write_text("content")

            sync = RepositorySynchronizer()
            backup_path = sync._backup_file(original_dir)

            # Backup should be created
            assert backup_path is not None
            assert backup_path.exists()
            assert backup_path.is_dir()
            assert (backup_path / "file.txt").exists()
            assert (backup_path / "file.txt").read_text() == "content"

    def test_backup_nonexistent_file_returns_none(self):
        """Test that backing up non-existent file returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            nonexistent = repo_path / "nonexistent.txt"

            sync = RepositorySynchronizer()
            backup_path = sync._backup_file(nonexistent)

            assert backup_path is None


class TokenSecurityTests:
    """Tests for secure token handling in git push operations."""

    @patch("pipery_tooling.cross_platform_sync.subprocess.run")
    def test_gitlab_push_no_token_in_args(self, mock_run):
        """Test that GitLab token is not in subprocess arguments."""
        mock_run.return_value = MagicMock(returncode=0)

        gitlab = GitLabAPI(token="secret-token-12345")

        # Mock the get_project response
        with patch.object(gitlab, 'get_project') as mock_get:
            mock_get.return_value = {
                "http_url_to_repo": "https://gitlab.com/test/repo.git"
            }

            gitlab.push_branch("test-project", "main", "/tmp/repo")

        # Verify git push command was called
        calls = [call for call in mock_run.call_args_list if "push" in str(call)]
        assert len(calls) > 0

        # Extract the push command arguments
        push_call = calls[0]
        args = push_call[0][0]  # First positional arg is the command list

        # Token should NOT be visible in command arguments
        assert "secret-token-12345" not in str(args)

        # URL should be clean (no token)
        assert "https://gitlab.com/test/repo.git" in args

    @patch("pipery_tooling.cross_platform_sync.subprocess.run")
    def test_bitbucket_push_no_token_in_args(self, mock_run):
        """Test that Bitbucket token is not in subprocess arguments."""
        mock_run.return_value = MagicMock(returncode=0)

        bitbucket = BitbucketAPI(workspace="test-workspace", token="secret-token-67890")

        # Mock the get_repository and get_repository_url
        with patch.object(bitbucket, 'get_repository') as mock_get_repo, \
             patch.object(bitbucket, 'get_repository_url') as mock_get_url:
            mock_get_repo.return_value = {"name": "test-repo"}
            mock_get_url.return_value = "https://bitbucket.org/test-workspace/test-repo.git"

            bitbucket.push_branch("test-repo", "main", "/tmp/repo")

        # Verify git push command was called
        calls = [call for call in mock_run.call_args_list if "push" in str(call)]
        assert len(calls) > 0

        # Extract the push command arguments
        push_call = calls[0]
        args = push_call[0][0]  # First positional arg is the command list

        # Token should NOT be visible in command arguments
        assert "secret-token-67890" not in str(args)

        # URL should be clean (no token)
        assert "https://bitbucket.org/test-workspace/test-repo.git" in args
