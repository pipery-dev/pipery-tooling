"""
Release branch generation logic for multi-platform CI/CD support.

Handles creation of platform-specific release branches with appropriate
configurations for GitHub, GitLab, and Bitbucket.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Literal

Platform = Literal["github", "gitlab", "bitbucket"]


def generate_release_branches(
    repo_dir: Path,
    version: str,
    platforms: list[Platform] | None = None,
    dry_run: bool = False,
) -> dict[str, str]:
    """
    Generate platform-specific release branches for a given version.

    For each platform, creates a release branch based on the current main branch:
    - GitHub: release/github-v${version} (keeps scripts separate)
    - GitLab: release/gitlab-v${version} (inlines scripts into .gitlab-ci.yml)
    - Bitbucket: release/bitbucket-v${version} (inlines scripts into bitbucket-pipelines.yml)

    Args:
        repo_dir: Path to the repository
        version: Semantic version string (e.g., "1.0.0")
        platforms: List of platforms to generate branches for. Defaults to all.
        dry_run: If True, don't actually create branches, just return what would be created.

    Returns:
        Dictionary mapping platform names to their branch names.

    Raises:
        RuntimeError: If git operations fail.
    """
    if platforms is None:
        platforms = ["github", "gitlab", "bitbucket"]

    branch_map = {}
    for platform in platforms:
        branch_name = f"release/{platform}-v{version}"
        branch_map[platform] = branch_name

        if not dry_run:
            _create_platform_branch(repo_dir, branch_name, platform, version)

    return branch_map


def _create_platform_branch(
    repo_dir: Path,
    branch_name: str,
    platform: Platform,
    version: str,
) -> None:
    """
    Create a single platform-specific release branch.

    Args:
        repo_dir: Path to the repository
        branch_name: Name of the branch to create
        platform: Platform type (github, gitlab, bitbucket)
        version: Semantic version string

    Raises:
        RuntimeError: If git operations fail.
    """
    try:
        # Get current branch to ensure we're starting from a known state
        current_branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_dir,
            text=True,
        ).strip()

        # Create the new branch from main (or current branch if main doesn't exist)
        base_branch = "main" if _branch_exists(repo_dir, "main") else current_branch

        subprocess.run(
            ["git", "checkout", "-b", branch_name, base_branch],
            cwd=repo_dir,
            check=True,
            capture_output=True,
        )

        # For GitLab and Bitbucket, inline scripts
        if platform == "gitlab":
            _inline_scripts_in_file(repo_dir, ".gitlab-ci.yml", platform)
        elif platform == "bitbucket":
            _inline_scripts_in_file(repo_dir, "bitbucket-pipelines.yml", platform)

        # Commit the changes if any were made
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )
        if status.stdout.strip():
            subprocess.run(
                ["git", "add", "."],
                cwd=repo_dir,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "commit", "-m", f"Prepare {platform} release v{version}"],
                cwd=repo_dir,
                check=True,
                capture_output=True,
            )

    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"Failed to create release branch {branch_name} for {platform}: {e.stderr}"
        ) from e


def _branch_exists(repo_dir: Path, branch_name: str) -> bool:
    """Check if a branch exists in the repository."""
    result = subprocess.run(
        ["git", "rev-parse", "--verify", branch_name],
        cwd=repo_dir,
        capture_output=True,
    )
    return result.returncode == 0


def _inline_scripts_in_file(
    repo_dir: Path,
    pipeline_file: str,
    platform: Platform,
) -> None:
    """
    Inline script content into a pipeline configuration file.

    Replaces bash script calls (e.g., "bash ./src/step-*.sh") with the actual
    script content, properly indented for YAML format.

    Args:
        repo_dir: Path to the repository
        pipeline_file: Name of the pipeline file (.gitlab-ci.yml or bitbucket-pipelines.yml)
        platform: Platform type for context-specific inlining
    """
    from .script_inliner import inline_scripts

    file_path = repo_dir / pipeline_file
    if file_path.exists():
        inline_scripts(platform, file_path)


def create_platform_release_branches(
    repo_dir: Path,
    tag_name: str,
    tagged_commit: str,
) -> dict[str, str]:
    """
    Create 3 platform-specific release branches from a tagged commit.

    Works in detached HEAD context. Creates:
    - release/github-{tag_name}: Full repository with all CI/CD files
    - release/gitlab-{tag_name}: Excludes action.yml and bitbucket-pipelines.yml
    - release/bitbucket-{tag_name}: Excludes action.yml and .gitlab-ci.template.yml

    Args:
        repo_dir: Path to the repository
        tag_name: Tag name (e.g., "v1.0.1")
        tagged_commit: Git commit SHA or ref pointing to the tagged commit

    Returns:
        Dictionary mapping platform names to their branch names:
        {
            "github": "release/github-v1.0.1",
            "gitlab": "release/gitlab-v1.0.1",
            "bitbucket": "release/bitbucket-v1.0.1",
        }

    Raises:
        RuntimeError: If git operations fail or tagged_commit is invalid.
    """
    platforms: dict[str, tuple[Platform, list[str]]] = {
        "github": ("github", []),
        "gitlab": ("gitlab", ["action.yml", "bitbucket-pipelines.yml"]),
        "bitbucket": ("bitbucket", ["action.yml", ".gitlab-ci.template.yml"]),
    }

    branch_map = {}

    try:
        # Verify the tagged commit exists
        subprocess.run(
            ["git", "rev-list", "-n", "1", tagged_commit],
            cwd=repo_dir,
            check=True,
            capture_output=True,
        )

        for platform_key, (platform, files_to_remove) in platforms.items():
            branch_name = f"release/{platform_key}-{tag_name}"
            branch_map[platform_key] = branch_name

            # Delete branch if it exists (for rerun safety)
            if _branch_exists(repo_dir, branch_name):
                subprocess.run(
                    ["git", "branch", "-D", branch_name],
                    cwd=repo_dir,
                    check=True,
                    capture_output=True,
                )

            # Create new branch from tagged commit (works in detached HEAD)
            subprocess.run(
                ["git", "checkout", "-b", branch_name, tagged_commit],
                cwd=repo_dir,
                check=True,
                capture_output=True,
            )

            # Remove platform-specific files if any
            if files_to_remove:
                for file_to_remove in files_to_remove:
                    _remove_file_gracefully(repo_dir, file_to_remove)

                # Check if there are changes to commit
                status = subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=repo_dir,
                    capture_output=True,
                    text=True,
                )

                if status.stdout.strip():
                    subprocess.run(
                        ["git", "add", "."],
                        cwd=repo_dir,
                        check=True,
                        capture_output=True,
                    )
                    subprocess.run(
                        ["git", "commit", "-m", f"Remove {platform} incompatible files"],
                        cwd=repo_dir,
                        check=True,
                        capture_output=True,
                    )

        return branch_map

    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"Failed to create platform release branches: {e.stderr}"
        ) from e


def _remove_file_gracefully(repo_dir: Path, file_path: str) -> None:
    """
    Remove a file from git and disk gracefully.

    Uses git rm --cached --ignore-unmatch to handle missing files silently,
    then removes the file from disk if it exists.

    Args:
        repo_dir: Path to the repository
        file_path: Relative path to the file to remove
    """
    # Remove from git index (--ignore-unmatch prevents error if not tracked)
    subprocess.run(
        ["git", "rm", "--cached", "--ignore-unmatch", file_path],
        cwd=repo_dir,
        capture_output=True,
    )

    # Remove from disk if it exists
    disk_path = repo_dir / file_path
    if disk_path.exists():
        disk_path.unlink()
