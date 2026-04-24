from __future__ import annotations

import json
import sys
import warnings

from .runner import run_via_psh, tool_available


# (tool_name, command) pairs per language
_LANG_TOOLS: dict[str, list[tuple[str, str]]] = {
    "python": [("pip-audit", "pip-audit")],
    "golang": [("nancy", "go list -json -m all | nancy sleuth")],
    "javascript": [("npm", "npm audit --audit-level=high")],
    "docker": [("trivy", "trivy fs --exit-code 0 .")],
}


def run(
    language: str,
    project_path: str,
    log_file: str,
    tools: list[str] | None = None,
) -> int:
    """Run SCA checks for *language* inside *project_path*.

    Always attempts trivy (except for docker which only uses trivy via the
    language-specific list).  Additional language-specific tools are run when
    installed.  Any tool not found on PATH is skipped with a warning.

    Returns 0 when all installed tools pass, non-zero otherwise.
    """
    tools_run: list[str] = []
    failed: list[str] = []

    # --- trivy (always attempted for non-docker; docker handled via _LANG_TOOLS) ---
    if language != "docker":
        if tool_available("trivy"):
            tools_run.append("trivy")
            rc = run_via_psh(
                "trivy fs --exit-code 0 --severity HIGH,CRITICAL .",
                log_file,
                project_path,
            )
            if rc != 0:
                failed.append("trivy")
        else:
            warnings.warn("trivy not found on PATH; skipping", stacklevel=2)

    # --- language-specific extras ---
    candidates = _LANG_TOOLS.get(language, [])
    for tool_name, cmd in candidates:
        if tools is not None and tool_name not in tools:
            continue
        if tool_available(tool_name):
            tools_run.append(tool_name)
            rc = run_via_psh(cmd, log_file, project_path)
            if rc != 0:
                failed.append(tool_name)
        else:
            warnings.warn(f"{tool_name} not found on PATH; skipping", stacklevel=2)

    status = "failure" if failed else "success"
    entry = json.dumps(
        {"event": "sca", "status": status, "language": language, "tools": tools_run}
    )
    _write_log_entry(entry, log_file, project_path)

    return 1 if failed else 0


def _write_log_entry(entry: str, log_file: str, cwd: str) -> None:
    try:
        with open(log_file, "a", encoding="utf-8") as fh:
            fh.write(entry + "\n")
    except OSError as exc:
        print(f"Warning: could not write log entry: {exc}", file=sys.stderr)
