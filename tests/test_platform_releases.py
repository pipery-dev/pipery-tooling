"""
Tests for platform-specific release functionality.

Tests script inlining, branch generation, and version tagging for GitLab and Bitbucket.
"""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


class PlatformReleasesTests(unittest.TestCase):
    """Test platform-specific release functionality."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        """Clean up test fixtures."""
        self.temp_dir.cleanup()

    def _create_test_repo_with_scripts(self) -> Path:
        """Create a test repository with sample scripts."""
        # Create src directory with sample scripts
        src_dir = self.repo_dir / "src"
        src_dir.mkdir()

        # Create a sample script
        script_content = """#!/usr/bin/env bash
set -euo pipefail

echo "Running lint check..."
ruff check .
echo "Lint passed!"
"""
        (src_dir / "step-lint.sh").write_text(script_content)

        # Create another script
        (src_dir / "step-test.sh").write_text("""#!/usr/bin/env bash
set -euo pipefail

echo "Running tests..."
pytest
""")

        return self.repo_dir

    def _create_git_repo(self) -> Path:
        """Create a git repository for testing."""
        # Initialize git
        subprocess.run(
            ["git", "init"],
            cwd=self.repo_dir,
            check=True,
            capture_output=True,
        )

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
        (self.repo_dir / "README.md").write_text("# Test Repo")
        subprocess.run(
            ["git", "add", "."],
            cwd=self.repo_dir,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=self.repo_dir,
            check=True,
            capture_output=True,
        )

        return self.repo_dir

    def test_extract_major_version(self) -> None:
        """Test major version extraction."""
        from pipery_tooling.version_tagger import _extract_major_version

        self.assertEqual(_extract_major_version("1.0.0"), "1")
        self.assertEqual(_extract_major_version("2.3.4"), "2")
        self.assertEqual(_extract_major_version("10.20.30"), "10")
        self.assertEqual(_extract_major_version("1.0.0-beta.1"), "1")

        with self.assertRaises(ValueError):
            _extract_major_version("invalid")

    def test_inline_scripts_gitlab(self) -> None:
        """Test inlining scripts into .gitlab-ci.yml."""
        from pipery_tooling.script_inliner import inline_scripts

        # Create test repo with scripts
        self._create_test_repo_with_scripts()

        # Create a .gitlab-ci.yml file with script references
        gitlab_yml = self.repo_dir / ".gitlab-ci.yml"
        gitlab_yml.write_text("""stages:
  - lint
  - test

lint_job:
  stage: lint
  script:
    - bash ./src/step-lint.sh

test_job:
  stage: test
  script:
    - bash ./src/step-test.sh
""")

        # Run inlining
        inline_scripts("gitlab", gitlab_yml)

        # Verify content
        content = gitlab_yml.read_text()
        self.assertIn("Running lint check...", content)
        self.assertIn("Running tests...", content)
        self.assertIn("ruff check .", content)

    def test_inline_scripts_bitbucket(self) -> None:
        """Test inlining scripts into bitbucket-pipelines.yml."""
        from pipery_tooling.script_inliner import inline_scripts

        # Create test repo with scripts
        self._create_test_repo_with_scripts()

        # Create a bitbucket-pipelines.yml file
        bitbucket_yml = self.repo_dir / "bitbucket-pipelines.yml"
        bitbucket_yml.write_text("""image: python:3.11-slim

pipelines:
  default:
    - step:
        name: Lint
        script:
          - bash ./src/step-lint.sh
    - step:
        name: Test
        script:
          - bash ./src/step-test.sh
""")

        # Run inlining
        inline_scripts("bitbucket", bitbucket_yml)

        # Verify content
        content = bitbucket_yml.read_text()
        self.assertIn("Running lint check...", content)
        self.assertIn("ruff check .", content)

    def test_inline_scripts_missing_script(self) -> None:
        """Test error handling for missing scripts."""
        from pipery_tooling.script_inliner import inline_scripts

        # Create test repo
        self._create_test_repo_with_scripts()

        # Create a pipeline file that references a non-existent script
        gitlab_yml = self.repo_dir / ".gitlab-ci.yml"
        gitlab_yml.write_text("""stages:
  - lint

lint_job:
  stage: lint
  script:
    - bash ./src/step-nonexistent.sh
""")

        # Should raise FileNotFoundError
        with self.assertRaises(FileNotFoundError):
            inline_scripts("gitlab", gitlab_yml)

    def test_validate_pipeline_file(self) -> None:
        """Test validation of pipeline files."""
        from pipery_tooling.script_inliner import validate_pipeline_file

        # Create test repo
        self._create_test_repo_with_scripts()

        # Create a valid pipeline file
        gitlab_yml = self.repo_dir / ".gitlab-ci.yml"
        gitlab_yml.write_text("""stages:
  - lint

lint_job:
  stage: lint
  script:
    - bash ./src/step-lint.sh
""")

        # Should validate successfully
        self.assertTrue(validate_pipeline_file(gitlab_yml))

        # Create an invalid pipeline file
        invalid_yml = self.repo_dir / "invalid.yml"
        invalid_yml.write_text("""stages:
  - lint

lint_job:
  stage: lint
  script:
    - bash ./src/step-missing.sh
""")

        # Should not validate
        self.assertFalse(validate_pipeline_file(invalid_yml))

    def test_create_platform_tags(self) -> None:
        """Test platform-specific tag creation."""
        from pipery_tooling.version_tagger import create_platform_tags

        # Create git repo
        self._create_git_repo()

        version = "1.0.0"
        platforms = ["github", "gitlab", "bitbucket"]

        tags_map = create_platform_tags(
            self.repo_dir,
            version,
            platforms=platforms,
            dry_run=False,
        )

        # Verify tags were created
        self.assertIn("github", tags_map)
        self.assertIn("gitlab", tags_map)
        self.assertIn("bitbucket", tags_map)

        # Verify tag names
        for platform in platforms:
            tags = tags_map[platform]
            self.assertIn(f"v{version}-{platform}", tags)
            self.assertIn(f"v1-{platform}", tags)
            self.assertIn(f"latest-{platform}", tags)

    def test_list_platform_tags(self) -> None:
        """Test listing platform-specific tags."""
        from pipery_tooling.version_tagger import (
            create_platform_tags,
            list_platform_tags,
        )

        # Create git repo
        self._create_git_repo()

        version = "1.0.0"
        platforms = ["gitlab", "bitbucket"]

        # Create tags
        create_platform_tags(
            self.repo_dir,
            version,
            platforms=platforms,
            dry_run=False,
        )

        # List tags
        gitlab_tags = list_platform_tags(self.repo_dir, "gitlab")
        self.assertEqual(len(gitlab_tags), 3)
        self.assertIn(f"v{version}-gitlab", gitlab_tags)

        bitbucket_tags = list_platform_tags(self.repo_dir, "bitbucket")
        self.assertEqual(len(bitbucket_tags), 3)
        self.assertIn(f"v{version}-bitbucket", bitbucket_tags)

    def test_generate_release_branches_dry_run(self) -> None:
        """Test generating platform-specific release branches in dry-run mode."""
        from pipery_tooling.release_branches import generate_release_branches

        version = "1.0.0"
        platforms = ["github", "gitlab"]

        branches = generate_release_branches(
            self.repo_dir,
            version,
            platforms=platforms,
            dry_run=True,  # Don't actually create
        )

        self.assertIn("github", branches)
        self.assertIn("gitlab", branches)
        self.assertEqual(branches["github"], f"release/github-v{version}")
        self.assertEqual(branches["gitlab"], f"release/gitlab-v{version}")
