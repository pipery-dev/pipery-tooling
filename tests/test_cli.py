from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from pipery_tooling.commands import (
    _copy_runtime_files,
    bump_version,
    clean_artifacts,
    create_release_branch,
    run_all_test_cases,
    update_changelog_for_release,
    validate_repo,
    validate_test_log,
)
from pipery_tooling.config import ActionConfig, load_config
from pipery_tooling.test_discovery import TestSpec, discover_test_specs, load_test_spec


ROOT = Path(__file__).resolve().parents[1]


class PiperyToolingTests(unittest.TestCase):

    # ------------------------------------------------------------------
    # scaffold
    # ------------------------------------------------------------------

    def test_scaffold_creates_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir) / "my-action"
            self.run_cli(
                "scaffold",
                "--repo", str(repo),
                "--owner", "pipery-dev",
                "--name", "my-action",
                "--title", "My Action",
                "--description", "Test action",
            )
            config = load_config(repo)
            self.assertEqual(config.repo_name, "my-action")
            self.assertTrue((repo / "action.yml").exists())
            self.assertTrue((repo / ".github" / "workflows" / "release.yml").exists())
            self.assertTrue((repo / "test-project" / "README.md").exists())
            self.assertEqual(validate_repo(repo, config), [])

    def test_scaffold_creates_test_spec(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = self._scaffold(Path(tmpdir))
            spec_path = repo / ".github" / "pipery" / "basic_test.yaml"
            self.assertTrue(spec_path.exists())
            content = spec_path.read_text()
            self.assertIn("name: basic-test", content)
            self.assertIn("source_path:", content)
            self.assertIn("success_values:", content)

    def test_scaffold_release_workflow_delegates_to_reusable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = self._scaffold(Path(tmpdir))
            workflow = (repo / ".github" / "workflows" / "release.yml").read_text()
            self.assertIn("pipery-release.yml", workflow)
            self.assertIn("inputs.bump", workflow)

    # ------------------------------------------------------------------
    # test discovery
    # ------------------------------------------------------------------

    def test_test_command_uses_spec_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = self._scaffold(Path(tmpdir))
            result = self.run_cli("test", "--repo", str(repo))
            self.assertIn("basic-test", result.stdout)
            self.assertIn("PASS", result.stdout)
            self.assertIn("Validation passed", result.stdout)

    def test_discover_test_specs_finds_yaml_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = self._scaffold(Path(tmpdir))
            specs = discover_test_specs(repo)
            self.assertEqual(len(specs), 1)
            self.assertEqual(specs[0].name, "basic-test")
            self.assertEqual(specs[0].source_path, "test-project")

    def test_discover_test_specs_returns_empty_without_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir) / "bare"
            repo.mkdir()
            self.assertEqual(discover_test_specs(repo), [])

    def test_load_test_spec_parses_all_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            spec_file = Path(tmpdir) / "my_test.yaml"
            spec_file.write_text(
                "name: my-test\n"
                "description: Tests something.\n"
                "source_path: fixtures/proj\n"
                "inputs:\n"
                "  project_path: fixtures/proj\n"
                "  strict: 'true'\n"
                "expect:\n"
                "  log_path: out.jsonl\n"
                "  success_values: [done]\n"
                "  required_fields:\n"
                "    - name: phase\n"
                "      value: build\n",
                encoding="utf-8",
            )
            spec = load_test_spec(spec_file)
            self.assertEqual(spec.name, "my-test")
            self.assertEqual(spec.source_path, "fixtures/proj")
            self.assertEqual(spec.inputs["strict"], "true")
            self.assertEqual(spec.log_path, "out.jsonl")
            self.assertEqual(spec.success_values, ["done"])
            self.assertEqual(spec.required_fields, [{"name": "phase", "value": "build"}])
            self.assertFalse(spec.expect_failure)

    def test_load_test_spec_parses_expect_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            spec_file = Path(tmpdir) / "fail_test.yaml"
            spec_file.write_text(
                "name: should-fail\n"
                "source_path: .\n"
                "expect:\n"
                "  failure: true\n",
                encoding="utf-8",
            )
            spec = load_test_spec(spec_file)
            self.assertTrue(spec.expect_failure)

    def test_expect_failure_passes_when_action_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = self._scaffold(Path(tmpdir))
            # Replace main.sh with one that always exits 1
            main_sh = repo / "src" / "main.sh"
            main_sh.write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")
            main_sh.chmod(0o755)
            # Overwrite the only spec so it expects failure
            spec_dir = repo / ".github" / "pipery"
            (spec_dir / "basic_test.yaml").write_text(
                "name: expect-fail\n"
                "source_path: test-project\n"
                "inputs:\n"
                "  project_path: test-project\n"
                "expect:\n"
                "  failure: true\n",
                encoding="utf-8",
            )
            result = self.run_cli("test", "--repo", str(repo))
            self.assertIn("PASS: expect-fail", result.stdout)

    def test_expect_failure_fails_when_action_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = self._scaffold(Path(tmpdir))
            spec_dir = repo / ".github" / "pipery"
            # Write a spec pointing at a valid source — action will succeed, but we expect failure
            (spec_dir / "wrong_expect_test.yaml").write_text(
                "name: wrong-expect\n"
                "source_path: test-project\n"
                "inputs:\n"
                "  project_path: test-project\n"
                "expect:\n"
                "  failure: true\n",
                encoding="utf-8",
            )
            result = self.run_cli_no_check("test", "--repo", str(repo))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("FAIL: wrong-expect", result.stdout)

    def test_spec_failure_reported_correctly(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = self._scaffold(Path(tmpdir))
            spec_dir = repo / ".github" / "pipery"
            # Add a spec that points to a non-existent fixture
            (spec_dir / "bad_test.yaml").write_text(
                "name: bad-test\nsource_path: nonexistent-fixture\n"
                "inputs:\n  project_path: nonexistent-fixture\n",
                encoding="utf-8",
            )
            result = self.run_cli_no_check("test", "--repo", str(repo))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("FAIL: bad-test", result.stdout)

    # ------------------------------------------------------------------
    # legacy test cases (config-based)
    # ------------------------------------------------------------------

    def test_multi_case_test_runner_all_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = self._scaffold(Path(tmpdir))
            config = load_config(repo)
            second_fixture = repo / "test-project-2"
            second_fixture.mkdir()
            multi_config = replace(
                config,
                test_cases=[
                    {"name": "case-a", "test_project_path": "test-project"},
                    {"name": "case-b", "test_project_path": "test-project-2"},
                ],
            )
            rc = run_all_test_cases(repo, multi_config)
            self.assertEqual(rc, 0)

    def test_multi_case_test_runner_partial_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = self._scaffold(Path(tmpdir))
            config = load_config(repo)
            multi_config = replace(
                config,
                test_cases=[
                    {"name": "good", "test_project_path": "test-project"},
                    {"name": "bad", "test_project_path": "nonexistent-fixture"},
                ],
            )
            rc = run_all_test_cases(repo, multi_config)
            self.assertNotEqual(rc, 0)

    # ------------------------------------------------------------------
    # validate_test_log
    # ------------------------------------------------------------------

    def test_validate_test_log_rejects_missing_success_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = self._scaffold(Path(tmpdir))
            (repo / "pipery.jsonl").write_text('{"event":"build","status":"failed"}\n', encoding="utf-8")
            errors = validate_test_log(repo, load_config(repo))
            self.assertEqual(len(errors), 1)
            self.assertIn("success entry", errors[0])

    # ------------------------------------------------------------------
    # version / changelog
    # ------------------------------------------------------------------

    def test_version_bump_updates_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = self._scaffold(Path(tmpdir))
            self.run_cli("version", "--repo", str(repo), "--bump", "minor")
            config = load_config(repo)
            self.assertEqual(config.version, "0.2.0")
            self.assertIn("0.2.0", (repo / "README.md").read_text())

    def test_bump_version_semver(self) -> None:
        self.assertEqual(bump_version("1.2.3", "patch"), "1.2.4")
        self.assertEqual(bump_version("1.2.3", "minor"), "1.3.0")
        self.assertEqual(bump_version("1.2.3", "major"), "2.0.0")

    def test_changelog_release_heading_inserted(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "CHANGELOG.md"
            path.write_text("# Changelog\n\n## [Unreleased]\n\n- Change\n", encoding="utf-8")
            update_changelog_for_release(path, "1.4.0")
            text = path.read_text()
            self.assertIn("## [1.4.0]", text)
            self.assertIn("- _Nothing yet._", text)

    def test_minor_version_property(self) -> None:
        config = ActionConfig(
            owner="x", action_name="y", title="Y", description="d",
            marketplace_category="ci", author="x", version="1.2.3",
        )
        self.assertEqual(config.minor_version, "1.2")
        self.assertEqual(config.major_version, "1")

    # ------------------------------------------------------------------
    # cleanup
    # ------------------------------------------------------------------

    def test_cleanup_removes_test_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = self._scaffold(Path(tmpdir))
            (repo / "pipery.jsonl").write_text('{"event":"build","status":"success"}\n', encoding="utf-8")
            result = self.run_cli("cleanup", "--repo", str(repo))
            self.assertIn("Removed: pipery.jsonl", result.stdout)
            self.assertFalse((repo / "pipery.jsonl").exists())

    def test_cleanup_reports_nothing_when_clean(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = self._scaffold(Path(tmpdir))
            result = self.run_cli("cleanup", "--repo", str(repo))
            self.assertIn("Nothing to clean up", result.stdout)

    def test_clean_artifacts_uses_glob_patterns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = self._scaffold(Path(tmpdir))
            (repo / "pipery.jsonl").write_text("{}", encoding="utf-8")
            (repo / "other.jsonl").write_text("{}", encoding="utf-8")
            config = replace(load_config(repo), cleanup_paths=["*.jsonl"])
            removed = clean_artifacts(repo, config)
            self.assertIn(Path("pipery.jsonl"), removed)
            self.assertIn(Path("other.jsonl"), removed)

    # ------------------------------------------------------------------
    # release
    # ------------------------------------------------------------------

    def test_release_dry_run_generates_release_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = self._scaffold(Path(tmpdir))
            self.run_cli("release", "--repo", str(repo), "--bump", "patch", "--dry-run")
            notes = (repo / "docs" / "release-notes.md").read_text()
            self.assertIn("Release v0.1.1", notes)

    def test_release_notes_contain_all_tag_forms(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = self._scaffold(Path(tmpdir))
            self.run_cli("release", "--repo", str(repo), "--bump", "minor", "--dry-run")
            notes = (repo / "docs" / "release-notes.md").read_text()
            self.assertIn("v0.2.0", notes)
            self.assertIn("v0.2", notes)
            self.assertIn("v0", notes)

    def test_release_cleans_artifacts_before_tagging(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = self._scaffold(Path(tmpdir))
            (repo / "pipery.jsonl").write_text('{"event":"build","status":"success"}\n', encoding="utf-8")
            self.run_cli("release", "--repo", str(repo), "--dry-run")
            self.assertFalse((repo / "pipery.jsonl").exists())

    # ------------------------------------------------------------------
    # release branch
    # ------------------------------------------------------------------

    def test_copy_runtime_files_composite(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = self._scaffold(Path(tmpdir))
            # Add extra step scripts to simulate a multi-step composite action
            (repo / "src" / "step-lint.sh").write_text("#!/usr/bin/env bash\necho lint\n")
            (repo / "src" / "step-build.sh").write_text("#!/usr/bin/env bash\necho build\n")
            dest = Path(tmpdir) / "release"
            dest.mkdir()
            config = load_config(repo)
            _copy_runtime_files(repo, dest, config)
            self.assertTrue((dest / "action.yml").exists())
            self.assertTrue((dest / "src" / "main.sh").exists())
            # All scripts in src/ must be copied, not just main.sh
            self.assertTrue((dest / "src" / "step-lint.sh").exists())
            self.assertTrue((dest / "src" / "step-build.sh").exists())
            self.assertTrue((dest / "README.md").exists())
            # dev-only files must NOT be copied
            self.assertFalse((dest / "pipery-action.toml").exists())
            self.assertFalse((dest / "CHANGELOG.md").exists())
            self.assertFalse((dest / ".github").exists())

    def test_copy_runtime_files_javascript(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = self._scaffold(Path(tmpdir), action_type="javascript")
            dest = Path(tmpdir) / "release"
            dest.mkdir()
            config = load_config(repo)
            _copy_runtime_files(repo, dest, config)
            self.assertTrue((dest / "action.yml").exists())
            self.assertTrue((dest / "dist" / "index.js").exists())
            self.assertFalse((dest / "src").exists())

    def test_release_branch_preview_no_push(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = self._scaffold(Path(tmpdir))
            config = load_config(repo)
            create_release_branch(repo, config, push=False)
            preview = repo / ".release-preview"
            self.assertTrue(preview.exists())
            self.assertTrue((preview / "action.yml").exists())
            self.assertTrue((preview / "src" / "main.sh").exists())
            self.assertFalse((preview / "pipery-action.toml").exists())

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _scaffold(self, tmpdir: Path, action_type: str = "composite") -> Path:
        repo = tmpdir / "example-action"
        self.run_cli(
            "scaffold",
            "--repo", str(repo),
            "--owner", "pipery-dev",
            "--name", "example-action",
            "--title", "Example Action",
            "--description", "Example description",
            "--action-type", action_type,
        )
        return repo

    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "pipery_tooling.cli", *args],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            env={"PYTHONPATH": str(ROOT / "src")},
        )

    def run_cli_no_check(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "pipery_tooling.cli", *args],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            env={"PYTHONPATH": str(ROOT / "src")},
        )


if __name__ == "__main__":
    unittest.main()
