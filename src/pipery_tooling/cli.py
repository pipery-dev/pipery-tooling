from __future__ import annotations

import argparse

from .commands import (
    cleanup_command,
    docs_command,
    release_command,
    scaffold_command,
    tag_command,
    test_command,
    version_command,
    sync_command,
    create_tags_command,
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
    release.add_argument(
        "--platform",
        choices=["github", "gitlab", "bitbucket", "all"],
        default="all",
        help="Create platform-specific release branches (default: all).",
    )
    release.add_argument(
        "--create-release-branches",
        action="store_true",
        help="Create platform-specific release branches (release/PLATFORM-vX.Y.Z).",
    )
    release.add_argument(
        "--inline-scripts",
        action="store_true",
        help="Inline scripts into GitLab and Bitbucket pipeline files for platform branches.",
    )
    release.set_defaults(func=release_command)

    tag = subparsers.add_parser("tag", help="Manage semantic version tags.")
    tag.add_argument("--repo", required=True, help="Repository directory.")
    tag_subparsers = tag.add_subparsers(dest="tag_action", required=True)

    create_version = tag_subparsers.add_parser(
        "create-version",
        help="Create all tags for a version release.",
    )
    create_version.add_argument("--version", required=True, help="Version string (e.g., 1.2.3).")
    create_version.add_argument("--commit", required=True, help="Commit hash to tag.")
    create_version.add_argument("--platform", help="Platform suffix (e.g., gitlab).")
    create_version.add_argument("--push", action="store_true", help="Push tags to origin.")
    create_version.set_defaults(func=tag_command)

    update_rolling = tag_subparsers.add_parser(
        "update-rolling",
        help="Update rolling tags (major/minor/latest) if version is newer.",
    )
    update_rolling.add_argument("--version", required=True, help="Version string (e.g., 1.2.3).")
    update_rolling.add_argument("--commit", required=True, help="Commit hash the version is at.")
    update_rolling.add_argument("--platform", help="Platform suffix (e.g., gitlab).")
    update_rolling.add_argument("--push", action="store_true", help="Push updates to origin.")
    update_rolling.set_defaults(func=tag_command)

    reconcile = tag_subparsers.add_parser(
        "reconcile",
        help="Reconcile all tags for a platform.",
    )
    reconcile.add_argument("--platform", help="Platform suffix (e.g., gitlab). All platforms if not specified.")
    reconcile.add_argument("--push", action="store_true", help="Push updates to origin.")
    reconcile.set_defaults(func=tag_command)

    list_tags = tag_subparsers.add_parser(
        "list",
        help="List all tags grouped by version.",
    )
    list_tags.add_argument("--platform", help="Filter by platform (e.g., gitlab).")
    list_tags.set_defaults(func=tag_command)

    validate = tag_subparsers.add_parser(
        "validate",
        help="Validate tags.",
    )
    validate.add_argument("--tag", help="Specific tag to validate. All if not specified.")
    validate.add_argument("--platform", help="Filter by platform.")
    validate.set_defaults(func=tag_command)

    cleanup_tags = tag_subparsers.add_parser(
        "cleanup",
        help="Remove orphaned or invalid tags.",
    )
    cleanup_tags.add_argument("--remove-orphaned", action="store_true", help="Remove orphaned tags.")
    cleanup_tags.add_argument("--remove-duplicates", action="store_true", help="Remove duplicate version tags.")
    cleanup_tags.add_argument("--platform", help="Platform filter.")
    cleanup_tags.add_argument("--push", action="store_true", help="Push deletions to origin.")
    cleanup_tags.set_defaults(func=tag_command)

    # Sync command
    sync = subparsers.add_parser("sync", help="Sync repositories to GitLab and/or Bitbucket.")
    sync.add_argument(
        "--platform",
        choices=["gitlab", "bitbucket", "all"],
        default="all",
        help="Target platform(s). Default: all",
    )
    sync.add_argument(
        "--repos",
        help="Comma-separated list of repos to sync (owner/repo format). If not specified, syncs all default Pipery repos.",
    )
    sync.add_argument("--gitlab-token", help="GitLab authentication token. Defaults to GITLAB_TOKEN env var.")
    sync.add_argument("--bitbucket-token", help="Bitbucket authentication token. Defaults to BITBUCKET_TOKEN env var.")
    sync.add_argument("--bitbucket-workspace", help="Bitbucket workspace. Defaults to BITBUCKET_WORKSPACE env var.")
    sync.add_argument("--report", help="Save sync report to file.")
    sync.add_argument("-v", "--verbose", action="store_true", help="Verbose logging.")
    sync.set_defaults(func=sync_command)

    # Create tags command
    create_tags = subparsers.add_parser("create-tags", help="Create tags on GitLab and/or Bitbucket.")
    create_tags.add_argument(
        "--platform",
        choices=["gitlab", "bitbucket", "all"],
        default="all",
        help="Target platform(s). Default: all",
    )
    create_tags.add_argument(
        "--repos",
        help="Comma-separated list of repos to create tags in. If not specified, uses all default Pipery repos.",
    )
    create_tags.add_argument("--gitlab-token", help="GitLab authentication token. Defaults to GITLAB_TOKEN env var.")
    create_tags.add_argument("--bitbucket-token", help="Bitbucket authentication token. Defaults to BITBUCKET_TOKEN env var.")
    create_tags.add_argument("--bitbucket-workspace", help="Bitbucket workspace. Defaults to BITBUCKET_WORKSPACE env var.")
    create_tags.add_argument("--report", help="Save tag creation report to file.")
    create_tags.add_argument("-v", "--verbose", action="store_true", help="Verbose logging.")
    create_tags.set_defaults(func=create_tags_command)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
