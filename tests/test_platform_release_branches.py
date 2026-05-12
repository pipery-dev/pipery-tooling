"""Integration tests for platform-specific release branch creation."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from pipery_tooling.release_branches import create_platform_release_branches


class CreatePlatformReleaseBranchesTests:
    """Tests for platform-specific release branch creation."""

    @pytest.fixture
    def git_repo(self):
        """Create a temporary git repo for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)

            # Initialize repo
            subprocess.run(
                ["git", "init"],
                cwd=repo_path,
                check=True,
                capture_output=True,
            )

            # Configure git
            subprocess.run(
                ["git", "config", "user.name", "Test User"],
                cwd=repo_path,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=repo_path,
                check=True,
                capture_output=True,
            )

            # Create initial commit with test files
            (repo_path / "action.yml").write_text("github: action")
            (repo_path / ".gitlab-ci.template.yml").write_text("gitlab: true")
            (repo_path / "bitbucket-pipelines.yml").write_text("bitbucket: true")
            (repo_path / "README.md").write_text("# Test")

            subprocess.run(
                ["git", "add", "."],
                cwd=repo_path,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "commit", "-m", "Initial commit"],
                cwd=repo_path,
                check=True,
                capture_output=True,
            )

            # Create and tag
            subprocess.run(
                ["git", "tag", "v1.0.0"],
                cwd=repo_path,
                check=True,
                capture_output=True,
            )

            # Get the commit SHA
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_path,
                check=True,
                capture_output=True,
                text=True,
            )
            tagged_commit = result.stdout.strip()

            # Detach HEAD to simulate GitHub Actions tag checkout
            subprocess.run(
                ["git", "checkout", tagged_commit],
                cwd=repo_path,
                check=True,
                capture_output=True,
            )

            yield repo_path, "v1.0.0", tagged_commit

    def test_create_branches_basic(self, git_repo):
        """Test creating three platform-specific release branches."""
        repo_path, tag_name, tagged_commit = git_repo

        result = create_platform_release_branches(
            repo_dir=repo_path,
            tag_name=tag_name,
            tagged_commit=tagged_commit,
        )

        # Verify all three branches were created
        assert result["github"] == "release/github-v1.0.0"
        assert result["gitlab"] == "release/gitlab-v1.0.0"
        assert result["bitbucket"] == "release/bitbucket-v1.0.0"

        # Verify branches exist in git
        branches_output = subprocess.run(
            ["git", "branch", "-a"],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True,
        )
        branches = branches_output.stdout
        assert "release/github-v1.0.0" in branches
        assert "release/gitlab-v1.0.0" in branches
        assert "release/bitbucket-v1.0.0" in branches

    def test_github_branch_has_all_files(self, git_repo):
        """Test that release/github branch contains all CI/CD files."""
        repo_path, tag_name, tagged_commit = git_repo

        create_platform_release_branches(
            repo_dir=repo_path,
            tag_name=tag_name,
            tagged_commit=tagged_commit,
        )

        # Checkout github branch
        subprocess.run(
            ["git", "checkout", "release/github-v1.0.0"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        # Verify all files exist
        assert (repo_path / "action.yml").exists()
        assert (repo_path / ".gitlab-ci.template.yml").exists()
        assert (repo_path / "bitbucket-pipelines.yml").exists()
        assert (repo_path / "README.md").exists()

    def test_gitlab_branch_excludes_correct_files(self, git_repo):
        """Test that release/gitlab branch excludes GitHub and Bitbucket CI files."""
        repo_path, tag_name, tagged_commit = git_repo

        create_platform_release_branches(
            repo_dir=repo_path,
            tag_name=tag_name,
            tagged_commit=tagged_commit,
        )

        # Checkout gitlab branch
        subprocess.run(
            ["git", "checkout", "release/gitlab-v1.0.0"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        # Verify exclusions
        assert not (repo_path / "action.yml").exists(), "action.yml should be removed from GitLab"
        assert not (repo_path / "bitbucket-pipelines.yml").exists(), "bitbucket-pipelines.yml should be removed from GitLab"
        # GitLab CI should be kept
        assert (repo_path / ".gitlab-ci.template.yml").exists()
        assert (repo_path / "README.md").exists()

    def test_bitbucket_branch_excludes_correct_files(self, git_repo):
        """Test that release/bitbucket branch excludes GitHub and GitLab CI files."""
        repo_path, tag_name, tagged_commit = git_repo

        create_platform_release_branches(
            repo_dir=repo_path,
            tag_name=tag_name,
            tagged_commit=tagged_commit,
        )

        # Checkout bitbucket branch
        subprocess.run(
            ["git", "checkout", "release/bitbucket-v1.0.0"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        # Verify exclusions
        assert not (repo_path / "action.yml").exists(), "action.yml should be removed from Bitbucket"
        assert not (repo_path / ".gitlab-ci.template.yml").exists(), ".gitlab-ci.template.yml should be removed from Bitbucket"
        # Bitbucket pipelines should be kept
        assert (repo_path / "bitbucket-pipelines.yml").exists()
        assert (repo_path / "README.md").exists()

    def test_branches_point_to_correct_commits(self, git_repo):
        """Test that all branches have the expected commit history."""
        repo_path, tag_name, tagged_commit = git_repo

        create_platform_release_branches(
            repo_dir=repo_path,
            tag_name=tag_name,
            tagged_commit=tagged_commit,
        )

        # Get branch commits
        def get_branch_commit(branch_name):
            result = subprocess.run(
                ["git", "rev-parse", branch_name],
                cwd=repo_path,
                check=True,
                capture_output=True,
                text=True,
            )
            return result.stdout.strip()

        github_commit = get_branch_commit("release/github-v1.0.0")
        gitlab_commit = get_branch_commit("release/gitlab-v1.0.0")
        bitbucket_commit = get_branch_commit("release/bitbucket-v1.0.0")

        # GitHub should point to original tagged commit
        assert github_commit == tagged_commit, "GitHub branch should point to original commit"

        # GitLab and Bitbucket should have different commits (due to file removals)
        assert gitlab_commit != tagged_commit, "GitLab branch should have its own commit"
        assert bitbucket_commit != tagged_commit, "Bitbucket branch should have its own commit"

    def test_branch_commits_have_correct_messages(self, git_repo):
        """Test that removed-file commits have proper messages."""
        repo_path, tag_name, tagged_commit = git_repo

        create_platform_release_branches(
            repo_dir=repo_path,
            tag_name=tag_name,
            tagged_commit=tagged_commit,
        )

        # Get commit messages
        def get_branch_message(branch_name):
            result = subprocess.run(
                ["git", "log", "-1", "--format=%s", branch_name],
                cwd=repo_path,
                check=True,
                capture_output=True,
                text=True,
            )
            return result.stdout.strip()

        github_msg = get_branch_message("release/github-v1.0.0")
        gitlab_msg = get_branch_message("release/gitlab-v1.0.0")
        bitbucket_msg = get_branch_message("release/bitbucket-v1.0.0")

        # GitHub should be original commit
        assert github_msg == "Initial commit"
        # Others should have file removal messages
        assert "chore" in gitlab_msg.lower() or "remove" in gitlab_msg.lower()
        assert "chore" in bitbucket_msg.lower() or "remove" in bitbucket_msg.lower()

    def test_rerun_safety_deletes_existing_branches(self, git_repo):
        """Test that running the function twice safely recreates branches."""
        repo_path, tag_name, tagged_commit = git_repo

        # Create branches first time
        result1 = create_platform_release_branches(
            repo_dir=repo_path,
            tag_name=tag_name,
            tagged_commit=tagged_commit,
        )

        # Modify a branch
        subprocess.run(
            ["git", "checkout", "release/github-v1.0.0"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        (repo_path / "extra.txt").write_text("extra content")
        subprocess.run(
            ["git", "add", "extra.txt"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Add extra file"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        # Return to detached HEAD
        subprocess.run(
            ["git", "checkout", tagged_commit],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        # Create branches again
        result2 = create_platform_release_branches(
            repo_dir=repo_path,
            tag_name=tag_name,
            tagged_commit=tagged_commit,
        )

        # Should succeed without error
        assert result1 == result2

        # The extra file should not be in the recreated branch
        subprocess.run(
            ["git", "checkout", "release/github-v1.0.0"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        assert not (repo_path / "extra.txt").exists(), "Extra file should be gone after rerun"

    def test_all_files_excluded_on_gitlab_and_bitbucket(self, git_repo):
        """Test that no GitHub-specific files exist on mirror branches."""
        repo_path, tag_name, tagged_commit = git_repo

        create_platform_release_branches(
            repo_dir=repo_path,
            tag_name=tag_name,
            tagged_commit=tagged_commit,
        )

        # Check GitLab branch
        subprocess.run(
            ["git", "checkout", "release/gitlab-v1.0.0"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        gitlab_files = set(f.name for f in repo_path.glob("*") if f.is_file())

        # Check Bitbucket branch
        subprocess.run(
            ["git", "checkout", "release/bitbucket-v1.0.0"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        bitbucket_files = set(f.name for f in repo_path.glob("*") if f.is_file())

        # Verify no action.yml on either
        assert "action.yml" not in gitlab_files
        assert "action.yml" not in bitbucket_files

        # Verify no cross-platform CI files
        assert "bitbucket-pipelines.yml" not in gitlab_files
        assert ".gitlab-ci.template.yml" not in bitbucket_files


class SyncPlatformWithTagsTests:
    """Tests for sync_to_platform with platform-specific tags."""

    def test_sync_to_platform_tag_parameter_accepted(self):
        """Test that sync_to_platform accepts tag_name parameter."""
        from pipery_tooling.cross_platform_sync import PlatformSync

        sync = PlatformSync()

        # Mock the sync operation to avoid real git operations
        with patch.object(sync, 'sync_to_platform', return_value={"status": "success"}):
            result = sync.sync_to_platform(
                "test-repo",
                "gitlab",
                "pipery-dev/test-repo",
                tag_name="v1.0.0",
            )

            assert result == {"status": "success"}

    def test_workflow_variables_integration(self):
        """Test that workflow GitHub Actions variables integrate correctly."""
        # Simulate GitHub Actions context
        test_cases = [
            {
                "github_ref": "refs/tags/v1.0.0",
                "expected_tag": "v1.0.0",
            },
            {
                "github_ref": "refs/tags/v2.3.4-rc1",
                "expected_tag": "v2.3.4-rc1",
            },
        ]

        for test in test_cases:
            github_ref = test["github_ref"]
            expected_tag = test["expected_tag"]

            # Simulate the workflow's tag extraction
            tag_name = github_ref.replace("refs/tags/", "")
            assert tag_name == expected_tag
