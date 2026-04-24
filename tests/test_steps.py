from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

# ---------------------------------------------------------------------------
# Helpers to locate the package under src/
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pipery_tooling.steps.cli", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        env={"PYTHONPATH": str(ROOT / "src")},
    )


def _run_cli_no_check(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pipery_tooling.steps.cli", *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={"PYTHONPATH": str(ROOT / "src")},
    )


# ---------------------------------------------------------------------------
# Runner tests
# ---------------------------------------------------------------------------

class RunnerTests(unittest.TestCase):

    def test_tool_available_true_for_python(self) -> None:
        from pipery_tooling.steps.runner import tool_available
        self.assertTrue(tool_available("python3") or tool_available("python"))

    def test_tool_available_false_for_nonexistent(self) -> None:
        from pipery_tooling.steps.runner import tool_available
        self.assertFalse(tool_available("__no_such_tool_xyz__"))

    def test_run_via_psh_uses_psh_when_available(self) -> None:
        from pipery_tooling.steps import runner
        with tempfile.TemporaryDirectory() as tmp:
            log = str(Path(tmp) / "out.jsonl")
            with (
                patch.object(runner, "tool_available", return_value=True),
                patch("pipery_tooling.steps.runner.subprocess.run") as mock_run,
            ):
                mock_run.return_value = MagicMock(returncode=0)
                rc = runner.run_via_psh("echo hello", log, tmp)
                self.assertEqual(rc, 0)
                args_used = mock_run.call_args[0][0]
                self.assertEqual(args_used[0], "psh")
                self.assertIn("-log-file", args_used)
                self.assertIn("-fail-on-error", args_used)
                self.assertIn("-c", args_used)

    def test_run_via_psh_falls_back_when_psh_absent(self) -> None:
        from pipery_tooling.steps import runner
        with tempfile.TemporaryDirectory() as tmp:
            log = str(Path(tmp) / "out.jsonl")
            with (
                patch.object(runner, "tool_available", return_value=False),
                patch("pipery_tooling.steps.runner.subprocess.run") as mock_run,
            ):
                mock_run.return_value = MagicMock(returncode=0)
                rc = runner.run_via_psh("echo hello", log, tmp)
                self.assertEqual(rc, 0)
                call_kwargs = mock_run.call_args[1]
                self.assertTrue(call_kwargs.get("shell"))

    def test_run_via_psh_returns_nonzero_on_failure(self) -> None:
        from pipery_tooling.steps import runner
        with tempfile.TemporaryDirectory() as tmp:
            log = str(Path(tmp) / "out.jsonl")
            with (
                patch.object(runner, "tool_available", return_value=False),
                patch("pipery_tooling.steps.runner.subprocess.run") as mock_run,
            ):
                mock_run.return_value = MagicMock(returncode=42)
                rc = runner.run_via_psh("false", log, tmp)
                self.assertEqual(rc, 42)


# ---------------------------------------------------------------------------
# CLI argument-parsing tests
# ---------------------------------------------------------------------------

