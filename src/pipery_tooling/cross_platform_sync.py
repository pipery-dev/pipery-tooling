"""Cross-platform repository synchronization for GitLab and Bitbucket."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, urlunparse

import requests

GIT_CREDENTIALS_HELPER = """
store_credentials() {
    export GIT_USERNAME="$1"
    export GIT_PASSWORD="$2"
}
read_credentials() {
    echo "$GIT_USERNAME:$GIT_PASSWORD"
}
"""


logger = logging.getLogger(__name__)


@dataclass
class SyncReport:
    """Report of sync operation results."""
    successful: list[str]
    failed: dict[str, str]
    timestamp: str
    platform: str

    def to_dict(self) -> dict:
        return {
            "platform": self.platform,
            "timestamp": self.timestamp,
            "successful": self.successful,
            "failed": self.failed,
            "summary": {
                "total": len(self.successful) + len(self.failed),
                "successful": len(self.successful),
                "failed": len(self.failed),
            },
        }


class GitLabAPI:
    """GitLab API client for repository management."""

    def __init__(self, base_url: str = "https://gitlab.com", token: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.token = token or os.getenv("GITLAB_TOKEN")
        if not self.token:
            logger.error("GitLab token not provided. Set GITLAB_TOKEN environment variable or pass token parameter.")
            raise ValueError(
                "GitLab token not provided. Set GITLAB_TOKEN environment variable or pass token parameter."
            )
        logger.info("GitLab API initialized with token from environment or parameters")
        self.headers = {
            "PRIVATE-TOKEN": self.token,
            "Content-Type": "application/json",
        }

    def get_project(self, project_id: str) -> dict | None:
        """Get project details. Returns None if project doesn't exist."""
        url = f"{self.base_url}/api/v4/projects/{self._encode_project_id(project_id)}"
        logger.debug(f"Looking up GitLab project at URL: {url}")
        response = requests.get(url, headers=self.headers, timeout=10)
        logger.debug(f"GitLab lookup response: {response.status_code}")
        if response.status_code == 404:
            logger.debug(f"Project '{project_id}' not found by direct lookup, trying search...")
            # Try searching across all projects
            return self._search_project(project_id)
        response.raise_for_status()
        logger.debug(f"Found project '{project_id}' on GitLab")
        return response.json()

    def _search_project(self, search_term: str) -> dict | None:
        """Search for a project by name across all namespaces."""
        url = f"{self.base_url}/api/v4/projects"
        params = {"search": search_term, "simple": "true"}
        response = requests.get(url, headers=self.headers, params=params, timeout=10)
        if response.status_code == 200:
            projects = response.json()
            # Return the first matching project
            if projects:
                logger.debug(f"Found {len(projects)} project(s) matching '{search_term}'")
                return projects[0]
            logger.debug(f"No projects found matching '{search_term}'")
        return None

    def create_project(
        self,
        name: str,
        description: str = "",
        visibility: str = "public",
        group_id: int | None = None,
    ) -> dict:
        """Create a new GitLab project."""
        url = f"{self.base_url}/api/v4/projects"
        # GitLab API requires both name and path; path must be URL-safe
        # Convert name to path by replacing hyphens and special chars with underscores
        path = name.replace("-", "_").lower()
        data = {
            "name": name,
            "path": path,
            "description": description,
            "visibility": visibility,
        }
        if group_id:
            data["namespace_id"] = group_id

        logger.debug(f"Creating GitLab project with data: {data}")
        response = requests.post(url, headers=self.headers, json=data, timeout=10)
        if response.status_code != 201:
            logger.error(f"GitLab API error {response.status_code}: {response.text}")
        response.raise_for_status()
        return response.json()

    def get_project_url(self, project_id: str) -> str:
        """Get HTTPS clone URL for a project."""
        project = self.get_project(project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found on GitLab")
        return project["http_url_to_repo"]

    def push_branch(self, project_id: str, branch_name: str, local_repo_path: str, project: dict | None = None) -> None:
        """Push a branch to GitLab project using secure credential passing.

        Args:
            project_id: Project ID or name
            branch_name: Name of the branch to push
            local_repo_path: Path to local repository
            project: Optional project dict (if already looked up) to avoid redundant API calls
        """
        if not project:
            project = self.get_project(project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found on GitLab")

        clone_url = project["http_url_to_repo"]

        # Configure git to use credential helper for secure token passing
        # Avoid embedding token in command line arguments (visible in process listings)
        subprocess.run(
            ["git", "config", "credential.helper", "store"],
            cwd=local_repo_path,
            check=True,
            capture_output=True,
        )

        # Prepare credentials in the format git expects
        credentials = f"https://oauth2:{self.token}@{urlparse(clone_url).netloc}\n"

        # Push using the clean URL, credentials will be retrieved from credential helper
        env = os.environ.copy()
        subprocess.run(
            ["git", "push", clone_url, f"{branch_name}:refs/heads/{branch_name}"],
            cwd=local_repo_path,
            input=credentials,
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )

    def create_tag(self, project_id: str, tag_name: str, ref: str, message: str = "") -> dict:
        """Create a tag in GitLab project."""
        url = f"{self.base_url}/api/v4/projects/{self._encode_project_id(project_id)}/repository/tags"
        data = {
            "tag_name": tag_name,
            "ref": ref,
        }
        if message:
            data["message"] = message

        response = requests.post(url, headers=self.headers, json=data, timeout=10)
        response.raise_for_status()
        return response.json()

    def get_tag(self, project_id: str, tag_name: str) -> dict | None:
        """Get tag details. Returns None if tag doesn't exist."""
        url = f"{self.base_url}/api/v4/projects/{self._encode_project_id(project_id)}/repository/tags/{tag_name}"
        response = requests.get(url, headers=self.headers, timeout=10)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    def list_branches(self, project_id: str) -> list[dict]:
        """List all branches in a project."""
        url = f"{self.base_url}/api/v4/projects/{self._encode_project_id(project_id)}/repository/branches"
        response = requests.get(url, headers=self.headers, timeout=10)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _encode_project_id(project_id: str) -> str:
        """Encode project ID for URL (URL-encoded format for namespace/project)."""
        return project_id.replace("/", "%2F")


class BitbucketAPI:
    """Bitbucket API client for repository management."""

    def __init__(self, workspace: str, token: str | None = None):
        self.base_url = "https://api.bitbucket.org/2.0"
        self.workspace = workspace
        self.token = token or os.getenv("BITBUCKET_TOKEN")
        if not self.token:
            logger.error("Bitbucket token not provided. Set BITBUCKET_TOKEN environment variable or pass token parameter.")
            raise ValueError(
                "Bitbucket token not provided. Set BITBUCKET_TOKEN environment variable or pass token parameter."
            )
        logger.info(f"Bitbucket API initialized for workspace '{workspace}' with token from environment or parameters")
        self.auth = ("x-token-auth", self.token)

    def get_repository(self, repo_slug: str) -> dict | None:
        """Get repository details. Returns None if repo doesn't exist."""
        url = f"{self.base_url}/repositories/{self.workspace}/{repo_slug}"
        response = requests.get(url, auth=self.auth, timeout=10)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    def create_repository(
        self,
        repo_slug: str,
        description: str = "",
        is_private: bool = False,
    ) -> dict:
        """Create a new Bitbucket repository."""
        url = f"{self.base_url}/repositories/{self.workspace}/{repo_slug}"
        data = {
            "scm": "git",
            "description": description,
            "is_private": is_private,
        }
        response = requests.post(url, auth=self.auth, json=data, timeout=10)
        response.raise_for_status()
        return response.json()

    def get_repository_url(self, repo_slug: str) -> str:
        """Get HTTPS clone URL for a repository."""
        repo = self.get_repository(repo_slug)
        if not repo:
            raise ValueError(f"Repository {repo_slug} not found on Bitbucket")
        # Get HTTPS link from links
        for link in repo.get("links", {}).get("clone", []):
            if link.get("name") == "https":
                return link["href"]
        raise ValueError(f"No HTTPS clone URL found for {repo_slug}")

    def push_branch(self, repo_slug: str, branch_name: str, local_repo_path: str) -> None:
        """Push a branch to Bitbucket repository using secure credential passing."""
        repo = self.get_repository(repo_slug)
        if not repo:
            raise ValueError(f"Repository {repo_slug} not found on Bitbucket")

        clone_url = self.get_repository_url(repo_slug)

        # Configure git to use credential helper for secure token passing
        # Avoid embedding token in command line arguments (visible in process listings)
        subprocess.run(
            ["git", "config", "credential.helper", "store"],
            cwd=local_repo_path,
            check=True,
            capture_output=True,
        )

        # Prepare credentials in Bitbucket format
        credentials = f"https://x-token-auth:{self.token}@{urlparse(clone_url).netloc}\n"

        # Push using the clean URL, credentials will be retrieved from credential helper
        env = os.environ.copy()
        subprocess.run(
            ["git", "push", clone_url, f"{branch_name}:refs/heads/{branch_name}"],
            cwd=local_repo_path,
            input=credentials,
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )

    def create_tag(self, repo_slug: str, tag_name: str, commit_hash: str) -> dict:
        """Create a tag in Bitbucket repository."""
        url = f"{self.base_url}/repositories/{self.workspace}/{repo_slug}/refs/tags/{tag_name}"
        data = {
            "object": {
                "type": "commit",
                "hash": commit_hash,
            }
        }
        response = requests.post(url, auth=self.auth, json=data, timeout=10)
        response.raise_for_status()
        return response.json()

    def get_tag(self, repo_slug: str, tag_name: str) -> dict | None:
        """Get tag details. Returns None if tag doesn't exist."""
        url = f"{self.base_url}/repositories/{self.workspace}/{repo_slug}/refs/tags/{tag_name}"
        response = requests.get(url, auth=self.auth, timeout=10)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    def list_branches(self, repo_slug: str) -> list[dict]:
        """List all branches in a repository."""
        url = f"{self.base_url}/repositories/{self.workspace}/{repo_slug}/refs/branches"
        response = requests.get(url, auth=self.auth, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("values", [])


class RepositorySynchronizer:
    """Synchronize repositories across platforms."""

    # Base files and directories to exclude from sync
    # Platform-specific configs (.gitlab-ci.yml, bitbucket-pipelines.yml) are handled separately
    # by _should_exclude_file() based on target platform
    # Note: .git is intentionally NOT excluded as it's needed for git operations (commit/push)
    EXCLUDE_PATTERNS = {
        ".github",
        ".gitignore",
        ".bitbucket",
        "action.yml",
        ".releases",
        ".tags",
    }

    # Platform-specific CI/CD files
    PLATFORM_CONFIG_FILES = {
        ".gitlab-ci.yml",
        "bitbucket-pipelines.yml",
    }

    def __init__(
        self,
        github_token: str | None = None,
    ):
        self.github_token = github_token or os.getenv("GITHUB_TOKEN")

    def _should_exclude_file(self, filename: str, target_platform: str) -> bool:
        """
        Determine if a file should be excluded based on target platform.

        Platform-specific CI/CD files are preserved for their target platform:
        - .gitlab-ci.yml is kept when syncing to GitLab, excluded for Bitbucket
        - bitbucket-pipelines.yml is kept when syncing to Bitbucket, excluded for GitLab

        Args:
            filename: Name of the file to check
            target_platform: Target platform ('gitlab' or 'bitbucket')

        Returns:
            True if file should be excluded, False otherwise
        """
        # Check base exclude patterns
        if filename in self.EXCLUDE_PATTERNS:
            return True

        # Platform-specific config files: keep for target, exclude for others
        if filename == ".gitlab-ci.yml":
            return target_platform != "gitlab"
        if filename == "bitbucket-pipelines.yml":
            return target_platform != "bitbucket"

        return False

    def sync_to_platform(
        self,
        github_repo: str,
        platform: str,
        auth_token: str | None = None,
        platform_config: dict | None = None,
    ) -> dict:
        """
        Sync a GitHub repository to GitLab or Bitbucket.

        Args:
            github_repo: GitHub repository in format 'owner/repo'
            platform: 'gitlab' or 'bitbucket'
            auth_token: Authentication token for target platform
            platform_config: Additional config (e.g., {'group_id': 123} for GitLab)

        Returns:
            dict with sync status and details
        """
        if platform not in ("gitlab", "bitbucket"):
            raise ValueError(f"Unknown platform: {platform}")

        platform_config = platform_config or {}

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir_path = Path(tmpdir)

                # Clone GitHub repo
                logger.info(f"Cloning GitHub repo: {github_repo}")
                github_clone_url = f"https://github.com/{github_repo}.git"
                local_repo_path = tmpdir_path / "repo"

                self._clone_repo(github_clone_url, str(local_repo_path))

                # Extract repo name
                repo_name = github_repo.split("/")[-1]

                if platform == "gitlab":
                    return self._sync_to_gitlab(
                        repo_name, github_repo, str(local_repo_path), auth_token, platform_config
                    )
                else:
                    return self._sync_to_bitbucket(
                        repo_name, github_repo, str(local_repo_path), auth_token, platform_config
                    )
        except Exception as e:
            logger.error(f"Error syncing {github_repo} to {platform}: {e}")
            return {
                "status": "failed",
                "error": str(e),
                "repo": github_repo,
                "platform": platform,
            }

    def _sync_to_gitlab(
        self,
        repo_name: str,
        github_repo: str,
        local_repo_path: str,
        auth_token: str | None,
        platform_config: dict,
    ) -> dict:
        """Sync repository to GitLab."""
        gitlab = GitLabAPI(token=auth_token)
        group_id = platform_config.get("group_id")

        # Check if project exists (use sanitized path for lookup)
        # Sanitize the name to match what was/will be created
        sanitized_path = repo_name.replace("-", "_").lower()
        logger.info(f"Checking GitLab for project: {repo_name} (path: {sanitized_path})")

        # Try both the original name and sanitized path for lookup
        existing = gitlab.get_project(repo_name)
        logger.info(f"Lookup by original name '{repo_name}': {'found' if existing else 'not found'}")

        # Store the actual project ID for later API calls
        gitlab.project_id = existing.get("id") if existing else None

        if not existing:
            existing = gitlab.get_project(sanitized_path)
            logger.info(f"Lookup by sanitized path '{sanitized_path}': {'found' if existing else 'not found'}")
            gitlab.project_id = existing.get("id") if existing else None

        if not existing:
            logger.info(f"Creating GitLab project: {repo_name}")
            try:
                gitlab.create_project(
                    name=repo_name,
                    description=f"Synced from GitHub: {github_repo}",
                    visibility="public",
                    group_id=group_id,
                )
                # Re-fetch the newly created project
                existing = gitlab.get_project(repo_name) or gitlab.get_project(sanitized_path)
                if existing:
                    gitlab.project_id = existing.get("id")
            except Exception as e:
                logger.error(f"Failed to create GitLab project: {e}")
                return {
                    "status": "failed",
                    "error": f"Failed to create project: {e}",
                    "repo": github_repo,
                    "platform": "gitlab",
                }

        # Sync code files (passing the existing project to avoid redundant lookups)
        logger.info(f"Syncing files to GitLab: {repo_name}")
        self._sync_files_to_gitlab(repo_name, local_repo_path, gitlab, existing)

        return {
            "status": "success",
            "repo": github_repo,
            "platform": "gitlab",
            "target_repo": repo_name,
        }

    def _sync_to_bitbucket(
        self,
        repo_name: str,
        github_repo: str,
        local_repo_path: str,
        auth_token: str | None,
        platform_config: dict,
    ) -> dict:
        """Sync repository to Bitbucket."""
        workspace = platform_config.get("workspace") or os.getenv("BITBUCKET_WORKSPACE")
        if not workspace or workspace.strip() == "":
            logger.warning(f"Skipping Bitbucket sync for {github_repo}: BITBUCKET_WORKSPACE not provided. Set BITBUCKET_WORKSPACE environment variable or provide workspace in platform_config.")
            return {
                "status": "skipped",
                "error": "Bitbucket workspace not provided. Set BITBUCKET_WORKSPACE environment variable.",
                "repo": github_repo,
                "platform": "bitbucket",
            }

        bitbucket = BitbucketAPI(workspace=workspace, token=auth_token)

        # Check if repo exists
        logger.info(f"Checking Bitbucket for repo: {repo_name}")
        existing = bitbucket.get_repository(repo_name)

        if not existing:
            logger.info(f"Creating Bitbucket repository: {repo_name}")
            try:
                bitbucket.create_repository(
                    repo_slug=repo_name,
                    description=f"Synced from GitHub: {github_repo}",
                    is_private=False,
                )
            except Exception as e:
                logger.error(f"Failed to create Bitbucket repo: {e}")
                return {
                    "status": "failed",
                    "error": f"Failed to create repository: {e}",
                    "repo": github_repo,
                    "platform": "bitbucket",
                }

        # Sync code files
        logger.info(f"Syncing files to Bitbucket: {repo_name}")
        self._sync_files_to_bitbucket(repo_name, local_repo_path, bitbucket)

        return {
            "status": "success",
            "repo": github_repo,
            "platform": "bitbucket",
            "target_repo": repo_name,
        }

    def _sync_files_to_gitlab(self, project_name: str, local_repo_path: str, gitlab: GitLabAPI, project: dict | None = None) -> None:
        """Push synced files to GitLab with platform-aware filtering.

        Args:
            project_name: Name of the project
            local_repo_path: Path to local repository
            gitlab: GitLab API client
            project: Optional project dict to avoid redundant lookups
        """
        # Prepare sync branch
        sync_branch = "sync/github-main"
        subprocess.run(
            ["git", "checkout", "-b", sync_branch],
            cwd=local_repo_path,
            check=True,
            capture_output=True,
        )

        # Remove excluded files/dirs (platform-aware for GitLab)
        self._remove_excluded_files(Path(local_repo_path), target_platform="gitlab")

        # Commit and push
        subprocess.run(
            ["git", "add", "-A"],
            cwd=local_repo_path,
            check=True,
            capture_output=True,
        )

        result = subprocess.run(
            ["git", "commit", "-m", "Sync from GitHub"],
            cwd=local_repo_path,
            capture_output=True,
            text=True,
        )

        logger.debug(f"Git commit result: returncode={result.returncode}, stdout={result.stdout[:200] if result.stdout else ''}, stderr={result.stderr[:200] if result.stderr else ''}")

        if result.returncode == 0 or "nothing to commit" in result.stdout.lower():
            # Push to GitLab (even if there's nothing new to commit, we still want to create the branch)
            logger.info(f"Pushing to GitLab: {project_name}")
            try:
                gitlab.push_branch(project_name, sync_branch, local_repo_path, project=project)
                logger.info(f"Successfully pushed sync branch to GitLab")
            except Exception as e:
                logger.error(f"Failed to push to GitLab: {e}")
        else:
            logger.error(f"Git commit failed: {result.stderr}")

    def _sync_files_to_bitbucket(
        self, repo_slug: str, local_repo_path: str, bitbucket: BitbucketAPI
    ) -> None:
        """Push synced files to Bitbucket with platform-aware filtering."""
        # Prepare sync branch
        sync_branch = "sync/github-main"
        subprocess.run(
            ["git", "checkout", "-b", sync_branch],
            cwd=local_repo_path,
            check=True,
            capture_output=True,
        )

        # Remove excluded files/dirs (platform-aware for Bitbucket)
        self._remove_excluded_files(Path(local_repo_path), target_platform="bitbucket")

        # Commit and push
        subprocess.run(
            ["git", "add", "-A"],
            cwd=local_repo_path,
            check=True,
            capture_output=True,
        )

        result = subprocess.run(
            ["git", "commit", "-m", "Sync from GitHub"],
            cwd=local_repo_path,
            capture_output=True,
            text=True,
        )

        logger.debug(f"Git commit result: returncode={result.returncode}, stdout={result.stdout[:200] if result.stdout else ''}, stderr={result.stderr[:200] if result.stderr else ''}")

        if result.returncode == 0 or "nothing to commit" in result.stdout.lower():
            # Push to Bitbucket (even if there's nothing new to commit, we still want to create the branch)
            logger.info(f"Pushing to Bitbucket: {repo_slug}")
            try:
                bitbucket.push_branch(repo_slug, sync_branch, local_repo_path)
                logger.info(f"Successfully pushed sync branch to Bitbucket")
            except Exception as e:
                logger.error(f"Failed to push to Bitbucket: {e}")
        else:
            logger.error(f"Git commit failed: {result.stderr}")

    def _backup_file(self, filepath: Path, backup_suffix: str = ".backup") -> Path:
        """
        Create a backup copy of a file before it would be overwritten.

        Args:
            filepath: Path to the file to backup
            backup_suffix: Suffix to append to backup filename

        Returns:
            Path to the backup file
        """
        if not filepath.exists():
            return None

        backup_path = filepath.parent / (filepath.name + backup_suffix)
        if filepath.is_dir():
            if backup_path.exists():
                shutil.rmtree(backup_path)
            shutil.copytree(filepath, backup_path)
        else:
            shutil.copy2(filepath, backup_path)

        logger.info(f"Created backup: {backup_path}")
        return backup_path

    def _remove_excluded_files(self, repo_path: Path, target_platform: str | None = None) -> None:
        """
        Remove excluded files and directories from repository.

        Args:
            repo_path: Path to the repository
            target_platform: Target platform ('gitlab' or 'bitbucket') for platform-aware filtering
        """
        # Remove base excluded patterns
        for item in self.EXCLUDE_PATTERNS:
            item_path = repo_path / item
            if item_path.exists():
                self._backup_file(item_path)
                if item_path.is_dir():
                    shutil.rmtree(item_path)
                else:
                    item_path.unlink()
                logger.debug(f"Removed: {item}")

        # Handle platform-specific config files
        if target_platform:
            for config_file in self.PLATFORM_CONFIG_FILES:
                if self._should_exclude_file(config_file, target_platform):
                    config_path = repo_path / config_file
                    if config_path.exists():
                        self._backup_file(config_path)
                        config_path.unlink()
                        logger.debug(f"Removed platform config: {config_file} (not for {target_platform})")
                else:
                    logger.debug(f"Preserving platform config: {config_file} (for {target_platform})")

    def _clone_repo(self, clone_url: str, target_path: str) -> None:
        """Clone a repository."""
        subprocess.run(
            ["git", "clone", "--quiet", clone_url, target_path],
            check=True,
            capture_output=True,
        )

    def sync_all_platforms(
        self,
        repos: list[str] | None = None,
        platforms: list[str] | None = None,
        gitlab_token: str | None = None,
        bitbucket_token: str | None = None,
        bitbucket_workspace: str | None = None,
    ) -> SyncReport:
        """
        Sync all or specified repos to all or specified platforms.

        Args:
            repos: List of repos in format 'owner/repo'. If None, syncs default pipery repos.
            platforms: List of platforms ('gitlab', 'bitbucket'). If None, syncs to all.
            gitlab_token: GitLab authentication token
            bitbucket_token: Bitbucket authentication token
            bitbucket_workspace: Bitbucket workspace name

        Returns:
            SyncReport with results
        """
        if repos is None:
            repos = self._get_default_repos()

        if platforms is None:
            platforms = ["gitlab", "bitbucket"]

        successful = []
        failed = {}

        for repo in repos:
            for platform in platforms:
                try:
                    logger.info(f"Syncing {repo} to {platform}")
                    platform_config = {}
                    if platform == "bitbucket" and bitbucket_workspace:
                        platform_config["workspace"] = bitbucket_workspace

                    token = gitlab_token if platform == "gitlab" else bitbucket_token
                    result = self.sync_to_platform(repo, platform, auth_token=token, platform_config=platform_config)

                    if result.get("status") == "success":
                        successful.append(f"{repo}→{platform}")
                    else:
                        failed[f"{repo}→{platform}"] = result.get("error", "Unknown error")
                except Exception as e:
                    failed[f"{repo}→{platform}"] = str(e)

        return SyncReport(
            successful=successful,
            failed=failed,
            timestamp=datetime.now().isoformat(),
            platform="all",
        )

    @staticmethod
    def _get_default_repos() -> list[str]:
        """Get default list of Pipery repos to sync."""
        return [
            "pipery-dev/pipery-cpp-ci",
            "pipery-dev/pipery-golang-ci",
            "pipery-dev/pipery-java-ci",
            "pipery-dev/pipery-npm-ci",
            "pipery-dev/pipery-python-ci",
            "pipery-dev/pipery-rust-ci",
            "pipery-dev/pipery-docker-ci",
            "pipery-dev/pipery-terraform-ci",
            "pipery-dev/pipery-ansible-cd",
            "pipery-dev/pipery-argocd-cd",
            "pipery-dev/pipery-cloudrun-cd",
            "pipery-dev/pipery-docker-cd",
            "pipery-dev/pipery-helm-cd",
            "pipery-dev/pipery-terraform-cd",
        ]
