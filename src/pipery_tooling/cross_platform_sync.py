"""Cross-platform repository synchronization using SSH and GitPython."""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

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

                # Clone from GitHub
                logger.info(f"Cloning GitHub repo: {github_repo}")
                github_url = f"https://github.com/{github_repo}"
                git_repo = Repo.clone_from(github_url, local_repo_path)

                # Determine target SSH URL based on platform
                if platform == "gitlab":
                    target_url = f"git@gitlab.com:pipery-dev/{repo}.git"
                elif platform == "bitbucket":
                    target_url = f"git@bitbucket.org:pipery-dev/{repo}.git"
                else:
                    return {"status": "failed", "error": f"Unknown platform: {platform}"}

                # Remove excluded files
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

                # Stage and commit changes
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
                try:
                    # Push branches using refs/heads/*
                    logger.debug(f"Pushing all branches to {platform}")
                    git_repo.git.push("target", "+refs/heads/*:refs/heads/*")

                    # Push tags using refs/tags/*
                    logger.debug(f"Pushing all tags to {platform}")
                    git_repo.git.push("target", "refs/tags/*:refs/tags/*")

                    logger.info(f"Successfully pushed all branches and tags to {platform}")
                except Exception as e:
                    logger.error(f"Failed to push to {platform}: {e}")
                    return {"status": "failed", "error": str(e)}

                return {"status": "success"}

        except Exception as e:
            logger.error(f"Sync failed: {e}")
            return {"status": "failed", "error": str(e)}

    def _remove_excluded_files(self, repo_path: str, platform: str):
        """Remove platform-specific files that shouldn't be synced."""
        excluded = EXCLUDE_PATTERNS.copy()

        # Exclude platform-specific templates from other platforms
        if platform != "bitbucket":
            excluded.add("bitbucket-pipelines.yml")
        if platform != "gitlab":
            excluded.add(".gitlab-ci.template.yml")

        for pattern in excluded:
            path = Path(repo_path) / pattern
            if path.exists():
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
                logger.debug(f"Removed: {pattern}")

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
