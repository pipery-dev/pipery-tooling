from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any

from .config import ActionConfig, CONFIG_FILE_NAME, load_config
from .test_discovery import TestSpec, discover_test_specs
from .rendering import (
    render_action_yaml,
    render_changelog,
    render_ci_workflow,
    render_config,
    render_entrypoint_script,
    render_gitignore,
    render_impl_file,
    render_readme,
    render_release_workflow,
    render_test_project_readme,
    render_test_spec,
    render_usage_doc,
)
from .cross_platform_sync import RepositorySynchronizer
from .rolling_tag_manager import TagManager as RollingTagManager, TagOperationError
from .tag_manager import TagManager
from .version_parser import VersionParser


logger = logging.getLogger(__name__)


SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:[-+].+)?$")


# ---------------------------------------------------------------------------
# scaffold
# ---------------------------------------------------------------------------

def scaffold_command(args: argparse.Namespace) -> int:
    repo_dir = Path(args.repo).resolve()
    config = ActionConfig(
        owner=args.owner,
        action_name=args.name,
        title=args.title,
        description=args.description,
        marketplace_category=args.marketplace_category,
        author=args.author or args.owner,
        action_type=args.action_type,
        default_branch=args.default_branch,
        version=args.version,
        inputs=[
            {
                "name": "project_path",
                "description": "Path to the project source tree the action should operate on.",
                "required": False,
                "default": ".",
            }
        ],
        test_command=args.test_command or "",
        test_project_path=args.test_project_path,
        test_project_input=args.test_project_input,
        test_log_path="pipery.jsonl",
        test_log_success_values=["success", "succeeded", "passed", "ok"],
        test_log_required_fields=[{"name": "event", "value": "build"}],
    )
    write_scaffold(repo_dir, config, overwrite=args.force)
    print(f"Scaffolded {config.repo_name} in {repo_dir}")
    return 0


def write_scaffold(repo_dir: Path, config: ActionConfig, overwrite: bool = False) -> None:
    files = {
        repo_dir / CONFIG_FILE_NAME: render_config(config),
        repo_dir / "README.md": render_readme(config),
        repo_dir / "CHANGELOG.md": render_changelog(),
        repo_dir / "action.yml": render_action_yaml(config),
        repo_dir / "docs" / "usage.md": render_usage_doc(config),
        repo_dir / ".github" / "workflows" / "ci.yml": render_ci_workflow(config),
        repo_dir / ".github" / "workflows" / "release.yml": render_release_workflow(config),
        repo_dir / ".github" / "pipery" / "basic_test.yaml": render_test_spec(config),
        repo_dir / ".gitignore": render_gitignore(config),
        repo_dir / config.test_project_path / "README.md": render_test_project_readme(config),
    }
    impl_path, impl_content = render_impl_file(config)
    files[repo_dir / impl_path] = impl_content
    if config.action_type == "docker":
        files[repo_dir / "entrypoint.sh"] = render_entrypoint_script()
    for path, content in files.items():
        if path.exists() and not overwrite:
            raise FileExistsError(f"{path} already exists. Use --force to overwrite.")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    if config.action_type in {"composite", "docker"}:
        _make_executable(repo_dir / impl_path)
    if config.action_type == "docker":
        _make_executable(repo_dir / "entrypoint.sh")


# ---------------------------------------------------------------------------
# cleanup
# ---------------------------------------------------------------------------

def cleanup_command(args: argparse.Namespace) -> int:
    repo_dir = Path(args.repo).resolve()
    config = load_config(repo_dir)
    removed = clean_artifacts(repo_dir, config)
    for path in removed:
        print(f"Removed: {path}")
    if not removed:
        print("Nothing to clean up.")
    return 0


def clean_artifacts(repo_dir: Path, config: ActionConfig) -> list[Path]:
    removed: list[Path] = []
    for pattern in config.cleanup_paths:
        for path in sorted(repo_dir.glob(pattern)):
            if path.is_file():
                path.unlink()
                removed.append(path.relative_to(repo_dir))
    return removed


# ---------------------------------------------------------------------------
# test
# ---------------------------------------------------------------------------

def test_command(args: argparse.Namespace) -> int:
    repo_dir = Path(args.repo).resolve()
    config = load_config(repo_dir)
    errors = validate_repo(repo_dir, config)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    specs = discover_test_specs(repo_dir)
    if specs:
        return _run_spec_tests(repo_dir, config, specs)
    return run_all_test_cases(repo_dir, config, run_test_command=args.run_test_command)