class CliParserTests(unittest.TestCase):

    def test_sast_requires_language(self) -> None:
        result = _run_cli_no_check("sast")
        self.assertNotEqual(result.returncode, 0)

    def test_sca_requires_language(self) -> None:
        result = _run_cli_no_check("sca")
        self.assertNotEqual(result.returncode, 0)

    def test_version_requires_language_and_bump(self) -> None:
        result = _run_cli_no_check("version")
        self.assertNotEqual(result.returncode, 0)

    def test_reintegrate_requires_branches(self) -> None:
        result = _run_cli_no_check("reintegrate")
        self.assertNotEqual(result.returncode, 0)

    def test_deploy_requires_target(self) -> None:
        result = _run_cli_no_check("deploy")
        self.assertNotEqual(result.returncode, 0)

    def test_help_exits_zero(self) -> None:
        result = _run_cli_no_check("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("pipery-steps", result.stdout)

    def test_sast_subcommand_help(self) -> None:
        result = _run_cli_no_check("sast", "--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--language", result.stdout)

    def test_version_bump_choices_validated(self) -> None:
        result = _run_cli_no_check("version", "--language", "python", "--bump", "invalid")
        self.assertNotEqual(result.returncode, 0)

    def test_deploy_strategy_choices_validated(self) -> None:
        result = _run_cli_no_check("deploy", "--target", "helm", "--strategy", "badstrat")
        self.assertNotEqual(result.returncode, 0)

    def test_deploy_target_choices_validated(self) -> None:
        result = _run_cli_no_check("deploy", "--target", "not-a-target", "--strategy", "rolling")
        self.assertNotEqual(result.returncode, 0)


# ---------------------------------------------------------------------------
# Version bumping tests
# ---------------------------------------------------------------------------

class VersionBumpTests(unittest.TestCase):

    # --- shared semver helper ---
    def test_semver_patch(self) -> None:
        from pipery_tooling.steps.version import bump_semver
        self.assertEqual(bump_semver("1.2.3", "patch"), "1.2.4")

    def test_semver_minor(self) -> None:
        from pipery_tooling.steps.version import bump_semver
        self.assertEqual(bump_semver("1.2.3", "minor"), "1.3.0")

    def test_semver_major(self) -> None:
        from pipery_tooling.steps.version import bump_semver
        self.assertEqual(bump_semver("1.2.3", "major"), "2.0.0")

    def test_semver_invalid_raises(self) -> None:
        from pipery_tooling.steps.version import bump_semver
        with self.assertRaises(ValueError):
            bump_semver("not-a-version", "patch")

    # --- Python pyproject.toml ---
    def test_python_pyproject_bump(self) -> None:
        from pipery_tooling.steps.version import run
        with tempfile.TemporaryDirectory() as tmp:
            pyproject = Path(tmp) / "pyproject.toml"
            pyproject.write_text(
                '[project]\nname = "myapp"\nversion = "1.0.0"\n', encoding="utf-8"
            )
            log = str(Path(tmp) / "steps.jsonl")
            rc = run("python", tmp, "minor", log)
            self.assertEqual(rc, 0)
            self.assertIn('version = "1.1.0"', pyproject.read_text())
            entry = json.loads(Path(log).read_text().strip())
            self.assertEqual(entry["old_version"], "1.0.0")
            self.assertEqual(entry["new_version"], "1.1.0")

    def test_python_setup_cfg_bump(self) -> None:
        from pipery_tooling.steps.version import run
        with tempfile.TemporaryDirectory() as tmp:
            setup_cfg = Path(tmp) / "setup.cfg"
            setup_cfg.write_text("[metadata]\nname = myapp\nversion = 2.3.4\n", encoding="utf-8")
            log = str(Path(tmp) / "steps.jsonl")
            rc = run("python", tmp, "patch", log)
            self.assertEqual(rc, 0)
            self.assertIn("version = 2.3.5", setup_cfg.read_text())

    def test_python_setup_py_bump(self) -> None:
        from pipery_tooling.steps.version import run
        with tempfile.TemporaryDirectory() as tmp:
            setup_py = Path(tmp) / "setup.py"
            setup_py.write_text(
                'from setuptools import setup\nsetup(name="myapp", version="0.9.0")\n',
                encoding="utf-8",
            )
            log = str(Path(tmp) / "steps.jsonl")
            rc = run("python", tmp, "major", log)
            self.assertEqual(rc, 0)
            self.assertIn('version="1.0.0"', setup_py.read_text())

    # --- Go ---
    def test_golang_version_file_bump(self) -> None:
        from pipery_tooling.steps.version import run
        with tempfile.TemporaryDirectory() as tmp:
            vf = Path(tmp) / "VERSION"
            vf.write_text("0.4.2\n", encoding="utf-8")
            log = str(Path(tmp) / "steps.jsonl")
            rc = run("golang", tmp, "minor", log)
            self.assertEqual(rc, 0)
            self.assertEqual(vf.read_text().strip(), "0.5.0")

    def test_golang_version_go_bump(self) -> None:
        from pipery_tooling.steps.version import run
        with tempfile.TemporaryDirectory() as tmp:
            vgo = Path(tmp) / "version.go"
            vgo.write_text('package main\nconst Version = "1.1.1"\n', encoding="utf-8")
            log = str(Path(tmp) / "steps.jsonl")
            rc = run("golang", tmp, "patch", log)
            self.assertEqual(rc, 0)
            self.assertIn('"1.1.2"', vgo.read_text())

    def test_golang_explicit_version_file(self) -> None:
        from pipery_tooling.steps.version import run
        with tempfile.TemporaryDirectory() as tmp:
            vf = Path(tmp) / "MY_VERSION"
            vf.write_text("3.0.0\n", encoding="utf-8")
            log = str(Path(tmp) / "steps.jsonl")
            rc = run("golang", tmp, "major", log, version_file="MY_VERSION")
            self.assertEqual(rc, 0)
            self.assertEqual(vf.read_text().strip(), "4.0.0")

    # --- JavaScript ---
    def test_javascript_package_json_bump(self) -> None:
        from pipery_tooling.steps.version import run
        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp) / "package.json"
            pkg.write_text(json.dumps({"name": "myapp", "version": "0.1.0"}), encoding="utf-8")
            log = str(Path(tmp) / "steps.jsonl")
            rc = run("javascript", tmp, "patch", log)
            self.assertEqual(rc, 0)
            data = json.loads(pkg.read_text())
            self.assertEqual(data["version"], "0.1.1")

    # --- Docker ---
    def test_docker_version_file_bump(self) -> None:
        from pipery_tooling.steps.version import run
        with tempfile.TemporaryDirectory() as tmp:
            vf = Path(tmp) / "VERSION"
            vf.write_text("1.2.3\n", encoding="utf-8")
            log = str(Path(tmp) / "steps.jsonl")
            rc = run("docker", tmp, "minor", log)
            self.assertEqual(rc, 0)
            self.assertEqual(vf.read_text().strip(), "1.3.0")

    def test_docker_dockerfile_label_bump(self) -> None:
        from pipery_tooling.steps.version import run
        with tempfile.TemporaryDirectory() as tmp:
            df = Path(tmp) / "Dockerfile"
            df.write_text('FROM alpine\nLABEL version="2.0.0"\n', encoding="utf-8")
            log = str(Path(tmp) / "steps.jsonl")
            rc = run("docker", tmp, "patch", log)
            self.assertEqual(rc, 0)
            self.assertIn('LABEL version="2.0.1"', df.read_text())

    def test_docker_dockerfile_arg_version_bump(self) -> None:
        from pipery_tooling.steps.version import run
        with tempfile.TemporaryDirectory() as tmp:
            df = Path(tmp) / "Dockerfile"
            df.write_text('FROM alpine\nARG VERSION=1.0.0\n', encoding="utf-8")
            log = str(Path(tmp) / "steps.jsonl")
            rc = run("docker", tmp, "major", log)
            self.assertEqual(rc, 0)
            self.assertIn("ARG VERSION=2.0.0", df.read_text())

    def test_unsupported_language_returns_error(self) -> None:
        from pipery_tooling.steps.version import run
        with tempfile.TemporaryDirectory() as tmp:
            log = str(Path(tmp) / "steps.jsonl")
            rc = run("rust", tmp, "patch", log)
            self.assertEqual(rc, 1)


