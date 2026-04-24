from __future__ import annotations

import json
import sys
import warnings

from .runner import run_via_psh, tool_available


# Map language -> extra tools to try (in addition to semgrep)
_EXTRA_TOOLS: dict[str, list[tuple[str, str]]] = {
    "python": [("bandit", "bandit -r . -q")],
    "golang": [("gosec", "gosec ./...")],
    "javascript": [("eslint", "eslint . --max-warnings=0")],
}


def run(
    language: str,
    project_path: str,
    log_file: str,
    tools: list[str] | None = None,
) -> int:
    """Run SAST checks for *language* inside *project_path*.

    Always attempts semgrep.  Additional language-specific tools are run when
    installed.  Any tool not found on PATH is skipped with a warning.

    Returns 0 when all installed tools pass, non-zero otherwise.
    """
    tools_run: list[str] = []
    failed: list[str] = []

    # --- semgrep (always attempted) ---
    if tool_available("semgrep"):
        tools_run.append("semgrep")
        rc = run_via_psh("semgrep scan --config=auto --quiet .", log_file, project_path)
        if rc != 0:
            failed.append("semgrep")
    else:
        warnings.warn("semgrep not found on PATH; skipping", stacklevel=2)

    # --- language-specific extras ---
    candidates = _EXTRA_TOOLS.get(language, [])
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
        {"event": "sast", "status": status, "language": language, "tools": tools_run}
    )
    # Write the summary entry via psh (or directly to the log file if psh absent)
    _write_log_entry(entry, log_file, project_path)

    return 1 if failed else 0


def _write_log_entry(entry: str, log_file: str, cwd: str) -> None:
    """Append a JSONL entry to *log_file* (direct write; the individual tool
    runs have already gone through psh)."""
    try:
        with open(log_file, "a", encoding="utf-8") as fh:
            fh.write(entry + "\n")
    except OSError as exc:
        print(f"Warning: could not write log entry: {exc}", file=sys.stderr)