def _run_spec_tests(repo_dir: Path, config: ActionConfig, specs: list[TestSpec]) -> int:
    passed = 0
    failed = 0
    for spec in specs:
        label = f"{spec.name} [expects failure]" if spec.expect_failure else spec.name
        print(f"\n--- {label} ---")
        if spec.description:
            print(f"    {spec.description}")
        exit_code, errors = _run_one_spec(repo_dir, config, spec)
        if exit_code != 0 or errors:
            for error in errors:
                print(f"ERROR: {error}")
            print(f"FAIL: {spec.name}")
            failed += 1
        else:
            print(f"PASS: {spec.name}")
            passed += 1
    print(f"\n{passed} passed, {failed} failed")
    if failed:
        return 1
    print(f"Validation passed for {config.repo_name}")
    return 0


def _run_one_spec(repo_dir: Path, config: ActionConfig, spec: TestSpec) -> tuple[int, list[str]]:
    source_dir = (repo_dir / spec.source_path).resolve()
    if not source_dir.exists():
        return 1, [f"source_path does not exist: {spec.source_path}"]
    log_path = repo_dir / spec.log_path
    if log_path.exists():
        log_path.unlink()
    command = _resolve_action_test_command(repo_dir, config)
    env = dict(os.environ)
    env["GITHUB_ACTION_PATH"] = str(repo_dir.resolve())
    env["GITHUB_WORKSPACE"] = str(source_dir)
    env["PIPERY_TEST_PROJECT_PATH"] = str(source_dir)
    env["PIPERY_LOG_PATH"] = str(log_path.resolve())
    for name, value in spec.inputs.items():
        env[_input_env_name(name)] = value
    print(f"Running action against: {source_dir}")
    result = subprocess.run(command, cwd=repo_dir, env=env, check=False, text=True)

    if spec.expect_failure:
        if result.returncode != 0:
            print(f"Action failed as expected (exit {result.returncode})")
            return 0, []
        return 1, ["Expected action to fail but it succeeded"]

    if result.returncode != 0:
        return result.returncode, []
    errors = _validate_jsonl_log(
        log_path, spec.log_path, spec.success_values, spec.required_fields
    )
    if not errors:
        print(f"Validated build log: {log_path}")
    return (1 if errors else 0), errors


def run_all_test_cases(
    repo_dir: Path, config: ActionConfig, run_test_command: bool = False
) -> int:
    cases: list[dict[str, Any]] = config.test_cases if config.test_cases else [{}]
    passed = 0
    failed = 0
    for raw_case in cases:
        case_config = _build_case_config(config, raw_case)
        name = str(raw_case.get("name", "default")) if raw_case else "default"
        if len(cases) > 1:
            print(f"\n--- Test case: {name} ---")
        _clean_test_log(repo_dir, case_config)
        action_result = run_action_test(repo_dir, case_config)
        if action_result is not None and action_result.returncode != 0:
            if len(cases) > 1:
                print(f"FAIL: {name}")
            failed += 1
            continue
        log_errors = validate_test_log(repo_dir, case_config)
        if log_errors:
            for error in log_errors:
                print(f"ERROR: {error}")
            if len(cases) > 1:
                print(f"FAIL: {name}")
            failed += 1
            continue
        if len(cases) > 1:
            print(f"PASS: {name}")
        passed += 1
    if run_test_command and config.test_command:
        result = subprocess.run(config.test_command, cwd=repo_dir, shell=True, check=False)
        if result.returncode != 0:
            return result.returncode
    if failed:
        print(f"\n{passed} passed, {failed} failed")
        return 1
    if len(cases) > 1:
        print(f"\n{passed} passed, 0 failed")
    print(f"Validation passed for {config.repo_name}")
    return 0


def _build_case_config(base: ActionConfig, case: dict[str, Any]) -> ActionConfig:
    if not case:
        return base
    return replace(
        base,
        test_project_path=str(case.get("test_project_path", base.test_project_path)),
        test_project_input=str(case.get("test_project_input", base.test_project_input)),
        test_log_path=str(case.get("test_log_path", base.test_log_path)),
        test_inputs=list(case.get("test_inputs", base.test_inputs)),
        test_log_success_values=list(case.get("test_log_success_values", base.test_log_success_values)),
        test_log_required_fields=list(case.get("test_log_required_fields", base.test_log_required_fields)),
    )


def _clean_test_log(repo_dir: Path, config: ActionConfig) -> None:
    if config.test_log_path:
        log_path = repo_dir / config.test_log_path
        if log_path.exists():
            log_path.unlink()


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

