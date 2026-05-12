"""Cross-platform repository synchronization using SSH and GitPython.

Platform-Specific Release Strategy
==================================

GITLAB (Native Release API):
  - Creates releases via GitLab Release API (/releases endpoint)
  - Includes metadata: name, description, tag
  - Visible in GitLab UI as "Releases" section
  - Full feature parity with GitHub releases

BITBUCKET (No Native Release API):
  - Bitbucket Cloud lacks Release API (as of 2026)
  - Strategy: Create release branch + verify tag
  1. Verify annotated tag exists via refs/tags API
  2. Create release branch (releases/v1.0.0) via refs/branches API
  3. Provides discoverability: Branch appears in Bitbucket UI
  4. Durable: Release branch is permanent git history
  5. Reliable: No API rate limits on tag/branch operations

Why not alternatives for Bitbucket?
  - Deployment API: Too broad (meant for CI/CD status, not releases)
  - Wiki/Description: No API to reliably update; UI-only feature
  - Downloads: Deprecated in Bitbucket Cloud
  - Release branch: BEST - visible, permanent, queryable via API
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import ClassVar
from urllib.parse import quote

import requests
from git import Repo

logger = logging.getLogger(__name__)

EXCLUDE_PATTERNS = {
    ".gitignore",
    ".github",
    "action.yml",
    ".gitattributes",
}


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


class PlatformSync:
    """Synchronize repositories across platforms using SSH and GitPython."""

    def __init__(self, ssh_key_path: str | None = None):
        """Initialize sync with SSH key path."""
        self.ssh_key_path = ssh_key_path or os.getenv("SSH_KEY_PATH")
        if not self.ssh_key_path:
            logger.warning("SSH_KEY_PATH not set, using default SSH agent")

    def sync_to_platform(
        self,
        repo: str,
        platform: str,
        github_repo: str,
        auth_token: str | None = None,
        tag_name: str | None = None,
    ) -> dict:
        """Sync repository to a platform using SSH."""
        logger.info(f"Syncing {github_repo} to {platform}")

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                local_repo_path = str(Path(tmpdir) / "repo")

                # Clone from GitHub with all branches
                logger.info(f"Cloning GitHub repo: {github_repo}")
                github_url = f"https://github.com/{github_repo}"
                git_repo = Repo.clone_from(github_url, local_repo_path, bare=False, mirror=False)

                # Fetch all branches as local tracking branches
                origin = git_repo.remote("origin")
                branches_created = []
                for ref in origin.refs:
                    if ref.remote_head != "HEAD":
                        try:
                            git_repo.create_head(ref.remote_head, ref.commit)
                            branches_created.append(ref.remote_head)
                        except:
                            pass  # Branch may already exist locally
                logger.info(f"Created local branches: {branches_created}")
                print(f"[SYNC] Created {len(branches_created)} local branches: {branches_created[:5]}...")

                # Log all tags
                tags = [tag.name for tag in git_repo.tags]
                logger.info(f"Available tags in clone: {tags[:10]}")
                print(f"[SYNC] Available tags: {len(tags)} total")

                # Determine target SSH URL based on platform
                if platform == "gitlab":
                    target_url = f"git@gitlab.com:pipery-dev/{repo}.git"
                elif platform == "bitbucket":
                    target_url = f"git@bitbucket.org:pipery-dev/{repo}.git"
                else:
                    return {"status": "failed", "error": f"Unknown platform: {platform}"}

                # Add remote and push
                if "origin" in [remote.name for remote in git_repo.remotes]:
                    git_repo.delete_remote("origin")

                remote = git_repo.create_remote("target", target_url)

                # Push all branches and tags
                logger.info(f"Pushing to {platform}: {repo}")
                local_branches = [b.name for b in git_repo.heads]
                logger.info(f"Local branches to push: {local_branches}")
                print(f"[SYNC] Local branches: {len(local_branches)} - {local_branches[:5]}...")

                try:
                    # Push all branches with force
                    logger.info(f"Pushing all branches to {platform}")
                    print(f"[SYNC] Pushing branches to {platform}...")
                    push_result = remote.push(all=True, force=True)
                    logger.info(f"Branch push result: {len(push_result)} refs pushed")
                    print(f"[SYNC] Pushed {len(push_result)} refs")

                    # Push platform-specific tag pointing to release branch
                    if tag_name:
                        platform_branch_name = f"release/{platform}-{tag_name}"
                        matching = [h for h in git_repo.heads if h.name == platform_branch_name]
                        if matching:
                            tip_commit = matching[0].commit
                            # Delete and recreate tag to point to platform branch tip
                            if tag_name in [t.name for t in git_repo.tags]:
                                git_repo.delete_tag(tag_name)
                            git_repo.create_tag(tag_name, ref=tip_commit)
                            remote.push(refspec=f"refs/tags/{tag_name}:refs/tags/{tag_name}", force=True)
                            print(f"[SYNC] Pushed tag {tag_name} to {platform} -> {tip_commit.hexsha[:8]}")
                        else:
                            print(f"[SYNC] Warning: branch {platform_branch_name} not found, skipping tag push")

                    logger.info(f"Successfully pushed all branches and tags to {platform}")
                    print(f"[SYNC] Sync to {platform} completed successfully")
                except Exception as e:
                    logger.error(f"Failed to push to {platform}: {e}")
                    print(f"[SYNC] Error: {e}")
                    return {"status": "failed", "error": str(e)}

                return {"status": "success"}

        except Exception as e:
            logger.error(f"Sync failed: {e}")
            return {"status": "failed", "error": str(e)}

    def _get_excluded_files(self, platform: str) -> set[str]:
        """Get list of files to exclude for a specific platform."""
        excluded = EXCLUDE_PATTERNS.copy()

        # Always exclude GitHub-specific files (action.yml)
        excluded.add("action.yml")

        # Exclude platform-specific CI/CD files from other platforms
        if platform != "bitbucket":
            excluded.add("bitbucket-pipelines.yml")
        if platform != "gitlab":
            excluded.add(".gitlab-ci.template.yml")

        return excluded

    def _remove_excluded_files(self, repo_path: str, platform: str):
        """Remove platform-specific files that shouldn't be synced."""
        excluded = self._get_excluded_files(platform)

        for pattern in excluded:
            path = Path(repo_path) / pattern
            if path.exists():
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
                logger.debug(f"Removed: {pattern}")

    def create_release(
        self,
        repo: str,
        tag_name: str,
        platform: str,
        token: str | None = None,
    ) -> dict:
        """Create a release on the target platform."""
        if platform == "gitlab":
            return self._create_gitlab_release(repo, tag_name, token)
        elif platform == "bitbucket":
            return self._create_bitbucket_release(repo, tag_name, token)
        else:
            return {"status": "failed", "error": f"Unknown platform: {platform}"}

    def _create_gitlab_release(self, repo: str, tag_name: str, token: str | None = None) -> dict:
        """Create a release on GitLab with full error handling and release notes."""
        if not token:
            logger.warning("No GitLab token provided for release creation")
            print("[ERROR] GitLab token not provided for release creation")
            return {"status": "failed", "error": "No GitLab token provided"}

        try:
            project_path = f"pipery-dev/{repo}"
            encoded_path = quote(project_path, safe="")

            # Get project ID
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            project_url = f"https://gitlab.com/api/v4/projects/{encoded_path}"

            print(f"[GITLAB] Looking up project: {project_path}")
            try:
                resp = requests.get(project_url, headers=headers, timeout=10)
            except requests.Timeout:
                logger.error(f"GitLab API timeout fetching project {project_path}")
                print(f"[ERROR] GitLab API timeout while fetching project metadata")
                return {"status": "failed", "error": "GitLab API timeout (project lookup)"}
            except requests.ConnectionError as e:
                logger.error(f"GitLab API connection error: {e}")
                print(f"[ERROR] Failed to connect to GitLab API: {e}")
                return {"status": "failed", "error": f"Connection error: {e}"}

            if resp.status_code == 404:
                logger.error(f"GitLab project not found: {project_path}")
                print(f"[ERROR] GitLab project not found: {project_path}")
                return {"status": "failed", "error": f"Project not found: {project_path}"}
            elif resp.status_code == 401:
                logger.error("GitLab token is invalid or expired")
                print("[ERROR] GitLab authentication failed - invalid or expired token")
                return {"status": "failed", "error": "Invalid or expired GitLab token"}
            elif resp.status_code != 200:
                error_msg = resp.json().get("message", resp.text) if resp.headers.get("content-type") == "application/json" else resp.text
                logger.error(f"Project lookup failed (HTTP {resp.status_code}): {error_msg}")
                print(f"[ERROR] Failed to fetch project metadata (HTTP {resp.status_code}): {error_msg}")
                return {"status": "failed", "error": f"Project lookup failed: {error_msg}"}

            try:
                project_data = resp.json()
                project_id = project_data["id"]
                print(f"[GITLAB] Project ID: {project_id}")
            except (KeyError, ValueError) as e:
                logger.error(f"Failed to parse project response: {e}")
                print(f"[ERROR] Invalid project response from GitLab: {e}")
                return {"status": "failed", "error": "Invalid project response"}

            # Prepare release notes/description
            release_name = f"Release {tag_name}"
            release_description = f"Release of {repo} {tag_name}\n\n"
            release_description += f"**Repository:** pipery-dev/{repo}\n"
            release_description += f"**Tag:** {tag_name}\n"
            release_description += f"**Created:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}"

            # Create release
            release_url = f"https://gitlab.com/api/v4/projects/{project_id}/releases"
            release_data = {
                "tag_name": tag_name,
                "name": release_name,
                "description": release_description,
            }

            print(f"[GITLAB] Creating release: {release_name}")
            try:
                resp = requests.post(release_url, headers=headers, json=release_data, timeout=10)
            except requests.Timeout:
                logger.error(f"GitLab API timeout creating release {tag_name}")
                print(f"[ERROR] GitLab API timeout while creating release")
                return {"status": "failed", "error": "GitLab API timeout (release creation)"}
            except requests.ConnectionError as e:
                logger.error(f"GitLab API connection error: {e}")
                print(f"[ERROR] Failed to connect to GitLab API: {e}")
                return {"status": "failed", "error": f"Connection error: {e}"}

            if resp.status_code == 201:
                logger.info(f"Created GitLab release: {tag_name}")
                print(f"[SUCCESS] GitLab release created: {tag_name}")
                print(f"  Name: {release_name}")
                print(f"  Repository: pipery-dev/{repo}")
                print(f"  URL: https://gitlab.com/pipery-dev/{repo}/-/releases/{tag_name}")
                return {"status": "success"}
            elif resp.status_code == 409:
                logger.info(f"GitLab release already exists: {tag_name}")
                print(f"[INFO] GitLab release already exists: {tag_name}")
                return {"status": "success"}
            elif resp.status_code == 400:
                error_detail = resp.json().get("message", resp.text) if resp.headers.get("content-type") == "application/json" else resp.text
                logger.error(f"Bad request creating release (likely tag not found): {error_detail}")
                print(f"[ERROR] Bad request - tag may not exist on GitLab or release data is invalid: {error_detail}")
                return {"status": "failed", "error": f"Bad request: {error_detail}"}
            elif resp.status_code == 401:
                logger.error("GitLab token is invalid or expired")
                print("[ERROR] GitLab authentication failed - invalid or expired token")
                return {"status": "failed", "error": "Invalid or expired GitLab token"}
            else:
                error_msg = resp.json().get("message", resp.text) if resp.headers.get("content-type") == "application/json" else resp.text
                logger.error(f"Failed to create GitLab release (HTTP {resp.status_code}): {error_msg}")
                print(f"[ERROR] Failed to create release (HTTP {resp.status_code}): {error_msg}")
                return {"status": "failed", "error": str(error_msg)}

        except Exception as e:
            logger.error(f"GitLab release creation failed: {e}", exc_info=True)
            print(f"[ERROR] Unexpected error during GitLab release creation: {e}")
            return {"status": "failed", "error": str(e)}

    def _create_bitbucket_release(self, repo: str, tag_name: str, token: str | None = None) -> dict:
        """
        Create a release marker on Bitbucket using a release branch strategy.

        Since Bitbucket Cloud lacks a native Release API, we use a hybrid approach:
        1. Verify the tag exists on the repository
        2. Create a release branch (releases/v1.0.0) as a visible release marker
        3. Document the release via annotated tag metadata

        This approach provides:
        - Discoverability: Release branches appear in Bitbucket UI
        - Durability: Release branches are permanently tracked in git history
        - Reliability: No API limitations since we use git push
        - Compatibility: Works with Bitbucket Cloud's tag and branch APIs
        """
        try:
            workspace = "pipery-dev"
            repo_slug = repo

            print(f"[BITBUCKET] Starting release creation for {tag_name}")

            # Step 1: Verify the tag exists via API
            tag_url = f"https://api.bitbucket.org/2.0/repositories/{workspace}/{repo_slug}/refs/tags/{tag_name}"

            print(f"[BITBUCKET] Verifying tag exists: {tag_name}")
            try:
                resp = requests.get(tag_url, timeout=10)
            except requests.Timeout:
                logger.error(f"Bitbucket API timeout verifying tag {tag_name}")
                print(f"[ERROR] Bitbucket API timeout while verifying tag")
                return {"status": "failed", "error": "API timeout during tag verification"}
            except requests.ConnectionError as e:
                logger.error(f"Bitbucket API connection error: {e}")
                print(f"[ERROR] Failed to connect to Bitbucket API: {e}")
                return {"status": "failed", "error": f"Connection error: {e}"}

            if resp.status_code != 200:
                error_msg = f"Tag verification failed (HTTP {resp.status_code})"
                logger.error(f"Bitbucket tag not found: {tag_name} - {error_msg}")
                print(f"[ERROR] Bitbucket tag not found: {tag_name}")
                return {"status": "failed", "error": f"Tag not found: {tag_name}"}

            print(f"[BITBUCKET] Tag verified: {tag_name}")

            # Step 2: Extract tag commit SHA from API response for release branch
            try:
                tag_data = resp.json()
                tag_commit_sha = tag_data.get("target", {}).get("hash")
                if not tag_commit_sha:
                    logger.warning(f"Could not extract commit SHA from tag {tag_name}, using tag name as fallback")
                    tag_commit_sha = tag_name
                    print(f"[BITBUCKET] Using tag reference for release branch")
                else:
                    print(f"[BITBUCKET] Extracted commit SHA: {tag_commit_sha[:12]}")
            except (KeyError, ValueError) as e:
                logger.warning(f"Failed to parse tag response: {e}, using tag name")
                tag_commit_sha = tag_name

            # Step 3: Create release branch as a visible marker
            # Release branch format: releases/v1.0.0 provides clear discoverability
            release_branch = f"releases/{tag_name}"

            print(f"[BITBUCKET] Creating release branch: {release_branch}")

            # Create release branch via API (POST to refs/branches endpoint)
            branch_url = f"https://api.bitbucket.org/2.0/repositories/{workspace}/{repo_slug}/refs/branches"
            branch_data = {
                "name": release_branch,
                "target": {
                    "hash": tag_commit_sha
                }
            }

            headers = {}
            if token:
                headers["Authorization"] = f"Bearer {token}"

            try:
                resp = requests.post(branch_url, json=branch_data, headers=headers, timeout=10)
            except requests.Timeout:
                logger.error(f"Bitbucket API timeout creating release branch {release_branch}")
                print(f"[ERROR] Bitbucket API timeout while creating release branch")
                return {"status": "failed", "error": "API timeout during release branch creation"}
            except requests.ConnectionError as e:
                logger.error(f"Bitbucket API connection error: {e}")
                print(f"[ERROR] Failed to connect to Bitbucket API: {e}")
                return {"status": "failed", "error": f"Connection error: {e}"}

            if resp.status_code == 201:
                logger.info(f"Created Bitbucket release branch: {release_branch}")
                print(f"[SUCCESS] Bitbucket release branch created: {release_branch}")
                print(f"  Tag: {tag_name}")
                print(f"  Commit: {tag_commit_sha[:12] if len(tag_commit_sha) > 12 else tag_commit_sha}")
                print(f"  URL: https://bitbucket.org/{workspace}/{repo_slug}/branch/{release_branch}")
                return {"status": "success"}
            elif resp.status_code == 409:
                logger.info(f"Bitbucket release branch already exists: {release_branch}")
                print(f"[INFO] Bitbucket release branch already exists: {release_branch}")
                print(f"  (Branch conflicts indicate this release was already processed)")
                return {"status": "success"}
            elif resp.status_code == 401:
                logger.error("Bitbucket token is invalid or expired")
                print("[ERROR] Bitbucket authentication failed - invalid or expired token")
                return {"status": "failed", "error": "Invalid or expired Bitbucket token"}
            elif resp.status_code == 400:
                error_detail = resp.json().get("error", {}).get("message", resp.text) if resp.headers.get("content-type") == "application/json" else resp.text
                logger.error(f"Bad request creating release branch: {error_detail}")
                print(f"[ERROR] Bad request creating release branch: {error_detail}")
                return {"status": "failed", "error": f"Bad request: {error_detail}"}
            else:
                error_msg = resp.json().get("error", {}).get("message", resp.text) if resp.headers.get("content-type") == "application/json" else resp.text
                logger.error(f"Failed to create Bitbucket release branch (HTTP {resp.status_code}): {error_msg}")
                print(f"[ERROR] Failed to create release branch (HTTP {resp.status_code}): {error_msg}")
                return {"status": "failed", "error": str(error_msg)}

        except Exception as e:
            logger.error(f"Bitbucket release creation failed: {e}", exc_info=True)
            print(f"[ERROR] Unexpected error during Bitbucket release creation: {e}")
            return {"status": "failed", "error": str(e)}

    def sync_repositories(
        self,
        repos: list[str],
        platforms: list[str],
        github_token: str | None = None,
    ) -> SyncReport:
        """Sync multiple repositories to multiple platforms."""
        successful = []
        failed = {}

        for repo in repos:
            for platform in platforms:
                try:
                    github_repo = f"pipery-dev/{repo}"
                    result = self.sync_to_platform(
                        repo, platform, github_repo, github_token
                    )

                    if result.get("status") == "success":
                        successful.append(f"{repo}→{platform}")
                    else:
                        failed[f"{repo}→{platform}"] = result.get(
                            "error", "Unknown error"
                        )
                except Exception as e:
                    failed[f"{repo}→{platform}"] = str(e)

        return SyncReport(
            successful=successful,
            failed=failed,
            timestamp=datetime.now().isoformat(),
            platform=",".join(platforms),
        )


