"""Rolling tag management for semantic versioning.

Handles:
- Creating immutable version tags
- Updating rolling tags (major, minor, latest) when new versions are released
- Finding the latest version in a series
- Reconciling tags across platforms
- Tag validation
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from .version_parser import ParsedVersion, VersionParser


class TagOperationError(Exception):
    """Raised when a git tag operation fails."""

    pass


class TagManager:
    """Manage git tags with semantic versioning support."""

    def __init__(self, repo_dir: Path):
        """Initialize tag manager for a repository."""
        self.repo_dir = Path(repo_dir).resolve()

    def get_all_tags(self) -> list[str]:
        """Get all tags in the repository."""
        try:
            result = subprocess.run(
                ["git", "tag", "-l"],
                cwd=self.repo_dir,
                capture_output=True,
                text=True,
                check=True,
            )
            return [tag.strip() for tag in result.stdout.splitlines() if tag.strip()]
        except subprocess.CalledProcessError as exc:
            raise TagOperationError(f"Failed to list tags: {exc.stderr}") from exc

    def get_tag_commit(self, tag: str) -> Optional[str]:
        """Get the commit hash that a tag points to."""
        try:
            result = subprocess.run(
                ["git", "rev-list", "-n", "1", tag],
                cwd=self.repo_dir,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except subprocess.CalledProcessError:
            return None

    def create_tag(self, tag: str, commit: Optional[str] = None) -> None:
        """Create a lightweight git tag."""
        try:
            cmd = ["git", "tag", tag]
            if commit:
                cmd.append(commit)
            subprocess.run(cmd, cwd=self.repo_dir, check=True, capture_output=True)
        except subprocess.CalledProcessError as exc:
            raise TagOperationError(f"Failed to create tag {tag}: {exc.stderr.decode()}") from exc

    def update_tag(self, tag: str, commit: str) -> None:
        """Update a tag to point to a different commit (uses --force)."""
        try:
            subprocess.run(
                ["git", "tag", "-f", tag, commit],
                cwd=self.repo_dir,
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            raise TagOperationError(f"Failed to update tag {tag}: {exc.stderr.decode()}") from exc

    def delete_tag(self, tag: str) -> None:
        """Delete a git tag."""
        try:
            subprocess.run(
                ["git", "tag", "-d", tag],
                cwd=self.repo_dir,
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            raise TagOperationError(f"Failed to delete tag {tag}: {exc.stderr.decode()}") from exc

    def push_tag(self, tag: str, remote: str = "origin", force: bool = False) -> None:
        """Push a tag to a remote repository."""
        try:
            cmd = ["git", "push", remote, tag]
            if force:
                cmd.insert(2, "--force")
            subprocess.run(cmd, cwd=self.repo_dir, check=True, capture_output=True)
        except subprocess.CalledProcessError as exc:
            raise TagOperationError(f"Failed to push tag {tag}: {exc.stderr.decode()}") from exc

    def delete_remote_tag(self, tag: str, remote: str = "origin") -> None:
        """Delete a tag from a remote repository."""
        try:
            subprocess.run(
                ["git", "push", remote, "--delete", tag],
                cwd=self.repo_dir,
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            raise TagOperationError(f"Failed to delete remote tag {tag}: {exc.stderr.decode()}") from exc

    def tag_exists(self, tag: str) -> bool:
        """Check if a tag exists."""
        return self.get_tag_commit(tag) is not None

    def get_versions_by_platform(self, platform: Optional[str] = None) -> dict[str, ParsedVersion]:
        """Get all parsed versions for a platform.

        Args:
            platform: Platform filter ('gitlab', 'github', None for all)

        Returns:
            Dictionary mapping tag names to ParsedVersion objects
        """
        all_tags = self.get_all_tags()
        versions = {}

        for tag in all_tags:
            parsed = VersionParser.parse_tag(tag)
            if parsed is None:
                continue
            if platform is not None and parsed.platform != platform:
                continue
            versions[tag] = parsed

        return versions

    def get_latest_version_in_series(
        self, major: int, minor: Optional[int] = None, platform: Optional[str] = None
    ) -> Optional[ParsedVersion]:
        """Find the latest version in a major/minor series.

        Examples:
            get_latest_version_in_series(1, None, 'gitlab')
                -> Highest v1.*.* for gitlab (e.g., v1.2.3-gitlab)
            get_latest_version_in_series(1, 2, 'gitlab')
                -> Highest v1.2.* for gitlab (e.g., v1.2.3-gitlab)

        Returns:
            The highest ParsedVersion in the series, or None if no versions found
        """
        versions = self.get_versions_by_platform(platform)
        candidates = []

        for parsed in versions.values():
            if parsed.is_latest:
                continue
            if parsed.major != major:
                continue
            if minor is not None and parsed.minor != minor:
                continue
            candidates.append(parsed)

        if not candidates:
            return None

        # Return the highest version
        return max(candidates)

    def create_version_tags(
        self, version_str: str, commit: str, platform: Optional[str] = None, push_to_remote: bool = False
    ) -> dict[str, str]:
        """Create all necessary tags for a new version release.

        Creates:
        - Immutable tag: v1.2.3 or v1.2.3-{platform}
        - Major tag: v1 or v1-{platform}
        - Minor tag: v1.2 or v1.2-{platform}
        - Latest tag: latest or latest-{platform}

        Args:
            version_str: Version string (e.g., '1.2.3')
            commit: Commit hash to tag
            platform: Platform suffix (None for GitHub)
            push_to_remote: Whether to push tags to origin

        Returns:
            Dictionary mapping tag names to created tags
        """
        parsed = VersionParser.parse_version_string(version_str)
        if parsed is None:
            raise ValueError(f"Invalid version format: {version_str}")

        if platform:
            parsed = ParsedVersion(
                major=parsed.major,
                minor=parsed.minor,
                patch=parsed.patch,
                platform=platform,
            )

        tags_created = {}

        # Create immutable version tag
        version_tag = parsed.tag_name
        if not self.tag_exists(version_tag):
            self.create_tag(version_tag, commit)
            tags_created["version"] = version_tag

        # Create/update major tag
        major_tag = VersionParser.get_major_tag(parsed)
        if self.tag_exists(major_tag):
            self.update_tag(major_tag, commit)
            tags_created["major"] = major_tag
        else:
            self.create_tag(major_tag, commit)
            tags_created["major"] = major_tag

        # Create/update minor tag (if minor version exists)
        if parsed.minor is not None:
            minor_tag = VersionParser.get_minor_tag(parsed)
            if self.tag_exists(minor_tag):
                self.update_tag(minor_tag, commit)
                tags_created["minor"] = minor_tag
            else:
                self.create_tag(minor_tag, commit)
                tags_created["minor"] = minor_tag

        # Create/update latest tag
        latest_tag = VersionParser.get_latest_tag(platform)
        if self.tag_exists(latest_tag):
            self.update_tag(latest_tag, commit)
            tags_created["latest"] = latest_tag
        else:
            self.create_tag(latest_tag, commit)
            tags_created["latest"] = latest_tag

        # Push tags if requested
        if push_to_remote:
            for tag in tags_created.values():
                force = tag in (major_tag, minor_tag, latest_tag)
                self.push_tag(tag, force=force)

        return tags_created

    def update_rolling_tags(
        self, version_str: str, commit: str, platform: Optional[str] = None, push_to_remote: bool = False
    ) -> dict[str, str]:
        """Update rolling tags (major, minor, latest) if this version is newer.

        This is useful for updating tags after a version is already released.

        Args:
            version_str: Version string (e.g., '1.2.3')
            commit: Commit hash the version is at
            platform: Platform suffix
            push_to_remote: Whether to push updates to origin

        Returns:
            Dictionary mapping tag names to tags that were updated (empty if no updates needed)
        """
        parsed = VersionParser.parse_version_string(version_str)
        if parsed is None:
            raise ValueError(f"Invalid version format: {version_str}")

        if platform:
            parsed = ParsedVersion(
                major=parsed.major,
                minor=parsed.minor,
                patch=parsed.patch,
                platform=platform,
            )

        tags_updated = {}

        # Check and update major tag
        major_tag = VersionParser.get_major_tag(parsed)
        major_latest = self.get_latest_version_in_series(parsed.major, None, platform)

        if major_latest is None or parsed > major_latest:
            if self.tag_exists(major_tag):
                self.update_tag(major_tag, commit)
            else:
                self.create_tag(major_tag, commit)
            tags_updated["major"] = major_tag

        # Check and update minor tag (if minor version exists)
        if parsed.minor is not None:
            minor_tag = VersionParser.get_minor_tag(parsed)
            minor_latest = self.get_latest_version_in_series(parsed.major, parsed.minor, platform)

            if minor_latest is None or parsed > minor_latest:
                if self.tag_exists(minor_tag):
                    self.update_tag(minor_tag, commit)
                else:
                    self.create_tag(minor_tag, commit)
                tags_updated["minor"] = minor_tag

        # Check and update latest tag
        latest_versions = self.get_versions_by_platform(platform)
        latest_version = None
        for v in latest_versions.values():
            if v.is_latest:
                continue
            if latest_version is None or v > latest_version:
                latest_version = v

        latest_tag = VersionParser.get_latest_tag(platform)
        if latest_version is None or parsed >= latest_version:
            if self.tag_exists(latest_tag):
                self.update_tag(latest_tag, commit)
            else:
                self.create_tag(latest_tag, commit)
            tags_updated["latest"] = latest_tag

        # Push updates if requested
        if push_to_remote:
            for tag in tags_updated.values():
                self.push_tag(tag, force=True)

        return tags_updated

    def validate_tag(self, tag: str, expected_branch: Optional[str] = None) -> list[str]:
        """Validate a tag.

        Checks:
        - Tag exists
        - Tag points to a valid commit
        - Tag follows naming conventions
        - Tag is on expected branch (if specified)

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        if not self.tag_exists(tag):
            errors.append(f"Tag does not exist: {tag}")
            return errors

        commit = self.get_tag_commit(tag)
        if not commit:
            errors.append(f"Tag points to invalid commit: {tag}")
            return errors

        # Check naming convention
        parsed = VersionParser.parse_tag(tag)
        if parsed is None:
            errors.append(f"Tag does not follow naming conventions: {tag}")

        # Check branch if specified
        if expected_branch:
            try:
                result = subprocess.run(
                    ["git", "branch", "-r", "--contains", commit],
                    cwd=self.repo_dir,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                branches = result.stdout.strip().split("\n")
                if not any(expected_branch in b for b in branches):
                    errors.append(f"Tag is not on expected branch {expected_branch}: {tag}")
            except subprocess.CalledProcessError:
                errors.append(f"Could not check tag branch: {tag}")

        return errors

    def find_orphaned_tags(self) -> list[tuple[str, ParsedVersion]]:
        """Find tags that don't follow conventions or have validation issues.

        Returns:
            List of (tag, parsed_version) tuples for problematic tags
        """
        all_tags = self.get_all_tags()
        orphaned = []

        for tag in all_tags:
            parsed = VersionParser.parse_tag(tag)
            if parsed is None:
                # Tag doesn't follow conventions
                orphaned.append((tag, None))

        return orphaned

    def find_duplicate_versions(self) -> dict[str, list[str]]:
        """Find duplicate versions (same version pointing to different commits).

        Returns:
            Dictionary mapping version to list of tags with that version
        """
        versions = self.get_versions_by_platform()
        duplicates = {}

        for tag, parsed in versions.items():
            if parsed.is_latest:
                continue
            key = parsed.full_version
            if key not in duplicates:
                duplicates[key] = []
            duplicates[key].append(tag)

        # Return only actual duplicates
        return {k: v for k, v in duplicates.items() if len(v) > 1}

    def reconcile_all_tags(self, platform: Optional[str] = None, push_to_remote: bool = False) -> dict[str, list[str]]:
        """Reconcile all tags for a platform.

        Scans all versions and ensures rolling tags point to the latest in each series.

        Args:
            platform: Platform to reconcile (None for all platforms)
            push_to_remote: Whether to push updates to origin

        Returns:
            Dictionary mapping action to list of tags affected
        """
        result = {
            "created": [],
            "updated": [],
            "errors": [],
        }

        versions = self.get_versions_by_platform(platform)

        # Group by major version
        by_major: dict[int, list[ParsedVersion]] = {}
        for parsed in versions.values():
            if parsed.is_latest:
                continue
            if parsed.major not in by_major:
                by_major[parsed.major] = []
            by_major[parsed.major].append(parsed)

        # Process each major version series
        for major, version_list in by_major.items():
            # Find latest in major series
            latest = max(version_list)
            latest_commit = self.get_tag_commit(latest.tag_name)

            if latest_commit:
                try:
                    updated = self.update_rolling_tags(
                        latest.full_version,
                        latest_commit,
                        platform,
                        push_to_remote,
                    )
                    result["updated"].extend(updated.values())
                except TagOperationError as exc:
                    result["errors"].append(str(exc))

            # Group by minor within major
            if any(v.minor is not None for v in version_list):
                by_minor: dict[int, list[ParsedVersion]] = {}
                for v in version_list:
                    if v.minor is not None:
                        if v.minor not in by_minor:
                            by_minor[v.minor] = []
                        by_minor[v.minor].append(v)

                for minor, minor_list in by_minor.items():
                    latest_minor = max(minor_list)
                    latest_minor_commit = self.get_tag_commit(latest_minor.tag_name)

                    if latest_minor_commit:
                        try:
                            updated = self.update_rolling_tags(
                                latest_minor.full_version,
                                latest_minor_commit,
                                platform,
                                push_to_remote,
                            )
                            result["updated"].extend(updated.values())
                        except TagOperationError as exc:
                            result["errors"].append(str(exc))

        return result