def validate_repo(repo_dir: Path, config: ActionConfig) -> list[str]:
    errors: list[str] = []
    required_paths = [
        repo_dir / CONFIG_FILE_NAME,
        repo_dir / "README.md",
        repo_dir / "CHANGELOG.md",
        repo_dir / "action.yml",
        repo_dir / "docs" / "usage.md",
        repo_dir / ".github" / "workflows" / "ci.yml",
        repo_dir / ".github" / "workflows" / "release.yml",
    ]
    for path in required_paths:
        if not path.exists():
            errors.append(f"Missing required file: {path.relative_to(repo_dir)}")
    action_text = _read_if_exists(repo_dir / "action.yml")
    if f"name: '{config.title}'" not in action_text and f'name: "{config.title}"' not in action_text:
        errors.append("action.yml title does not match pipery-action.toml")
    if config.description not in action_text:
        errors.append("action.yml description does not match pipery-action.toml")
    readme_text = _read_if_exists(repo_dir / "README.md")
    if config.version not in readme_text:
        errors.append("README.md does not contain current version")
    changelog_text = _read_if_exists(repo_dir / "CHANGELOG.md")
    if "## [Unreleased]" not in changelog_text:
        errors.append("CHANGELOG.md is missing an [Unreleased] section")
    if not SEMVER_RE.match(config.version):
        errors.append(f"Version is not valid semver: {config.version}")
    if config.test_project_path:
        test_project_dir = repo_dir / config.test_project_path
        if not test_project_dir.exists():
            errors.append(f"Configured test project path does not exist: {config.test_project_path}")
    if config.test_log_path and Path(config.test_log_path).is_absolute():
        errors.append("test_log_path must be repository-relative")
    return errors


# ---------------------------------------------------------------------------
# version / docs
# ---------------------------------------------------------------------------

def version_command(args: argparse.Namespace) -> int:
    repo_dir = Path(args.repo).resolve()
    config = load_config(repo_dir)
    new_version = args.set_version or bump_version(config.version, args.bump)
    updated = replace(config, version=new_version)
    _write_generated_files(repo_dir, updated)
    update_changelog_for_release(repo_dir / "CHANGELOG.md", new_version)
    print(new_version)
    return 0


def docs_command(args: argparse.Namespace) -> int:
    repo_dir = Path(args.repo).resolve()
    config = load_config(repo_dir)
    _write_generated_files(repo_dir, config, docs_only=True)
    print(f"Documentation generated for {config.repo_name}")
    return 0


# ---------------------------------------------------------------------------
# release
# ---------------------------------------------------------------------------

def release_command(args: argparse.Namespace) -> int:
    repo_dir = Path(args.repo).resolve()
    config = load_config(repo_dir)

    if args.bump or args.set_version:
        new_version = args.set_version or bump_version(config.version, args.bump)
        config = replace(config, version=new_version)
        _write_generated_files(repo_dir, config)
        update_changelog_for_release(repo_dir / "CHANGELOG.md", config.version)

    errors = validate_repo(repo_dir, config)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    removed = clean_artifacts(repo_dir, config)
    for path in removed:
        print(f"Cleaned: {path}")

    notes_path = repo_dir / "docs" / "release-notes.md"
    notes_path.write_text(build_release_notes(repo_dir, config), encoding="utf-8")

    use_release_branch = getattr(args, "release_branch", False)
    print(f"Version: {config.version}")
    print(f"Tag:      v{config.version}")
    print(f"Minor:    v{config.minor_version}")
    print(f"Major:    v{config.major_version}")
    if use_release_branch:
        print(f"Branch:   releases/v{config.major_version}")
    print(f"Notes:    {notes_path}")

    if args.dry_run:
        print("Dry run — no git changes made.")
        return 0

    do_push = args.push
    do_commit = args.commit or do_push

    if do_commit:
        _run_git(["git", "add", "."], repo_dir)
        _run_git(["git", "commit", "-m", f"Release v{config.version}"], repo_dir)

    # Handle platform-specific releases (new feature)
    create_platform_branches = getattr(args, "create_release_branches", False)
    if create_platform_branches:
        _create_platform_specific_releases(repo_dir, config, args)

    if use_release_branch:
        if do_push:
            _run_git(["git", "push", "origin", "HEAD"], repo_dir)
        create_release_branch(repo_dir, config, push=do_push)
    else:
        do_tag = args.create_tags or do_push
        if do_tag:
            _run_git(["git", "tag", f"v{config.version}"], repo_dir)
            _run_git(["git", "tag", "-f", f"v{config.minor_version}"], repo_dir)
            _run_git(["git", "tag", "-f", f"v{config.major_version}"], repo_dir)
        if do_push:
            _run_git(["git", "push", "origin", "HEAD"], repo_dir)
            _run_git(["git", "push", "origin", f"v{config.version}"], repo_dir)
            _run_git(["git", "push", "origin", f"v{config.minor_version}", "--force"], repo_dir)
            _run_git(["git", "push", "origin", f"v{config.major_version}", "--force"], repo_dir)

    if not do_commit and not args.create_tags and not use_release_branch:
        print("\nNext commands:")
        print("  git add .")
        print(f"  git commit -m 'Release v{config.version}'")
        if use_release_branch:
            print(f"  pipery-actions release --repo . --release-branch --push")
        else:
            print(f"  git tag v{config.version}")
            print(f"  git tag -f v{config.minor_version}")
            print(f"  git tag -f v{config.major_version}")
            print("  git push origin HEAD")
            print(f"  git push origin v{config.version}")
            print(f"  git push origin v{config.minor_version} --force")
            print(f"  git push origin v{config.major_version} --force")
    return 0