# ---------------------------------------------------------------------------
# SAST tests
# ---------------------------------------------------------------------------

class SASTTests(unittest.TestCase):

    def test_sast_skips_missing_tools_and_succeeds(self) -> None:
        from pipery_tooling.steps import sast
        with tempfile.TemporaryDirectory() as tmp:
            log = str(Path(tmp) / "sast.jsonl")
            with patch("pipery_tooling.steps.sast.tool_available", return_value=False):
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    rc = sast.run("python", tmp, log)
            self.assertEqual(rc, 0)
            entry = json.loads(Path(log).read_text().strip())
            self.assertEqual(entry["event"], "sast")
            self.assertEqual(entry["tools"], [])

    def test_sast_runs_semgrep_when_available(self) -> None:
        from pipery_tooling.steps import sast
        with tempfile.TemporaryDirectory() as tmp:
            log = str(Path(tmp) / "sast.jsonl")
            with (
                patch("pipery_tooling.steps.sast.tool_available", return_value=True),
                patch("pipery_tooling.steps.sast.run_via_psh", return_value=0) as mock_psh,
            ):
                rc = sast.run("python", tmp, log)
            self.assertEqual(rc, 0)
            cmds = [c[0][0] for c in mock_psh.call_args_list]
            self.assertTrue(any("semgrep" in c for c in cmds))

    def test_sast_reports_failure_when_tool_fails(self) -> None:
        from pipery_tooling.steps import sast
        with tempfile.TemporaryDirectory() as tmp:
            log = str(Path(tmp) / "sast.jsonl")
            with (
                patch("pipery_tooling.steps.sast.tool_available", return_value=True),
                patch("pipery_tooling.steps.sast.run_via_psh", return_value=1),
            ):
                rc = sast.run("golang", tmp, log)
            self.assertEqual(rc, 1)
            entry = json.loads(Path(log).read_text().strip())
            self.assertEqual(entry["status"], "failure")

    def test_sast_writes_language_in_log(self) -> None:
        from pipery_tooling.steps import sast
        with tempfile.TemporaryDirectory() as tmp:
            log = str(Path(tmp) / "sast.jsonl")
            with (
                patch("pipery_tooling.steps.sast.tool_available", return_value=False),
            ):
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    sast.run("javascript", tmp, log)
            entry = json.loads(Path(log).read_text().strip())
            self.assertEqual(entry["language"], "javascript")


