"""Tests for version parsing and rolling tag management."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from unittest import TestCase

from pipery_tooling.version_parser import ParsedVersion, VersionParser
from pipery_tooling.rolling_tag_manager import TagManager, TagOperationError


class VersionParserTests(TestCase):
    """Test version parsing and comparison."""

    def test_parse_basic_semver(self) -> None:
        """Parse basic semver versions."""
        parsed = VersionParser.parse_tag("v1.2.3")
        assert parsed is not None
        assert parsed.major == 1
        assert parsed.minor == 2
        assert parsed.patch == 3
        assert parsed.platform is None
        assert not parsed.is_latest

    def test_parse_major_only(self) -> None:
        """Parse major-only versions."""
        parsed = VersionParser.parse_tag("v1")
        assert parsed is not None
        assert parsed.major == 1
        assert parsed.minor is None
        assert parsed.patch is None

    def test_parse_major_minor(self) -> None:
        """Parse major.minor versions."""
        parsed = VersionParser.parse_tag("v1.2")
        assert parsed is not None
        assert parsed.major == 1
        assert parsed.minor == 2
        assert parsed.patch is None

    def test_parse_with_platform_suffix(self) -> None:
        """Parse versions with platform suffixes."""
        parsed = VersionParser.parse_tag("v1.2.3-gitlab")
        assert parsed is not None
        assert parsed.major == 1
        assert parsed.minor == 2
        assert parsed.patch == 3
        assert parsed.platform == "gitlab"

    def test_parse_latest_tag(self) -> None:
        """Parse latest tags."""
        parsed = VersionParser.parse_tag("latest")
        assert parsed is not None
        assert parsed.is_latest
        assert parsed.platform is None

    def test_parse_latest_with_platform(self) -> None:
        """Parse latest tags with platform."""
        parsed = VersionParser.parse_tag("latest-gitlab")
        assert parsed is not None
        assert parsed.is_latest
        assert parsed.platform == "gitlab"

    def test_parse_invalid_format(self) -> None:
        """Reject invalid formats."""
        assert VersionParser.parse_tag("invalid") is None
        # Note: "1.2.3" without 'v' prefix is actually accepted now
        # since we handle both formats

    def test_version_comparison_greater(self) -> None:
        """Test version greater-than comparison."""
        v1 = ParsedVersion(major=1, minor=2, patch=3)
        v2 = ParsedVersion(major=1, minor=2, patch=0)
        assert v1 > v2

    def test_version_comparison_less(self) -> None:
        """Test version less-than comparison."""
        v1 = ParsedVersion(major=1, minor=2, patch=0)
        v2 = ParsedVersion(major=1, minor=2, patch=3)
        assert v1 < v2

    def test_version_comparison_equal(self) -> None:
        """Test version equality."""
        v1 = ParsedVersion(major=1, minor=2, patch=3)
        v2 = ParsedVersion(major=1, minor=2, patch=3)
        assert v1 == v2

    def test_version_comparison_ignores_platform(self) -> None:
        """Version comparison ignores platform suffix."""
        v1 = ParsedVersion(major=1, minor=2, patch=3, platform="gitlab")
        v2 = ParsedVersion(major=1, minor=2, patch=3, platform="github")
        assert v1 == v2

    def test_version_full_version_string(self) -> None:
        """Get full version string."""
        v = ParsedVersion(major=1, minor=2, patch=3)
        assert v.full_version == "1.2.3"

    def test_version_tag_name_with_platform(self) -> None:
        """Get tag name with platform."""
        v = ParsedVersion(major=1, minor=2, patch=3, platform="gitlab")
        assert v.tag_name == "v1.2.3-gitlab"

    def test_version_tag_name_without_platform(self) -> None:
        """Get tag name without platform."""
        v = ParsedVersion(major=1, minor=2, patch=3)
        assert v.tag_name == "v1.2.3"

    def test_get_major_tag(self) -> None:
        """Get major version tag."""
        v = ParsedVersion(major=1, minor=2, patch=3, platform="gitlab")
        tag = VersionParser.get_major_tag(v)
        assert tag == "v1-gitlab"

    def test_get_minor_tag(self) -> None:
        """Get minor version tag."""
        v = ParsedVersion(major=1, minor=2, patch=3, platform="gitlab")
        tag = VersionParser.get_minor_tag(v)
        assert tag == "v1.2-gitlab"

    def test_get_latest_tag_with_platform(self) -> None:
        """Get latest tag with platform."""
        tag = VersionParser.get_latest_tag("gitlab")
        assert tag == "latest-gitlab"

    def test_get_latest_tag_without_platform(self) -> None:
        """Get latest tag without platform."""
        tag = VersionParser.get_latest_tag(None)
        assert tag == "latest"


class TagManagerTests(TestCase):
    """Test rolling tag management."""

    def setUp(self) -> None:
        """Create a temporary git repository for testing."""
        self.temp_dir = tempfile.mkdtemp(prefix="pipery-tag-test-")
        self.repo_dir = Path(self.temp_dir)

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=self.repo_dir, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=self.repo_dir,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=self.repo_dir,
            check=True,
            capture_output=True,
        )

        # Create initial commit
        test_file = self.repo_dir / "test.txt"
        test_file.write_text("test")
        subprocess.run(["git", "add", "."], cwd=self.repo_dir, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=self.repo_dir,
            check=True,
            capture_output=True,
        )

        self.manager = TagManager(self.repo_dir)

    def tearDown(self) -> None:
        """Clean up temporary repository."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _get_current_commit(self) -> str:
        """Get current HEAD commit."""
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_dir,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    def test_create_version_tags(self) -> None:
        """Create all version tags."""
        commit = self._get_current_commit()
        tags = self.manager.create_version_tags("1.2.3", commit, "gitlab")

        assert "version" in tags
        assert "major" in tags
        assert "minor" in tags
        assert "latest" in tags

        assert self.manager.tag_exists("v1.2.3-gitlab")
        assert self.manager.tag_exists("v1-gitlab")
        assert self.manager.tag_exists("v1.2-gitlab")
        assert self.manager.tag_exists("latest-gitlab")

    def test_create_version_tags_without_platform(self) -> None:
        """Create version tags without platform suffix."""
        commit = self._get_current_commit()
        tags = self.manager.create_version_tags("1.2.3", commit)

        assert self.manager.tag_exists("v1.2.3")
        assert self.manager.tag_exists("v1")
        assert self.manager.tag_exists("v1.2")
        assert self.manager.tag_exists("latest")

    def test_update_rolling_tags_on_newer_version(self) -> None:
        """Update rolling tags when a newer version is created."""
        commit1 = self._get_current_commit()
        self.manager.create_version_tags("1.0.0", commit1, "gitlab")

        # Create a new commit and tag a newer version
        test_file = self.repo_dir / "test2.txt"
        test_file.write_text("test2")
        subprocess.run(["git", "add", "."], cwd=self.repo_dir, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Second commit"],
            cwd=self.repo_dir,
            check=True,
            capture_output=True,
        )
        commit2 = self._get_current_commit()

        updated = self.manager.update_rolling_tags("1.2.3", commit2, "gitlab")

        assert "major" in updated
        assert "minor" in updated
        assert "latest" in updated

        # Verify tags point to new commit
        assert self.manager.get_tag_commit("v1-gitlab") == commit2
        assert self.manager.get_tag_commit("v1.2-gitlab") == commit2
        assert self.manager.get_tag_commit("latest-gitlab") == commit2

    def test_update_rolling_tags_ignores_older_version(self) -> None:
        """Don't update rolling tags when version is older."""
        commit1 = self._get_current_commit()
        self.manager.create_version_tags("1.2.3", commit1, "gitlab")

        # Try to create an older version
        test_file = self.repo_dir / "test2.txt"
        test_file.write_text("test2")
        subprocess.run(["git", "add", "."], cwd=self.repo_dir, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Second commit"],
            cwd=self.repo_dir,
            check=True,
            capture_output=True,
        )
        commit2 = self._get_current_commit()

        updated = self.manager.update_rolling_tags("1.0.0", commit2, "gitlab")

        # Should not update major tag since 1.0.0 < 1.2.3
        assert "major" not in updated

        # Tags should still point to v1.2.3 commit
        assert self.manager.get_tag_commit("v1-gitlab") == commit1

    def test_get_latest_version_in_series(self) -> None:
        """Find latest version in a series."""
        commit = self._get_current_commit()

        # Create multiple versions
        self.manager.create_version_tags("1.0.0", commit, "gitlab")
        self.manager.create_version_tags("1.2.0", commit, "gitlab")
        self.manager.create_version_tags("1.2.3", commit, "gitlab")

        latest = self.manager.get_latest_version_in_series(1, None, "gitlab")
        assert latest is not None
        assert latest.major == 1
        assert latest.minor == 2
        assert latest.patch == 3

    def test_get_latest_version_in_minor_series(self) -> None:
        """Find latest version in a minor series."""
        commit = self._get_current_commit()

        # Create versions in v1.2 series
        self.manager.create_version_tags("1.2.0", commit, "gitlab")
        self.manager.create_version_tags("1.2.3", commit, "gitlab")

        latest = self.manager.get_latest_version_in_series(1, 2, "gitlab")
        assert latest is not None
        assert latest.major == 1
        assert latest.minor == 2
        assert latest.patch == 3

    def test_get_versions_by_platform(self) -> None:
        """Get all versions for a platform."""
        commit = self._get_current_commit()

        self.manager.create_version_tags("1.0.0", commit, "gitlab")
        self.manager.create_version_tags("1.2.3", commit, "github")

        gitlab_versions = self.manager.get_versions_by_platform("gitlab")
        assert len(gitlab_versions) >= 4  # v1.0.0, v1, v1.0, latest

        github_versions = self.manager.get_versions_by_platform("github")
        assert len(github_versions) >= 4

    def test_tag_validation_valid_tag(self) -> None:
        """Validate a valid tag."""
        commit = self._get_current_commit()
        self.manager.create_version_tags("1.2.3", commit, "gitlab")

        errors = self.manager.validate_tag("v1.2.3-gitlab")
        assert len(errors) == 0

    def test_tag_validation_nonexistent_tag(self) -> None:
        """Validate a nonexistent tag."""
        errors = self.manager.validate_tag("v99.99.99-gitlab")
        assert len(errors) > 0
        assert "does not exist" in errors[0]

    def test_delete_tag(self) -> None:
        """Delete a tag."""
        commit = self._get_current_commit()
        self.manager.create_version_tags("1.2.3", commit, "gitlab")

        assert self.manager.tag_exists("v1.2.3-gitlab")
        self.manager.delete_tag("v1.2.3-gitlab")
        assert not self.manager.tag_exists("v1.2.3-gitlab")

    def test_find_orphaned_tags(self) -> None:
        """Find tags that don't follow conventions."""
        commit = self._get_current_commit()

        # Create a valid tag
        self.manager.create_version_tags("1.2.3", commit, "gitlab")

        # Create an invalid tag
        self.manager.create_tag("invalid-tag-format", commit)

        orphaned = self.manager.find_orphaned_tags()
        assert len(orphaned) >= 1
        assert any(tag == "invalid-tag-format" for tag, _ in orphaned)

    def test_find_duplicate_versions(self) -> None:
        """Find duplicate versions pointing to different commits."""
        commit1 = self._get_current_commit()

        # Create v1.2.3 at commit1
        self.manager.create_tag("v1.2.3-gitlab", commit1)

        # Create a new commit
        test_file = self.repo_dir / "test2.txt"
        test_file.write_text("test2")
        subprocess.run(["git", "add", "."], cwd=self.repo_dir, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Second commit"],
            cwd=self.repo_dir,
            check=True,
            capture_output=True,
        )
        commit2 = self._get_current_commit()

        # Create another v1.2.3-github tag at commit2
        self.manager.create_tag("v1.2.3-github", commit2)

        duplicates = self.manager.find_duplicate_versions()
        # Both tags have the same version "1.2.3" but different platforms
        # The find_duplicate_versions looks at versions regardless of platform
        # So this should find them as duplicates (both v1.2.3)
        assert "1.2.3" in duplicates
        assert len(duplicates["1.2.3"]) == 2