def create_release_branch(repo_dir: Path, config: ActionConfig, push: bool = False) -> None:
    """Build a slim releases/vMAJOR branch containing only runtime files, then tag it."""
    branch = f"releases/v{config.major_version}"

    if not push:
        preview_dir = repo_dir / ".release-preview"
        if preview_dir.exists():
            shutil.rmtree(preview_dir)
        preview_dir.mkdir()
        _copy_runtime_files(repo_dir, preview_dir, config)
        print(f"Release preview at: .release-preview/")
        print(f"Re-run with --push when ready.")
        return

    remote_url = subprocess.check_output(
        ["git", "remote", "get-url", "origin"], cwd=repo_dir, text=True
    ).strip()

    # If GITHUB_TOKEN is available, inject it into the remote URL for authentication
    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token and remote_url.startswith("https://github.com/"):
        remote_url = remote_url.replace("https://github.com/", f"https://x-access-token:{github_token}@github.com/")

    with tempfile.TemporaryDirectory(prefix="pipery-release-") as tmpdir:
        release_dir = Path(tmpdir) / "release"
        release_dir.mkdir()
        _copy_runtime_files(repo_dir, release_dir, config)

        for cmd in [
            ["git", "init"],
            ["git", "checkout", "-b", branch],
            ["git", "config", "user.name", "github-actions[bot]"],
            ["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"],
            ["git", "add", "."],
            ["git", "commit", "-m", f"release v{config.version}"],
            ["git", "remote", "add", "origin", remote_url],
            ["git", "push", "origin", branch, "--force"],
            ["git", "tag", f"v{config.version}"],
            ["git", "tag", "-f", f"v{config.minor_version}"],
            ["git", "tag", "-f", f"v{config.major_version}"],
            ["git", "push", "origin", f"v{config.version}"],
            ["git", "push", "origin", f"v{config.minor_version}", "--force"],
            ["git", "push", "origin", f"v{config.major_version}", "--force"],
        ]:
            _run_git(cmd, release_dir)

    print(f"Released v{config.version} → {branch}")


def _create_platform_specific_releases(repo_dir: Path, config: ActionConfig, args: argparse.Namespace) -> None:
    """
    Create platform-specific release branches with optional script inlining.

    For each platform, creates:
    - GitHub: release/github-v${version} (keeps scripts separate)
    - GitLab: release/gitlab-v${version} (optionally inlines scripts)
    - Bitbucket: release/bitbucket-v${version} (optionally inlines scripts)
    """
    from .release_branches import generate_release_branches
    from .version_tagger import create_platform_tags

    platforms = args.platform if args.platform != "all" else ["github", "gitlab", "bitbucket"]
    if isinstance(platforms, str):
        platforms = [platforms]

    try:
        print(f"\nCreating platform-specific release branches for v{config.version}...")

        # Generate platform-specific branches
        branch_map = generate_release_branches(
            repo_dir,
            config.version,
            platforms=platforms,
            dry_run=False,
        )

        for platform, branch_name in branch_map.items():
            print(f"  ✓ {platform}: {branch_name}")

        # Create platform-specific tags
        print(f"\nCreating platform-specific tags for v{config.version}...")
        tags_map = create_platform_tags(
            repo_dir,
            config.version,
            platforms=platforms,
            dry_run=False,
        )

        for platform, tags in tags_map.items():
            print(f"  {platform}:")
            for tag in tags:
                print(f"    - {tag}")

        if args.push:
            print("\nPushing platform-specific branches and tags...")
            for branch in branch_map.values():
                try:
                    _run_git(["git", "push", "origin", branch], repo_dir)
                    print(f"  ✓ Pushed branch: {branch}")
                except RuntimeError as e:
                    print(f"  ✗ Failed to push branch {branch}: {e}")

            from .version_tagger import push_platform_tags
            try:
                push_platform_tags(repo_dir, config.version, platforms=platforms)
                print(f"  ✓ Pushed all platform-specific tags")
            except RuntimeError as e:
                print(f"  ✗ Failed to push tags: {e}")

    except (RuntimeError, ValueError) as e:
        print(f"ERROR creating platform-specific releases: {e}")