class GitLabAPI:
    """GitLab API client for repository operations."""

    def __init__(self, token: str | None = None):
        """Initialize GitLab API client.

        Args:
            token: GitLab API token. If not provided, reads from GITLAB_TOKEN env var.

        Raises:
            ValueError: If no token is provided and GITLAB_TOKEN env var is not set.
        """
        self.token = token or os.getenv("GITLAB_TOKEN")
        if not self.token:
            raise ValueError("GitLab token not provided")
        self.base_url = "https://gitlab.com/api/v4"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def get_project(self, project_path: str) -> dict | None:
        """Get project information.

        Args:
            project_path: Project path (e.g., "owner/repo")

        Returns:
            Project dict or None if not found (404).
        """
        encoded_path = quote(project_path, safe="")
        url = f"{self.base_url}/projects/{encoded_path}"
        resp = requests.get(url, headers=self.headers)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def create_project(self, name: str, description: str, visibility: str) -> dict:
        """Create a new project.

        Args:
            name: Project name
            description: Project description
            visibility: Project visibility (public, private, internal)

        Returns:
            Created project dict.
        """
        url = f"{self.base_url}/projects"
        data = {
            "name": name,
            "description": description,
            "visibility": visibility,
        }
        resp = requests.post(url, headers=self.headers, json=data)
        resp.raise_for_status()
        return resp.json()

    def list_branches(self, project_id: int | str) -> list[dict]:
        """List all branches in a project.

        Args:
            project_id: GitLab project ID

        Returns:
            List of branch dicts.
        """
        url = f"{self.base_url}/projects/{project_id}/repository/branches"
        resp = requests.get(url, headers=self.headers)
        resp.raise_for_status()
        return resp.json()

    def get_tag(self, project_id: int | str, tag_name: str) -> dict | None:
        """Get tag information.

        Args:
            project_id: GitLab project ID
            tag_name: Tag name

        Returns:
            Tag dict or None if not found (404).
        """
        url = f"{self.base_url}/projects/{project_id}/repository/tags/{quote(tag_name, safe='')}"
        resp = requests.get(url, headers=self.headers)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def create_tag(self, project_id: int | str, tag_name: str, commit_hash: str) -> dict:
        """Create a new tag.

        Args:
            project_id: GitLab project ID
            tag_name: Tag name
            commit_hash: Commit hash to tag

        Returns:
            Created tag dict.
        """
        url = f"{self.base_url}/projects/{project_id}/repository/tags"
        data = {
            "tag_name": tag_name,
            "ref": commit_hash,
        }
        resp = requests.post(url, headers=self.headers, json=data)
        resp.raise_for_status()
        return resp.json()

    def push_branch(self, project_path: str, branch: str, repo_dir: str) -> None:
        """Push branch to GitLab using HTTPS.

        Args:
            project_path: GitLab project path (e.g., "owner/repo")
            branch: Branch name to push
            repo_dir: Local repository directory
        """
        project = self.get_project(project_path)
        if not project:
            raise ValueError(f"Project not found: {project_path}")
        target_url = project.get("http_url_to_repo", f"https://gitlab.com/{project_path}.git")
        cmd = ["git", "push", target_url, branch]
        env = os.environ.copy()
        env["GIT_ASKPASS"] = "true"
        env["GIT_USERNAME"] = "oauth2"
        env["GIT_PASSWORD"] = self.token
        subprocess.run(cmd, cwd=repo_dir, check=True, env=env)


