"""Tag management and versioning for cross-platform repositories."""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .cross_platform_sync import GitLabAPI, BitbucketAPI


logger = logging.getLogger(__name__)


@dataclass
class VersionInfo:
    """Information about a version."""
    major: int
    minor: int
    patch: int
    platform: str

    def __str__(self) -> str:
        return f"v{self.major}.{self.minor}.{self.patch}"

    def major_tag(self) -> str:
        """Get major version tag for platform."""
        return f"v{self.major}-{self.platform}"

    def minor_tag(self) -> str:
        """Get minor version tag for platform."""
        return f"v{self.major}.{self.minor}-{self.platform}"

    def latest_tag(self) -> str:
        """Get latest tag for platform."""
        return f"latest-{self.platform}"


class TagManager:
    """Manage version tags on GitLab and Bitbucket."""

    # Regex to match release branches: release/vX.Y.Z
    RELEASE_BRANCH_PATTERN = re.compile(r"^release/v(\d+)\.(\d+)\.(\d+).*$")

    def __init__(
        self,
        gitlab_token: str | None = None,
        bitbucket_token: str | None = None,
        bitbucket_workspace: str | None = None,
    ):
        self.gitlab_token = gitlab_token
        self.bitbucket_token = bitbucket_token
        self.bitbucket_workspace = bitbucket_workspace

    def create_missing_tags_gitlab(self, project_id: str) -> dict:
        """
        Create missing tags on GitLab based on release branches.

        Args:
            project_id: GitLab project ID or path

        Returns:
            dict with results of tag creation
        """
        gitlab = GitLabAPI(token=self.gitlab_token)
        results = {
            "created": [],
            "updated": [],
            "errors": [],
        }

        try:
            # Get all branches
            branches = gitlab.list_branches(project_id)
            release_branches = [b for b in branches if self._is_release_branch(b["name"])]

            if not release_branches:
                logger.info(f"No release branches found on GitLab project {project_id}")
                return results

            # Process each release branch
            for branch in release_branches:
                try:
                    version = self._parse_version_from_branch(branch["name"])
                    if not version:
                        continue

                    version.platform = "gitlab"

                    # Create/update tags
                    self._create_or_update_tag_gitlab(
                        gitlab, project_id, branch, version, results
                    )
                except Exception as e:
                    results["errors"].append(f"Error processing {branch['name']}: {e}")

            return results
        except Exception as e:
            results["errors"].append(f"Failed to create tags on GitLab: {e}")
            return results

    def create_missing_tags_bitbucket(self, repo_slug: str) -> dict:
        """
        Create missing tags on Bitbucket based on release branches.

        Args:
            repo_slug: Bitbucket repository slug

        Returns:
            dict with results of tag creation
        """
        bitbucket = BitbucketAPI(
            workspace=self.bitbucket_workspace,
            token=self.bitbucket_token
        )
        results = {
            "created": [],
            "updated": [],
            "errors": [],
        }

        try:
            # Get all branches
            branches = bitbucket.list_branches(repo_slug)
            release_branches = [b for b in branches if self._is_release_branch(b["name"])]

            if not release_branches:
                logger.info(f"No release branches found on Bitbucket repo {repo_slug}")
                return results

            # Process each release branch
            for branch in release_branches:
                try:
                    version = self._parse_version_from_branch(branch["name"])
                    if not version:
                        continue

                    version.platform = "bitbucket"

                    # Create/update tags
                    self._create_or_update_tag_bitbucket(
                        bitbucket, repo_slug, branch, version, results
                    )
                except Exception as e:
                    results["errors"].append(f"Error processing {branch['name']}: {e}")

            return results
        except Exception as e:
            results["errors"].append(f"Failed to create tags on Bitbucket: {e}")
            return results

    def _create_or_update_tag_gitlab(
        self,
        gitlab: GitLabAPI,
        project_id: str,
        branch: dict,
        version: VersionInfo,
        results: dict,
    ) -> None:
        """Create or update tags on GitLab."""
        commit_hash = branch.get("commit", {}).get("id")
        if not commit_hash:
            logger.warning(f"No commit hash for branch {branch['name']}")
            return

        # Create version tag if it doesn't exist
        version_tag = str(version)
        if not gitlab.get_tag(project_id, version_tag):
            try:
                gitlab.create_tag(project_id, version_tag, commit_hash)
                results["created"].append(version_tag)
                logger.info(f"Created tag {version_tag}")
            except Exception as e:
                logger.error(f"Failed to create tag {version_tag}: {e}")

        # Update major version tag
        major_tag = version.major_tag()
        try:
            if gitlab.get_tag(project_id, major_tag):
                # Tag already exists, we need to update it
                # GitLab doesn't allow updating tags directly, so we log this
                logger.info(f"Tag {major_tag} already exists, skipping update")
            else:
                gitlab.create_tag(project_id, major_tag, commit_hash)
                results["created"].append(major_tag)
                logger.info(f"Created tag {major_tag}")
        except Exception as e:
            logger.error(f"Failed to create tag {major_tag}: {e}")

        # Update minor version tag
        minor_tag = version.minor_tag()
        try:
            if gitlab.get_tag(project_id, minor_tag):
                logger.info(f"Tag {minor_tag} already exists, skipping update")
            else:
                gitlab.create_tag(project_id, minor_tag, commit_hash)
                results["created"].append(minor_tag)
                logger.info(f"Created tag {minor_tag}")
        except Exception as e:
            logger.error(f"Failed to create tag {minor_tag}: {e}")

        # Update latest tag
        latest_tag = version.latest_tag()
        try:
            if gitlab.get_tag(project_id, latest_tag):
                logger.info(f"Tag {latest_tag} already exists, skipping update")
            else:
                gitlab.create_tag(project_id, latest_tag, commit_hash)
                results["created"].append(latest_tag)
                logger.info(f"Created tag {latest_tag}")
        except Exception as e:
            logger.error(f"Failed to create tag {latest_tag}: {e}")

    def _create_or_update_tag_bitbucket(
        self,
        bitbucket: BitbucketAPI,
        repo_slug: str,
        branch: dict,
        version: VersionInfo,
        results: dict,
    ) -> None:
        """Create or update tags on Bitbucket."""
        commit_hash = branch.get("target", {}).get("hash")
        if not commit_hash:
            logger.warning(f"No commit hash for branch {branch['name']}")
            return

        # Create version tag if it doesn't exist
        version_tag = str(version)
        if not bitbucket.get_tag(repo_slug, version_tag):
            try:
                bitbucket.create_tag(repo_slug, version_tag, commit_hash)
                results["created"].append(version_tag)
                logger.info(f"Created tag {version_tag}")
            except Exception as e:
                logger.error(f"Failed to create tag {version_tag}: {e}")

        # Update major version tag
        major_tag = version.major_tag()
        try:
            if bitbucket.get_tag(repo_slug, major_tag):
                logger.info(f"Tag {major_tag} already exists, skipping update")
            else:
                bitbucket.create_tag(repo_slug, major_tag, commit_hash)
                results["created"].append(major_tag)
                logger.info(f"Created tag {major_tag}")
        except Exception as e:
            logger.error(f"Failed to create tag {major_tag}: {e}")

        # Update minor version tag
        minor_tag = version.minor_tag()
        try:
            if bitbucket.get_tag(repo_slug, minor_tag):
                logger.info(f"Tag {minor_tag} already exists, skipping update")
            else:
                bitbucket.create_tag(repo_slug, minor_tag, commit_hash)
                results["created"].append(minor_tag)
                logger.info(f"Created tag {minor_tag}")
        except Exception as e:
            logger.error(f"Failed to create tag {minor_tag}: {e}")

        # Update latest tag
        latest_tag = version.latest_tag()
        try:
            if bitbucket.get_tag(repo_slug, latest_tag):
                logger.info(f"Tag {latest_tag} already exists, skipping update")
            else:
                bitbucket.create_tag(repo_slug, latest_tag, commit_hash)
                results["created"].append(latest_tag)
                logger.info(f"Created tag {latest_tag}")
        except Exception as e:
            logger.error(f"Failed to create tag {latest_tag}: {e}")

    @staticmethod
    def _is_release_branch(branch_name: str) -> bool:
        """Check if a branch is a release branch."""
        return TagManager.RELEASE_BRANCH_PATTERN.match(branch_name) is not None

    @staticmethod
    def _parse_version_from_branch(branch_name: str) -> VersionInfo | None:
        """Parse version from release branch name."""
        match = TagManager.RELEASE_BRANCH_PATTERN.match(branch_name)
        if not match:
            return None

        major, minor, patch = match.groups()
        return VersionInfo(
            major=int(major),
            minor=int(minor),
            patch=int(patch),
            platform="",
        )