def _copy_runtime_files(repo_dir: Path, dest: Path, config: ActionConfig) -> None:
    shutil.copy2(repo_dir / "action.yml", dest / "action.yml")
    for name in ("README.md", "LICENSE"):
        src = repo_dir / name
        if src.exists():
            shutil.copy2(src, dest / name)
    if config.action_type == "composite":
        src_dir = repo_dir / "src"
        if src_dir.exists():
            (dest / "src").mkdir(parents=True, exist_ok=True)
            for script in src_dir.iterdir():
                if script.is_file():
                    shutil.copy2(script, dest / "src" / script.name)
                    _make_executable(dest / "src" / script.name)
    elif config.action_type == "javascript":
        dist_src = repo_dir / "dist"
        if dist_src.exists():
            shutil.copytree(dist_src, dest / "dist")
    elif config.action_type == "docker":
        for name in ("Dockerfile", "entrypoint.sh"):
            src = repo_dir / name
            if src.exists():
                shutil.copy2(src, dest / name)
        ep = dest / "entrypoint.sh"
        if ep.exists():
            _make_executable(ep)


# ---------------------------------------------------------------------------
# release notes / changelog / version helpers
# ---------------------------------------------------------------------------

def build_release_notes(repo_dir: Path, config: ActionConfig) -> str:
    changelog = _read_if_exists(repo_dir / "CHANGELOG.md")
    return (
        f"# Release v{config.version}\n\n"
        f"Repository: `{config.uses_slug}`\n\n"
        "## Deployment\n\n"
        f"Reference this release as `{config.uses_slug}@v{config.version}`, "
        f"`{config.uses_slug}@v{config.minor_version}`, "
        f"or `{config.uses_slug}@v{config.major_version}`.\n\n"
        "## Changelog\n\n"
        f"{changelog}"
    )


def bump_version(current: str, bump: str) -> str:
    match = SEMVER_RE.match(current)
    if not match:
        raise ValueError(f"Current version is not semver: {current}")
    major, minor, patch = [int(group) for group in match.groups()]
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    if bump == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"Unsupported bump kind: {bump}")


def update_changelog_for_release(path: Path, version: str) -> None:
    text = _read_if_exists(path)
    release_heading = f"## [{version}]"
    if release_heading in text:
        return
    unreleased = "## [Unreleased]\n"
    if unreleased not in text:
        text += "\n## [Unreleased]\n"
    replacement = f"## [Unreleased]\n\n- _Nothing yet._\n\n{release_heading}\n"
    text = text.replace(unreleased, replacement, 1)
    path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# action execution / log validation
# ---------------------------------------------------------------------------

def run_action_test(repo_dir: Path, config: ActionConfig) -> subprocess.CompletedProcess[str] | None:
    if not config.test_project_path:
        return None
    test_project_dir = (repo_dir / config.test_project_path).resolve()
    command = _resolve_action_test_command(repo_dir, config)
    env = _build_action_test_env(repo_dir, config, test_project_dir)
    print(f"Running action against test project: {test_project_dir}")
    return subprocess.run(command, cwd=repo_dir, env=env, check=False, text=True)


def validate_test_log(repo_dir: Path, config: ActionConfig) -> list[str]:
    if not config.test_log_path:
        return []
    log_path = repo_dir / config.test_log_path
    errors = _validate_jsonl_log(
        log_path,
        config.test_log_path,
        config.test_log_success_values,
        config.test_log_required_fields,
    )
    if not errors:
        print(f"Validated build log: {log_path}")
    return errors


def _validate_jsonl_log(
    log_path: Path,
    display_path: str,
    success_values: list[str],
    required_fields: list[dict[str, str]],
) -> list[str]:
    if not log_path.exists():
        return [f"Expected log not created: {display_path}"]
    entries, parse_errors = _load_jsonl_entries(log_path)
    if parse_errors:
        return parse_errors
    if not entries:
        return [f"Log is empty: {display_path}"]
    if not _has_success_entry(entries, success_values):
        return [f"Log has no success entry matching {success_values}: {display_path}"]
    return _missing_required_log_fields(entries, required_fields)


def _resolve_action_test_command(repo_dir: Path, config: ActionConfig) -> list[str]:
    if config.action_type == "docker":
        return [str(repo_dir / "entrypoint.sh")]
    if config.action_type == "javascript":
        node = shutil.which("node")
        if node is None:
            raise FileNotFoundError("Node.js is required to test javascript actions")
        return [node, str(repo_dir / "dist" / "index.js")]
    return [str(repo_dir / "src" / "main.sh")]