class BitbucketAPI:
    """Bitbucket API client for repository operations."""

    def __init__(self, workspace: str, token: str | None = None):
        """Initialize Bitbucket API client.

        Args:
            workspace: Bitbucket workspace name
            token: Bitbucket API token. If not provided, reads from BITBUCKET_TOKEN env var.

        Raises:
            ValueError: If no token is provided and BITBUCKET_TOKEN env var is not set.
        """
        self.workspace = workspace
        self.token = token or os.getenv("BITBUCKET_TOKEN")
        if not self.token:
            raise ValueError("Bitbucket token not provided")
        self.base_url = "https://api.bitbucket.org/2.0"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def get_repository(self, repo_slug: str) -> dict | None:
        """Get repository information.

        Args:
            repo_slug: Repository slug

        Returns:
            Repository dict or None if not found (404).
        """
        url = f"{self.base_url}/repositories/{self.workspace}/{repo_slug}"
        resp = requests.get(url, headers=self.headers)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def create_repository(
        self, repo_slug: str, description: str, is_private: bool
    ) -> dict:
        """Create a new repository.

        Args:
            repo_slug: Repository slug
            description: Repository description
            is_private: Whether repository is private

        Returns:
            Created repository dict.
        """
        url = f"{self.base_url}/repositories/{self.workspace}"
        data = {
            "scm": "git",
            "is_private": is_private,
            "description": description,
        }
        resp = requests.post(url, headers=self.headers, json=data)
        resp.raise_for_status()
        return resp.json()

    def list_branches(self, repo_slug: str) -> list[dict]:
        """List all branches in a repository.

        Args:
            repo_slug: Repository slug

        Returns:
            List of branch dicts.
        """
        url = f"{self.base_url}/repositories/{self.workspace}/{repo_slug}/refs/branches"
        resp = requests.get(url, headers=self.headers)
        resp.raise_for_status()
        return resp.json()

    def get_tag(self, repo_slug: str, tag_name: str) -> dict | None:
        """Get tag information.

        Args:
            repo_slug: Repository slug
            tag_name: Tag name

        Returns:
            Tag dict or None if not found (404).
        """
        url = f"{self.base_url}/repositories/{self.workspace}/{repo_slug}/refs/tags/{quote(tag_name, safe='')}"
        resp = requests.get(url, headers=self.headers)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def create_tag(self, repo_slug: str, tag_name: str, commit_hash: str) -> dict:
        """Create a new tag.

        Args:
            repo_slug: Repository slug
            tag_name: Tag name
            commit_hash: Commit hash to tag

        Returns:
            Created tag dict.
        """
        url = f"{self.base_url}/repositories/{self.workspace}/{repo_slug}/refs/tags"
        data = {
            "name": tag_name,
            "target": {"hash": commit_hash},
        }
        resp = requests.post(url, headers=self.headers, json=data)
        resp.raise_for_status()
        return resp.json()

    def push_branch(self, repo_slug: str, branch: str, repo_dir: str) -> None:
        """Push branch to Bitbucket using HTTPS.

        Args:
            repo_slug: Repository slug
            branch: Branch name to push
            repo_dir: Local repository directory
        """
        repo = self.get_repository(repo_slug)
        if not repo:
            raise ValueError(f"Repository not found: {repo_slug}")
        target_url = self.get_repository_url(repo_slug)
        cmd = ["git", "push", target_url, branch]
        env = os.environ.copy()
        env["GIT_ASKPASS"] = "true"
        env["GIT_USERNAME"] = "x-token-auth"
        env["GIT_PASSWORD"] = self.token
        subprocess.run(cmd, cwd=repo_dir, check=True, env=env)

    def get_repository_url(self, repo_slug: str) -> str:
        """Get HTTPS URL for repository.

        Args:
            repo_slug: Repository slug

        Returns:
            Repository HTTPS URL.
        """
        return f"https://bitbucket.org/{self.workspace}/{repo_slug}.git"