# ---------------------------------------------------------------------------
# SCA tests
# ---------------------------------------------------------------------------

class SCATests(unittest.TestCase):

    def test_sca_skips_missing_tools_and_succeeds(self) -> None:
        from pipery_tooling.steps import sca
        with tempfile.TemporaryDirectory() as tmp:
            log = str(Path(tmp) / "sca.jsonl")
            with patch("pipery_tooling.steps.sca.tool_available", return_value=False):
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    rc = sca.run("python", tmp, log)
            self.assertEqual(rc, 0)
            entry = json.loads(Path(log).read_text().strip())
            self.assertEqual(entry["event"], "sca")
            self.assertEqual(entry["tools"], [])

    def test_sca_runs_trivy_for_non_docker(self) -> None:
        from pipery_tooling.steps import sca
        with tempfile.TemporaryDirectory() as tmp:
            log = str(Path(tmp) / "sca.jsonl")
            with (
                patch("pipery_tooling.steps.sca.tool_available", return_value=True),
                patch("pipery_tooling.steps.sca.run_via_psh", return_value=0) as mock_psh,
            ):
                rc = sca.run("golang", tmp, log)
            self.assertEqual(rc, 0)
            cmds = [c[0][0] for c in mock_psh.call_args_list]
            self.assertTrue(any("trivy" in c for c in cmds))

    def test_sca_writes_event_and_language(self) -> None:
        from pipery_tooling.steps import sca
        with tempfile.TemporaryDirectory() as tmp:
            log = str(Path(tmp) / "sca.jsonl")
            with patch("pipery_tooling.steps.sca.tool_available", return_value=False):
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    sca.run("javascript", tmp, log)
            entry = json.loads(Path(log).read_text().strip())
            self.assertEqual(entry["language"], "javascript")
            self.assertEqual(entry["event"], "sca")

    def test_sca_reports_failure_when_tool_fails(self) -> None:
        from pipery_tooling.steps import sca
        with tempfile.TemporaryDirectory() as tmp:
            log = str(Path(tmp) / "sca.jsonl")
            with (
                patch("pipery_tooling.steps.sca.tool_available", return_value=True),
                patch("pipery_tooling.steps.sca.run_via_psh", return_value=1),
            ):
                rc = sca.run("python", tmp, log)
            self.assertEqual(rc, 1)
            entry = json.loads(Path(log).read_text().strip())
            self.assertEqual(entry["status"], "failure")


# ---------------------------------------------------------------------------
# Reintegrate tests
# ---------------------------------------------------------------------------

class ReintegrateTests(unittest.TestCase):

    def test_dry_run_prints_and_exits_zero(self) -> None:
        from pipery_tooling.steps import reintegrate
        with tempfile.TemporaryDirectory() as tmp:
            log = str(Path(tmp) / "ri.jsonl")
            rc = reintegrate.run(
                project_path=tmp,
                source_branch="feature/foo",
                target_branch="main",
                log_file=log,
                dry_run=True,
            )
            self.assertEqual(rc, 0)
            entry = json.loads(Path(log).read_text().strip())
            self.assertEqual(entry["status"], "skipped")

    def test_dry_run_logs_branches(self) -> None:
        from pipery_tooling.steps import reintegrate
        with tempfile.TemporaryDirectory() as tmp:
            log = str(Path(tmp) / "ri.jsonl")
            reintegrate.run(
                project_path=tmp,
                source_branch="release/1.0",
                target_branch="develop",
                log_file=log,
                dry_run=True,
            )
            entry = json.loads(Path(log).read_text().strip())
            self.assertEqual(entry["source_branch"], "release/1.0")
            self.assertEqual(entry["target_branch"], "develop")

    def test_existing_pr_exits_zero(self) -> None:
        from pipery_tooling.steps import reintegrate
        with tempfile.TemporaryDirectory() as tmp:
            log = str(Path(tmp) / "ri.jsonl")
            mock_result = MagicMock(returncode=0, stdout="42\n")
            with patch("pipery_tooling.steps.reintegrate.subprocess.run", return_value=mock_result):
                rc = reintegrate.run(
                    project_path=tmp,
                    source_branch="feature/bar",
                    target_branch="main",
                    log_file=log,
                )
            self.assertEqual(rc, 0)
            entry = json.loads(Path(log).read_text().strip())
            self.assertEqual(entry["status"], "already_exists")


