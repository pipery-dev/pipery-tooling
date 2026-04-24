from __future__ import annotations

import argparse

from . import sast, sca, version, reintegrate, deploy


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pipery-steps",
        description="Language-agnostic CI/CD steps for Pipery action repos.",
    )
    # Shared options available on every subcommand
    parser.add_argument(
        "--project-path",
        default=".",
        help="Path to the project root (default: current directory).",
    )
    parser.add_argument(
        "--log-file",
        default="pipery.jsonl",
        help="JSONL log file path (default: pipery.jsonl).",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- sast ---
    sast_cmd = subparsers.add_parser(
        "sast", help="Run static analysis security testing (SAST)."
    )
    sast_cmd.add_argument("--language", required=True, help="Project language.")
    sast_cmd.add_argument(
        "--tools",
        nargs="*",
        help="Restrict to specific tools (default: all installed tools for the language).",
    )
    sast_cmd.set_defaults(func=_run_sast)

    # --- sca ---
    sca_cmd = subparsers.add_parser(
        "sca", help="Run software composition analysis (SCA)."
    )
    sca_cmd.add_argument("--language", required=True, help="Project language.")
    sca_cmd.add_argument(
        "--tools",
        nargs="*",
        help="Restrict to specific tools (default: all installed tools for the language).",
    )
    sca_cmd.set_defaults(func=_run_sca)

    # --- version ---
    version_cmd = subparsers.add_parser(
        "version", help="Bump the project version."
    )
    version_cmd.add_argument("--language", required=True, help="Project language.")
    version_cmd.add_argument(
        "--bump",
        required=True,
        choices=["patch", "minor", "major"],
        help="Version component to increment.",
    )
    version_cmd.add_argument(
        "--version-file",
        default=None,
        help="Explicit version file path (relative to --project-path).",
    )
    version_cmd.set_defaults(func=_run_version)

    # --- reintegrate ---
    reintegrate_cmd = subparsers.add_parser(
        "reintegrate", help="Open a reintegration PR."
    )
    reintegrate_cmd.add_argument("--source-branch", required=True, help="Source branch.")
    reintegrate_cmd.add_argument("--target-branch", required=True, help="Target branch.")
    reintegrate_cmd.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would happen without creating a PR.",
    )
    reintegrate_cmd.set_defaults(func=_run_reintegrate)

    # --- deploy ---
    deploy_cmd = subparsers.add_parser(
        "deploy", help="Deploy to a target environment."
    )
    deploy_cmd.add_argument(
        "--target",
        required=True,
        choices=["argocd", "cloud-run", "helm", "ansible"],
        help="Deployment target.",
    )
    deploy_cmd.add_argument(
        "--strategy",
        default="rolling",
        choices=["rolling", "blue-green", "canary"],
        help="Deployment strategy (default: rolling).",
    )
    deploy_cmd.add_argument(
        "--config-file",
        default=None,
        help="Optional YAML config file with deployment parameters.",
    )
    deploy_cmd.set_defaults(func=_run_deploy)

    return parser


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def _run_sast(args: argparse.Namespace) -> int:
    return sast.run(
        language=args.language,
        project_path=args.project_path,
        log_file=args.log_file,
        tools=args.tools,
    )


def _run_sca(args: argparse.Namespace) -> int:
    return sca.run(
        language=args.language,
        project_path=args.project_path,
        log_file=args.log_file,
        tools=args.tools,
    )


def _run_version(args: argparse.Namespace) -> int:
    return version.run(
        language=args.language,
        project_path=args.project_path,
        bump=args.bump,
        log_file=args.log_file,
        version_file=args.version_file,
    )


def _run_reintegrate(args: argparse.Namespace) -> int:
    return reintegrate.run(
        project_path=args.project_path,
        source_branch=args.source_branch,
        target_branch=args.target_branch,
        log_file=args.log_file,
        dry_run=args.dry_run,
    )


def _run_deploy(args: argparse.Namespace) -> int:
    return deploy.run(
        target=args.target,
        strategy=args.strategy,
        log_file=args.log_file,
        config_file=args.config_file,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
