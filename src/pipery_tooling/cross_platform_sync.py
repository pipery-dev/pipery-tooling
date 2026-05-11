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
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
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

                # Remove excluded files from git index (affects all branches)
                excluded_for_platform = self._get_excluded_files(platform)
                print(f"[SYNC] Removing platform-specific files: {excluded_for_platform}")
                for file_pattern in excluded_for_platform:
                    try:
                        git_repo.index.remove([file_pattern], working_tree=True)
                        print(f"[SYNC] Removed from git: {file_pattern}")
                    except:
                        pass  # File may not exist

                # Also remove from working directory
                self._remove_excluded_files(local_repo_path, platform)

                # Create sync branch
                sync_branch = "sync/github-main"
                try:
                    git_repo.create_head(sync_branch)
                except:
                    logger.debug(f"Branch {sync_branch} may already exist")

                # Check out sync branch
                git_repo.heads[sync_branch].checkout()

                # Configure git user
                with git_repo.config_writer() as git_config:
                    git_config.set_value("user", "name", "pipery-sync")
                    git_config.set_value("user", "email", "sync@pipery.dev")

                # Stage and commit changes (removed files)
                git_repo.index.add("*")
                try:
                    git_repo.index.commit(f"Sync from GitHub - {datetime.now().isoformat()}")
                    logger.info(f"Created commit on {sync_branch}")
                except:
                    logger.info(f"No changes to commit on {sync_branch}")

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

                    # Push all tags with force
                    logger.info(f"Pushing all tags to {platform}")
                    print(f"[SYNC] Pushing tags to {platform}...")
                    tag_result = remote.push(tags=True, force=True)
                    logger.info(f"Tag push result: {len(tag_result)} refs pushed")
                    print(f"[SYNC] Pushed {len(tag_result)} tag refs")

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