# ---------------------------------------------------------------------------
# Deploy tests
# ---------------------------------------------------------------------------

class DeployTests(unittest.TestCase):

    def test_deploy_argocd_builds_correct_command(self) -> None:
        from pipery_tooling.steps import deploy
        with tempfile.TemporaryDirectory() as tmp:
            log = str(Path(tmp) / "deploy.jsonl")
            with patch("pipery_tooling.steps.deploy.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                import os
                env_patch = {
                    "ARGOCD_APP": "myapp",
                    "ARGOCD_SERVER": "argocd.example.com",
                    "ARGOCD_AUTH_TOKEN": "tok",
                }
                with patch.dict(os.environ, env_patch):
                    rc = deploy.run("argocd", "rolling", log)
            self.assertEqual(rc, 0)
            cmd = mock_run.call_args[0][0]
            self.assertIn("argocd", cmd)
            self.assertIn("myapp", cmd)

    def test_deploy_writes_jsonl_entry(self) -> None:
        from pipery_tooling.steps import deploy
        with tempfile.TemporaryDirectory() as tmp:
            log = str(Path(tmp) / "deploy.jsonl")
            with patch("pipery_tooling.steps.deploy.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                deploy.run("helm", "canary", log)
            entry = json.loads(Path(log).read_text().strip())
            self.assertEqual(entry["event"], "deploy")
            self.assertEqual(entry["target"], "helm")
            self.assertEqual(entry["strategy"], "canary")
            self.assertEqual(entry["status"], "success")

    def test_deploy_failure_status_in_log(self) -> None:
        from pipery_tooling.steps import deploy
        with tempfile.TemporaryDirectory() as tmp:
            log = str(Path(tmp) / "deploy.jsonl")
            with patch("pipery_tooling.steps.deploy.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=1)
                rc = deploy.run("cloud-run", "rolling", log)
            self.assertEqual(rc, 1)
            entry = json.loads(Path(log).read_text().strip())
            self.assertEqual(entry["status"], "failure")

    def test_deploy_unsupported_target_returns_error(self) -> None:
        from pipery_tooling.steps import deploy
        with tempfile.TemporaryDirectory() as tmp:
            log = str(Path(tmp) / "deploy.jsonl")
            rc = deploy.run("kubernetes", "rolling", log)
            self.assertEqual(rc, 1)

    def test_deploy_config_file_merged(self) -> None:
        from pipery_tooling.steps import deploy
        with tempfile.TemporaryDirectory() as tmp:
            log = str(Path(tmp) / "deploy.jsonl")
            cfg_file = Path(tmp) / "deploy.yaml"
            cfg_file.write_text("helm_release: myrel\nhelm_chart: mychart\n", encoding="utf-8")
            with patch("pipery_tooling.steps.deploy.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                rc = deploy.run("helm", "rolling", log, config_file=str(cfg_file))
            self.assertEqual(rc, 0)
            cmd = mock_run.call_args[0][0]
            self.assertIn("myrel", cmd)
            self.assertIn("mychart", cmd)


# ---------------------------------------------------------------------------
# CLI integration (argument parsing round-trip via subprocess)
# ---------------------------------------------------------------------------

class CliIntegrationTests(unittest.TestCase):
    """Smoke-test the CLI by running subcommands that don't need external tools."""

    def test_version_subcommand_bumps_pyproject(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pyproject = Path(tmp) / "pyproject.toml"
            pyproject.write_text(
                '[project]\nname = "demo"\nversion = "0.1.0"\n', encoding="utf-8"
            )
            log = str(Path(tmp) / "pipery.jsonl")
            result = _run_cli(
                "--project-path", tmp,
                "--log-file", log,
                "version",
                "--language", "python",
                "--bump", "patch",
            )
            self.assertEqual(result.returncode, 0)
            self.assertIn("0.1.1", result.stdout)
            self.assertIn('version = "0.1.1"', pyproject.read_text())

    def test_reintegrate_dry_run_via_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = str(Path(tmp) / "pipery.jsonl")
            result = _run_cli(
                "--project-path", tmp,
                "--log-file", log,
                "reintegrate",
                "--source-branch", "feat/x",
                "--target-branch", "main",
                "--dry-run",
            )
            self.assertEqual(result.returncode, 0)
            self.assertIn("dry-run", result.stdout)


if __name__ == "__main__":
    unittest.main()
