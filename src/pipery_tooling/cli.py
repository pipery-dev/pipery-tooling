from __future__ import annotations

import argparse

from .commands import (
    cleanup_command,
    docs_command,
    release_command,
    scaffold_command,
    test_command,
    version_command,
)



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pipery-actions",
        description="Manage Pipery GitHub Action sister repositories.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    scaffold = subparsers.add_parser("scaffold", help="Create a new action sister repository scaffold.")
    scaffold.add_argument("--repo", required=True, help="Target repository directory.")
    scaffold.add_argument("--owner", required=True, help="GitHub organization or user owning the action.")
    scaffold.add_argument("--name", required=True, help="GitHub repository name for the action.")
    scaffold.add_argument("--title", required=True, help="Marketplace-facing action title.")
    scaffold.add_argument("--description", required=True, help="Short action description.")
    scaffold.add_argument(
        "--marketplace-category",
        default="continuous-integration",
        help="GitHub Marketplace category.",
    )
    scaffold.add_argument("--author", help="Action author.")
    scaffold.add_argument(
        "--action-type",
        choices=["composite", "docker", "javascript"],
        default="composite",
        help="GitHub Action runtime type.",
    )
    scaffold.add_argument("--default-branch", default="main", help="Default git branch.")
    scaffold.add_argument("--version", default="0.1.0", help="Initial semver version.")
    scaffold.add_argument("--test-command", help="Optional extra validation command for the sister repo.")
    scaffold.add_argument(
        "--test-project-path",
        default="test-project",
        help="Repository-relative source fixture path used when executing the action under test.",
    )
    scaffold.add_argument(
        "--test-project-input",
        default="project_path",
        help="Input name that receives the test project path during `pipery-actions test`.",
    )
    scaffold.add_argument("--force", action="store_true", help="Overwrite existing generated files.")
    scaffold.set_defaults(func=scaffold_command)

    test = subparsers.add_parser("test", help="Validate an action sister repository.")
    test.add_argument("--repo", required=True, help="Action repository directory.")
    test.add_argument(
        "--run-test-command",
        action="store_true",
        help="Run the configured `test_command` after structural validation.",
    )
    test.set_defaults(func=test_command)

    cleanup = subparsers.add_parser("cleanup", help="Remove test artifacts from an action repository.")
    cleanup.add_argument("--repo", required=True, help="Action repository directory.")
    cleanup.set_defaults(func=cleanup_command)

    version = subparsers.add_parser("version", help="Update semantic version metadata.")
    version.add_argument("--repo", required=True, help="Action repository directory.")
    version_group = version.add_mutually_exclusive_group(required=True)
    version_group.add_argument("--bump", choices=["patch", "minor", "major"], help="Version bump kind.")
    version_group.add_argument("--set-version", help="Explicit semver version.")
    version.set_defaults(func=version_command)

    docs = subparsers.add_parser("docs", help="Regenerate README and docs content.")
    docs.add_argument("--repo", required=True, help="Action repository directory.")
    docs.set_defaults(func=docs_command)

    release = subparsers.add_parser("release", help="Prepare a marketplace release.")
    release.add_argument("--repo", required=True, help="Action repository directory.")
    release_group = release.add_mutually_exclusive_group()
    release_group.add_argument("--bump", choices=["patch", "minor", "major"], help="Version bump kind.")
    release_group.add_argument("--set-version", help="Explicit semver version.")
    release.add_argument("--dry-run", action="store_true", help="Skip all git operations.")
    release.add_argument("--commit", action="store_true", help="Commit release changes with 'Release vX.Y.Z'.")
    release.add_argument("--create-tags", action="store_true", help="Create local git tags on the source branch.")
    release.add_argument(
        "--release-branch",
        action="store_true",
        help="Build a slim releases/vMAJOR branch with only runtime files and tag it there.",
    )
    release.add_argument("--push", action="store_true", help="Commit, tag, and push everything to origin.")
    release.set_defaults(func=release_command)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
