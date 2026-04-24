from __future__ import annotations

import json
import subprocess
import sys


def run(
    project_path: str,
    source_branch: str,
    target_branch: str,
    log_file: str,
    dry_run: bool = False,
) -> int:
    """Create a reintegration PR from *source_branch* into *target_branch*.

    If a PR already exists for this head/base combination, prints a message
    and exits 0.  In dry-run mode only prints what would happen.

    Returns 0 on success, 1 on failure.
    """
    title = f"Reintegrate {source_branch} into {target_branch}"
    body = "Automated reintegration."

    if dry_run:
        print(
            f"[dry-run] Would create PR: '{title}' "
            f"(--base {target_branch} --head {source_branch})"
        )
        _write_log(log_file, "skipped", source_branch, target_branch)
        return 0

    # Check whether a PR already exists for this head/base pair
    check = subprocess.run(
        [
            "gh", "pr", "list",
            "--base", target_branch,
            "--head", source_branch,
            "--json", "number",
            "--jq", ".[].number",
        ],
        cwd=project_path,
        capture_output=True,
        text=True,
        check=False,
    )
    if check.returncode == 0 and check.stdout.strip():
        pr_number = check.stdout.strip()
        print(f"PR #{pr_number} already exists for {source_branch} -> {target_branch}")
        _write_log(log_file, "already_exists", source_branch, target_branch)
        return 0

    result = subprocess.run(
        [
            "gh", "pr", "create",
            "--base", target_branch,
            "--head", source_branch,
            "--title", title,
            "--body", body,
            "--fill",
        ],
        cwd=project_path,
        check=False,
        text=True,
    )

    status = "success" if result.returncode == 0 else "failure"
    _write_log(log_file, status, source_branch, target_branch)

    if result.returncode != 0:
        print(f"gh pr create failed with exit code {result.returncode}", file=sys.stderr)
        return 1

    return 0


def _write_log(log_file: str, status: str, source: str, target: str) -> None:
    entry = json.dumps(
        {
            "event": "reintegrate",
            "status": status,
            "source_branch": source,
            "target_branch": target,
        }
    )
    try:
        with open(log_file, "a", encoding="utf-8") as fh:
            fh.write(entry + "\n")
    except OSError as exc:
        print(f"Warning: could not write log entry: {exc}", file=sys.stderr)