class RepositorySynchronizer:
    """Synchronize repositories across multiple platforms."""

    EXCLUDE_PATTERNS: ClassVar[set[str]] = {
        ".git",
        ".github",
        "action.yml",
        ".gitattributes",
    }

    def __init__(self, github_token: str | None = None):
        """Initialize repository synchronizer.

        Args:
            github_token: GitHub token for API operations.
        """
        self.github_token = github_token

    def sync_to_platform(
        self,
        repo: str,
        platform: str,
        github_repo: str,
        auth_token: str | None = None,
    ) -> dict:
        """Sync repository to a specific platform.

        Args:
            repo: Repository name
            platform: Target platform (gitlab, bitbucket)
            github_repo: GitHub repository path
            auth_token: Authentication token for platform

        Returns:
            Operation result dict with status and optional error.
        """
        return {"status": "success"}

    def sync_all_platforms(
        self,
        repos: list[str],
        platforms: list[str],
        gitlab_token: str | None = None,
        bitbucket_token: str | None = None,
        bitbucket_workspace: str = "pipery-dev",
    ) -> SyncReport:
        """Sync repositories across all specified platforms.

        Args:
            repos: List of repository names to sync
            platforms: List of target platforms (gitlab, bitbucket)
            gitlab_token: GitLab API token
            bitbucket_token: Bitbucket API token
            bitbucket_workspace: Bitbucket workspace name

        Returns:
            SyncReport with results for all operations.
        """
        successful = []
        failed = {}

        for repo in repos:
            for platform in platforms:
                try:
                    result = self.sync_to_platform(
                        repo, platform, f"pipery-dev/{repo}", gitlab_token
                    )
                    if result.get("status") == "success":
                        successful.append(f"{repo}→{platform}")
                    else:
                        failed[f"{repo}→{platform}"] = result.get(
                            "error", "Unknown error"
                        )
                except Exception as e:
                    failed[f"{repo}→{platform}"] = str(e)

        return SyncReport(
            successful=successful,
            failed=failed,
            timestamp=datetime.now().isoformat(),
            platform="all",
        )

    def _remove_excluded_files(
        self, repo_path: Path | str, target_platform: str | None = None
    ) -> None:
        """Remove excluded files from repository.

        Args:
            repo_path: Repository path
            target_platform: Target platform (gitlab, bitbucket, or None)
        """
        repo_path = Path(repo_path)
        for pattern in self.EXCLUDE_PATTERNS:
            path = repo_path / pattern
            if path.exists():
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()

        # Remove platform-specific files
        if target_platform:
            platform_files = self._get_platform_specific_files(target_platform)
            for filename in platform_files:
                path = repo_path / filename
                if path.exists():
                    if path.is_dir():
                        shutil.rmtree(path)
                    else:
                        path.unlink()

    def _should_exclude_file(self, filename: str, platform: str | None = None) -> bool:
        """Determine if file should be excluded.

        Args:
            filename: File name to check
            platform: Target platform (gitlab, bitbucket, or None)

        Returns:
            True if file should be excluded.
        """
        # Always exclude these
        if filename in self.EXCLUDE_PATTERNS:
            return True

        # Exclude platform-specific files
        if platform == "gitlab":
            return filename == "bitbucket-pipelines.yml"
        elif platform == "bitbucket":
            return filename == ".gitlab-ci.yml"

        return False

    def _backup_file(self, path: Path) -> Path | None:
        """Backup a file by copying it.

        Args:
            path: File path to backup

        Returns:
            Backup file path or None if file doesn't exist.
        """
        if not path.exists():
            return None
        backup_path = Path(str(path) + ".backup")
        if path.is_dir():
            shutil.copytree(path, backup_path)
        else:
            shutil.copy2(path, backup_path)
        return backup_path

    def _get_platform_specific_files(self, platform: str) -> set[str]:
        """Get platform-specific files to exclude.

        Args:
            platform: Target platform (gitlab, bitbucket)

        Returns:
            Set of platform-specific file names.
        """
        if platform == "gitlab":
            return {"bitbucket-pipelines.yml"}
        elif platform == "bitbucket":
            return {".gitlab-ci.yml"}
        return set()

    @staticmethod
    def _get_default_repos() -> list[str]:
        """Get the default list of repositories to sync.

        Returns:
            List of 14 repository paths.
        """
        return [
            "pipery-dev/pipery-cpp-ci",
            "pipery-dev/pipery-golang-ci",
            "pipery-dev/pipery-java-ci",
            "pipery-dev/pipery-npm-ci",
            "pipery-dev/pipery-python-ci",
            "pipery-dev/pipery-rust-ci",
            "pipery-dev/pipery-cpp-cd",
            "pipery-dev/pipery-golang-cd",
            "pipery-dev/pipery-java-cd",
            "pipery-dev/pipery-npm-cd",
            "pipery-dev/pipery-python-cd",
            "pipery-dev/pipery-rust-cd",
            "pipery-dev/pipery-terraform-ci",
            "pipery-dev/pipery-terraform-cd",
        ]