def _build_action_test_env(repo_dir: Path, config: ActionConfig, test_project_dir: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["GITHUB_ACTION_PATH"] = str(repo_dir.resolve())
    env["GITHUB_WORKSPACE"] = str(test_project_dir)
    env["PIPERY_TEST_PROJECT_PATH"] = str(test_project_dir)
    if config.test_log_path:
        env["PIPERY_LOG_PATH"] = str((repo_dir / config.test_log_path).resolve())
    if config.test_project_input:
        env[_input_env_name(config.test_project_input)] = str(test_project_dir)
    for item in config.test_inputs:
        env[_input_env_name(str(item["name"]))] = str(item.get("value", ""))
    return env


def _load_jsonl_entries(path: Path) -> tuple[list[dict[str, object]], list[str]]:
    entries: list[dict[str, object]] = []
    errors: list[str] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"Invalid JSON in {path.name} at line {line_number}: {exc.msg}")
            continue
        if not isinstance(record, dict):
            errors.append(f"Expected JSON object in {path.name} at line {line_number}")
            continue
        entries.append(record)
    return entries, errors


def _has_success_entry(entries: list[dict[str, object]], success_values: list[str]) -> bool:
    normalized = {value.lower() for value in success_values}
    for entry in entries:
        for key in ("status", "result", "outcome", "state"):
            value = entry.get(key)
            if isinstance(value, str) and value.lower() in normalized:
                return True
    return False


def _missing_required_log_fields(
    entries: list[dict[str, object]],
    required_fields: list[dict[str, str]],
) -> list[str]:
    errors: list[str] = []
    for requirement in required_fields:
        name = str(requirement["name"])
        value = str(requirement.get("value", ""))
        matched = any(str(entry.get(name, "")) == value for entry in entries)
        if not matched:
            errors.append(f"Test log is missing expected entry field {name}={value!r}")
    return errors


# ---------------------------------------------------------------------------
# git / file helpers
# ---------------------------------------------------------------------------

def _write_generated_files(repo_dir: Path, config: ActionConfig, docs_only: bool = False) -> None:
    (repo_dir / CONFIG_FILE_NAME).write_text(render_config(config), encoding="utf-8")
    (repo_dir / "README.md").write_text(render_readme(config), encoding="utf-8")
    (repo_dir / "docs" / "usage.md").parent.mkdir(parents=True, exist_ok=True)
    (repo_dir / "docs" / "usage.md").write_text(render_usage_doc(config), encoding="utf-8")
    if not docs_only:
        (repo_dir / "action.yml").write_text(render_action_yaml(config), encoding="utf-8")


