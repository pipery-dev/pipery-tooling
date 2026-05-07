"""Tests for tag management functionality."""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from pipery_tooling.tag_manager import TagManager, VersionInfo


class VersionInfoTests:
    """Tests for version information."""

    def test_version_str(self):
        """Test version string representation."""
        version = VersionInfo(major=1, minor=2, patch=3, platform="")
        assert str(version) == "v1.2.3"

    def test_major_tag(self):
        """Test major version tag."""
        version = VersionInfo(major=1, minor=2, patch=3, platform="gitlab")
        assert version.major_tag() == "v1-gitlab"

    def test_minor_tag(self):
        """Test minor version tag."""
        version = VersionInfo(major=1, minor=2, patch=3, platform="gitlab")
        assert version.minor_tag() == "v1.2-gitlab"

    def test_latest_tag(self):
        """Test latest version tag."""
        version = VersionInfo(major=1, minor=2, patch=3, platform="gitlab")
        assert version.latest_tag() == "latest-gitlab"


class TagManagerTests:
    """Tests for tag manager."""

    def test_init(self):
        """Test tag manager initialization."""
        manager = TagManager(
            gitlab_token="gitlab-token",
            bitbucket_token="bitbucket-token",
            bitbucket_workspace="workspace",
        )
        assert manager.gitlab_token == "gitlab-token"
        assert manager.bitbucket_token == "bitbucket-token"
        assert manager.bitbucket_workspace == "workspace"

    def test_is_release_branch_valid(self):
        """Test recognizing valid release branches."""
        assert TagManager._is_release_branch("release/v1.0.0")
        assert TagManager._is_release_branch("release/v1.2.3")
        assert TagManager._is_release_branch("release/v1.2.3-rc1")

    def test_is_release_branch_invalid(self):
        """Test rejecting invalid branch names."""
        assert not TagManager._is_release_branch("main")
        assert not TagManager._is_release_branch("develop")
        assert not TagManager._is_release_branch("feature/my-feature")
        assert not TagManager._is_release_branch("release/v1")

    def test_parse_version_from_branch(self):
        """Test parsing version from branch name."""
        version = TagManager._parse_version_from_branch("release/v1.2.3")

        assert version is not None
        assert version.major == 1
        assert version.minor == 2
        assert version.patch == 3

    def test_parse_version_invalid_branch(self):
        """Test that invalid branches return None."""
        version = TagManager._parse_version_from_branch("main")
        assert version is None

    @patch("pipery_tooling.tag_manager.GitLabAPI")
    def test_create_missing_tags_gitlab_no_branches(self, mock_gitlab_class):
        """Test creating tags when no release branches exist."""
        mock_gitlab = Mock()
        mock_gitlab.list_branches.return_value = []
        mock_gitlab_class.return_value = mock_gitlab

        manager = TagManager(gitlab_token="token")
        results = manager.create_missing_tags_gitlab("test-project")

        assert results["created"] == []
        assert results["updated"] == []
        assert results["errors"] == []

    @patch("pipery_tooling.tag_manager.GitLabAPI")
    def test_create_missing_tags_gitlab_with_release_branch(self, mock_gitlab_class):
        """Test creating tags for a release branch."""
        mock_gitlab = Mock()
        mock_gitlab.list_branches.return_value = [
            {
                "name": "release/v1.2.3",
                "commit": {"id": "abc123"},
            }
        ]
        mock_gitlab.get_tag.return_value = None  # Tag doesn't exist
        mock_gitlab.create_tag.return_value = {"name": "v1.2.3"}
        mock_gitlab_class.return_value = mock_gitlab

        manager = TagManager(gitlab_token="token")
        results = manager.create_missing_tags_gitlab("test-project")

        # Should create version tag and rolling tags
        assert "v1.2.3" in results["created"]
        assert mock_gitlab.create_tag.call_count > 0

    @patch("pipery_tooling.tag_manager.BitbucketAPI")
    def test_create_missing_tags_bitbucket_no_branches(self, mock_bitbucket_class):
        """Test creating tags when no release branches exist."""
        mock_bitbucket = Mock()
        mock_bitbucket.list_branches.return_value = []
        mock_bitbucket_class.return_value = mock_bitbucket

        manager = TagManager(bitbucket_token="token", bitbucket_workspace="workspace")
        results = manager.create_missing_tags_bitbucket("test-repo")

        assert results["created"] == []
        assert results["updated"] == []
        assert results["errors"] == []

    @patch("pipery_tooling.tag_manager.BitbucketAPI")
    def test_create_missing_tags_bitbucket_with_release_branch(self, mock_bitbucket_class):
        """Test creating tags for a release branch on Bitbucket."""
        mock_bitbucket = Mock()
        mock_bitbucket.list_branches.return_value = [
            {
                "name": "release/v1.2.3",
                "target": {"hash": "abc123"},
            }
        ]
        mock_bitbucket.get_tag.return_value = None  # Tag doesn't exist
        mock_bitbucket.create_tag.return_value = {"name": "v1.2.3"}
        mock_bitbucket_class.return_value = mock_bitbucket

        manager = TagManager(bitbucket_token="token", bitbucket_workspace="workspace")
        results = manager.create_missing_tags_bitbucket("test-repo")

        # Should create version tag and rolling tags
        assert "v1.2.3" in results["created"]
        assert mock_bitbucket.create_tag.call_count > 0

    def test_version_comparison(self):
        """Test comparing versions."""
        v1 = VersionInfo(major=1, minor=2, patch=3, platform="gitlab")
        v2 = VersionInfo(major=1, minor=2, patch=4, platform="gitlab")
        v3 = VersionInfo(major=1, minor=3, patch=0, platform="gitlab")
        v4 = VersionInfo(major=2, minor=0, patch=0, platform="gitlab")

        # Compare major versions
        assert v1.major < v4.major
        assert v4.major > v1.major

        # Compare minor versions
        assert v1.minor < v3.minor

        # Compare patch versions
        assert v1.patch < v2.patch
