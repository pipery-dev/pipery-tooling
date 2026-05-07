"""
Version tag creation for platform-specific releases.

Creates immutable version tags, major version tags, and latest tags for each platform.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Literal

Platform = Literal["github", "gitlab", "bitbucket"]


def create_platform_tags(
    repo_dir: Path,
    version: str,
    platforms: list[Platform] | None = None,
    target_commit: str | None = None,
    dry_run: bool = False,
) -> dict[str, list[str]]:
    """
    Create platform-specific version tags for a release.

    For each platform, creates three tag types:
    - Immutable version tag: v${version}-${platform} (e.g., v1.0.0-gitlab)
    - Major version tag: v${major}-${platform} (e.g., v1-gitlab) - UPDATES if newer exists
    - Latest tag: latest-${platform} - UPDATES to point to newest version

    Args:
        repo_dir: Path to the repository
        version: Semantic version string (e.g., "1.0.0")
        platforms: List of platforms to create tags for. Defaults to all.
        target_commit: Git commit to tag. If None, tags the current HEAD.
        dry_run: If True, don't actually create tags, just return what would be created.

    Returns:
        Dictionary mapping platform names to lists of created tag names.

    Raises:
        RuntimeError: If git operations fail or version format is invalid.
    """
    if platforms is None:
        platforms = ["github", "gitlab", "bitbucket"]

    # Parse version to extract major version
    major_version = _extract_major_version(version)

    tags_by_platform = {}
    for platform in platforms:
        tags = [
            f"v{version}-{platform}",
            f"v{major_version}-{platform}",
            f"latest-{platform}",
        ]

        if not dry_run:
            for tag in tags:
                _create_or_update_tag(repo_dir, tag, target_commit, force=(tag != f"v{version}-{platform}"))

        tags_by_platform[platform] = tags

    return tags_by_platform


def _extract_major_version(version: str) -> str:
    """
    Extract the major version from a semantic version string.

    Args:
        version: Semantic version string (e.g., "1.0.0" or "1.0.0-beta.1")

    Returns:
        Major version string (e.g., "1")

    Raises:
        ValueError: If version format is invalid.
    """
    # Match semver pattern: X.Y.Z with optional pre-release and metadata
    match = re.match(r"^(\d+)\.\d+\.\d+(?:[-+].+)?$", version)
    if not match:
        raise ValueError(
            f"Invalid semantic version format: {version}\n"
            f"Expected format: MAJOR.MINOR.PATCH[-prerelease][+metadata]"
        )
    return match.group(1)


def _create_or_update_tag(
    repo_dir: Path,
    tag_name: str,
    target_commit: str | None = None,
    force: bool = False,
) -> None:
    """
    Create or update a tag in the repository.

    Args:
        repo_dir: Path to the repository
        tag_name: Name of the tag to create
        target_commit: Git commit to tag. If None, tags current HEAD.
        force: If True, overwrite existing tag.

    Raises:
        RuntimeError: If git operations fail.
    """
    try:
        cmd = ["git", "tag", tag_name]
        if force:
            cmd.insert(2, "-f")
        if target_commit:
            cmd.append(target_commit)

        subprocess.run(cmd, cwd=repo_dir, check=True, capture_output=True)

    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"Failed to create/update tag {tag_name}: {e.stderr.decode('utf-8', errors='replace')}"
        ) from e


def push_platform_tags(
    repo_dir: Path,
    version: str,
    platforms: list[Platform] | None = None,
    remote: str = "origin",
) -> None:
    """
    Push platform-specific tags to a remote repository.

    Args:
        repo_dir: Path to the repository
        version: Semantic version string
        platforms: List of platforms. Defaults to all.
        remote: Remote repository name (default: "origin")

    Raises:
        RuntimeError: If git push operations fail.
    """
    if platforms is None:
        platforms = ["github", "gitlab", "bitbucket"]

    major_version = _extract_major_version(version)

    try:
        for platform in platforms:
            # Push immutable version tag
            immutable_tag = f"v{version}-{platform}"
            subprocess.run(
                ["git", "push", remote, immutable_tag],
                cwd=repo_dir,
                check=True,
                capture_output=True,
            )

            # Push major version tag with force (in case it existed before)
            major_tag = f"v{major_version}-{platform}"
            subprocess.run(
                ["git", "push", remote, major_tag, "--force"],
                cwd=repo_dir,
                check=True,
                capture_output=True,
            )

            # Push latest tag with force (always update to newest)
            latest_tag = f"latest-{platform}"
            subprocess.run(
                ["git", "push", remote, latest_tag, "--force"],
                cwd=repo_dir,
                check=True,
                capture_output=True,
            )

    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"Failed to push tags to {remote}: {e.stderr.decode('utf-8', errors='replace')}"
        ) from e


def list_platform_tags(
    repo_dir: Path,
    platform: Platform,
    version: str | None = None,
) -> list[str]:
    """
    List existing platform-specific tags.

    Args:
        repo_dir: Path to the repository
        platform: Platform type to list tags for
        version: Optional specific version to list tags for

    Returns:
        List of matching tag names.

    Raises:
        RuntimeError: If git operations fail.
    """
    try:
        pattern = f"*-{platform}"
        if version:
            pattern = f"v{version}-{platform}"

        result = subprocess.run(
            ["git", "tag", "-l", pattern],
            cwd=repo_dir,
            check=True,
            capture_output=True,
            text=True,
        )

        return result.stdout.strip().split("\n") if result.stdout.strip() else []

    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"Failed to list tags for {platform}: {e.stderr.decode('utf-8', errors='replace')}"
        ) from e