def _run_git(command: list[str], cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def _input_env_name(name: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]", "_", name).upper()
    return f"INPUT_{normalized}"


def _make_executable(path: Path) -> None:
    current = path.stat().st_mode
    path.chmod(current | 0o111)


def _read_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# sync
# ---------------------------------------------------------------------------

def sync_command(args: argparse.Namespace) -> int:
    """Sync repositories to GitLab and/or Bitbucket."""
    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    synchronizer = RepositorySynchronizer()

    # Determine repos to sync
    repos = None
    if args.repos:
        repos = args.repos.split(",")

    # Determine platforms
    platforms = None
    if args.platform != "all":
        platforms = [args.platform]

    # Get tokens from env or args
    gitlab_token = args.gitlab_token or os.getenv("GITLAB_TOKEN")
    bitbucket_token = args.bitbucket_token or os.getenv("BITBUCKET_TOKEN")
    bitbucket_workspace = args.bitbucket_workspace or os.getenv("BITBUCKET_WORKSPACE")

    if not gitlab_token and (not platforms or "gitlab" in platforms):
        print("ERROR: GitLab token not provided. Set GITLAB_TOKEN env var or use --gitlab-token")
        return 1

    if not bitbucket_token and (not platforms or "bitbucket" in platforms):
        print("ERROR: Bitbucket token not provided. Set BITBUCKET_TOKEN env var or use --bitbucket-token")
        return 1

    # Run sync
    print(f"Syncing repositories to {args.platform}...")
    report = synchronizer.sync_all_platforms(
        repos=repos,
        platforms=platforms,
        gitlab_token=gitlab_token,
        bitbucket_token=bitbucket_token,
        bitbucket_workspace=bitbucket_workspace,
    )

    # Print results
    print("\n" + "=" * 60)
    print(f"Sync Report ({report.platform})")
    print("=" * 60)
    print(f"Timestamp: {report.timestamp}")
    print(f"Total:     {report.to_dict()['summary']['total']}")
    print(f"Success:   {report.to_dict()['summary']['successful']}")
    print(f"Failed:    {report.to_dict()['summary']['failed']}")

    if report.successful:
        print("\nSuccessful syncs:")
        for repo in report.successful:
            print(f"  ✓ {repo}")

    if report.failed:
        print("\nFailed syncs:")
        for repo, error in report.failed.items():
            print(f"  ✗ {repo}: {error}")

    # Save report to file if requested
    if args.report:
        report_path = Path(args.report)
        report_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
        print(f"\nReport saved to: {report_path}")

    return 0 if not report.failed else 1


def create_tags_command(args: argparse.Namespace) -> int:
    """Create missing tags on GitLab and Bitbucket based on release branches."""
    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    # Get tokens
    gitlab_token = args.gitlab_token or os.getenv("GITLAB_TOKEN")
    bitbucket_token = args.bitbucket_token or os.getenv("BITBUCKET_TOKEN")
    bitbucket_workspace = args.bitbucket_workspace or os.getenv("BITBUCKET_WORKSPACE")

    tag_manager = TagManager(
        gitlab_token=gitlab_token,
        bitbucket_token=bitbucket_token,
        bitbucket_workspace=bitbucket_workspace,
    )

    results = {
        "gitlab": {},
        "bitbucket": {},
    }

    # Process GitLab repos
    if args.platform in ("gitlab", "all"):
        if not gitlab_token:
            print("ERROR: GitLab token not provided for --platform gitlab")
            return 1

        print("Creating tags on GitLab...")
        if args.repos:
            for repo in args.repos.split(","):
                print(f"  Processing: {repo}")
                results["gitlab"][repo] = tag_manager.create_missing_tags_gitlab(repo)
        else:
            # Process all default repos
            for repo in RepositorySynchronizer._get_default_repos():
                repo_name = repo.split("/")[-1]
                print(f"  Processing: {repo_name}")
                results["gitlab"][repo_name] = tag_manager.create_missing_tags_gitlab(repo_name)

    # Process Bitbucket repos
    if args.platform in ("bitbucket", "all"):
        if not bitbucket_token:
            print("ERROR: Bitbucket token not provided for --platform bitbucket")
            return 1

        print("Creating tags on Bitbucket...")
        if args.repos:
            for repo in args.repos.split(","):
                print(f"  Processing: {repo}")
                results["bitbucket"][repo] = tag_manager.create_missing_tags_bitbucket(repo)
        else:
            # Process all default repos
            for repo in RepositorySynchronizer._get_default_repos():
                repo_name = repo.split("/")[-1]
                print(f"  Processing: {repo_name}")
                results["bitbucket"][repo_name] = tag_manager.create_missing_tags_bitbucket(repo_name)

    # Print results
    print("\n" + "=" * 60)
    print("Tag Creation Results")
    print("=" * 60)

    for platform, repos_results in results.items():
        if not repos_results:
            continue
        print(f"\n{platform.upper()}:")
        for repo, result in repos_results.items():
            if result.get("errors"):
                print(f"  ✗ {repo}")
                for error in result["errors"]:
                    print(f"      {error}")
            else:
                created_count = len(result.get("created", []))
                updated_count = len(result.get("updated", []))
                print(f"  ✓ {repo} ({created_count} created, {updated_count} updated)")

    # Save results to file if requested
    if args.report:
        report_path = Path(args.report)
        report_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"\nResults saved to: {report_path}")

    return 0


# ---------------------------------------------------------------------------
# tag management (semantic versioning and rolling tags)
# ---------------------------------------------------------------------------

def tag_command(args: argparse.Namespace) -> int:
    """Manage semantic version tags with rolling tag updates."""
    repo_dir = Path(args.repo).resolve()

    if not repo_dir.is_dir():
        print(f"ERROR: Repository directory not found: {repo_dir}")
        return 1

    manager = RollingTagManager(repo_dir)
    tag_action = getattr(args, "tag_action", None)

    try:
        if tag_action == "create-version":
            return _tag_create_version(manager, args)
        elif tag_action == "update-rolling":
            return _tag_update_rolling(manager, args)
        elif tag_action == "reconcile":
            return _tag_reconcile(manager, args)
        elif tag_action == "list":
            return _tag_list(manager, args)
        elif tag_action == "validate":
            return _tag_validate(manager, args)
        elif tag_action == "cleanup":
            return _tag_cleanup(manager, args)
        else:
            print(f"ERROR: Unknown tag action: {tag_action}")
            return 1
    except TagOperationError as exc:
        print(f"ERROR: {exc}")
        return 1
    except Exception as exc:
        print(f"ERROR: {exc}")
        logger.exception("Unexpected error during tag operation")
        return 1


def _tag_create_version(manager: RollingTagManager, args: argparse.Namespace) -> int:
    """Create all tags for a version release."""
    version = args.version.lstrip("v")
    commit = args.commit
    platform = getattr(args, "platform", None)
    push = getattr(args, "push", False)

    parsed = VersionParser.parse_version_string(version)
    if not parsed:
        print(f"ERROR: Invalid version format: {version}")
        return 1

    tags = manager.create_version_tags(version, commit, platform, push)

    print(f"Created tags for v{version}{f'-{platform}' if platform else ''}:")
    for kind, tag in tags.items():
        print(f"  {kind:8} {tag}")

    if push:
        print(f"Pushed {len(tags)} tags to origin")

    return 0


def _tag_update_rolling(manager: RollingTagManager, args: argparse.Namespace) -> int:
    """Update rolling tags if version is newer."""
    version = args.version.lstrip("v")
    commit = args.commit
    platform = getattr(args, "platform", None)
    push = getattr(args, "push", False)

    parsed = VersionParser.parse_version_string(version)
    if not parsed:
        print(f"ERROR: Invalid version format: {version}")
        return 1

    updated = manager.update_rolling_tags(version, commit, platform, push)

    if updated:
        print(f"Updated rolling tags for v{version}{f'-{platform}' if platform else ''}:")
        for kind, tag in updated.items():
            print(f"  {kind:8} {tag}")
        if push:
            print(f"Pushed {len(updated)} tag updates to origin")
    else:
        print(f"No rolling tag updates needed for v{version}")

    return 0


def _tag_reconcile(manager: RollingTagManager, args: argparse.Namespace) -> int:
    """Reconcile all tags for a platform."""
    platform = getattr(args, "platform", None)
    push = getattr(args, "push", False)

    print(f"Reconciling tags{f' for {platform}' if platform else ' for all platforms'}...")
    result = manager.reconcile_all_tags(platform, push)

    print("\nReconciliation Summary:")
    print(f"  Created: {len(result['created'])}")
    print(f"  Updated: {len(result['updated'])}")
    print(f"  Errors:  {len(result['errors'])}")

    if result["created"]:
        print("\nCreated tags:")
        for tag in result["created"]:
            print(f"  + {tag}")

    if result["updated"]:
        print("\nUpdated tags:")
        for tag in result["updated"]:
            print(f"  ~ {tag}")

    if result["errors"]:
        print("\nErrors:")
        for error in result["errors"]:
            print(f"  ! {error}")
        return 1

    return 0


def _tag_list(manager: RollingTagManager, args: argparse.Namespace) -> int:
    """List all tags grouped by version."""
    platform = getattr(args, "platform", None)
    versions = manager.get_versions_by_platform(platform)

    if not versions:
        print("No tags found")
        return 0

    # Group by major.minor series
    by_series = {}
    for tag, parsed in sorted(versions.items()):
        if parsed.is_latest:
            series = "latest"
        else:
            series = f"v{parsed.major}"
            if parsed.minor is not None:
                series += f".{parsed.minor}"
        if series not in by_series:
            by_series[series] = []
        by_series[series].append((tag, parsed))

    # Sort and display
    for series in sorted(by_series.keys(), key=lambda s: (s != "latest", s)):
        tags = by_series[series]
        print(f"\n{series}:")
        for tag, parsed in sorted(tags):
            commit = manager.get_tag_commit(tag)
            commit_short = commit[:8] if commit else "???"
            print(f"  {tag:30} {commit_short}")

    return 0


def _tag_validate(manager: RollingTagManager, args: argparse.Namespace) -> int:
    """Validate tags."""
    specific_tag = getattr(args, "tag", None)
    platform = getattr(args, "platform", None)
    has_errors = False

    if specific_tag:
        errors = manager.validate_tag(specific_tag)
        if errors:
            print(f"✗ {specific_tag}:")
            for error in errors:
                print(f"    {error}")
            has_errors = True
        else:
            print(f"✓ {specific_tag} is valid")
    else:
        versions = manager.get_versions_by_platform(platform)
        if not versions:
            print("No tags found to validate")
            return 0

        for tag in sorted(versions.keys()):
            errors = manager.validate_tag(tag)
            if errors:
                print(f"✗ {tag}:")
                for error in errors:
                    print(f"    {error}")
                has_errors = True
            else:
                print(f"✓ {tag}")

    return 1 if has_errors else 0


def _tag_cleanup(manager: RollingTagManager, args: argparse.Namespace) -> int:
    """Remove orphaned or invalid tags."""
    remove_orphaned = getattr(args, "remove_orphaned", False)
    remove_duplicates = getattr(args, "remove_duplicates", False)
    platform = getattr(args, "platform", None)
    push = getattr(args, "push", False)

    removed = []

    if remove_orphaned:
        orphaned = manager.find_orphaned_tags()
        for tag, parsed in orphaned:
            print(f"Removing orphaned tag: {tag}")
            manager.delete_tag(tag)
            if push:
                manager.delete_remote_tag(tag)
            removed.append(tag)

    if remove_duplicates:
        duplicates = manager.find_duplicate_versions()
        for version, tags in duplicates.items():
            # Keep the first, remove others
            print(f"Version {version} has duplicates: {tags}")
            for tag in tags[1:]:
                print(f"  Removing duplicate: {tag}")
                manager.delete_tag(tag)
                if push:
                    manager.delete_remote_tag(tag)
                removed.append(tag)

    if removed:
        print(f"\nRemoved {len(removed)} tags")
    else:
        print("No tags to clean up")

    return 0
