from __future__ import annotations

import shutil
import subprocess


def tool_available(name: str) -> bool:
    """Return True if *name* is found on PATH."""
    return shutil.which(name) is not None


def run_via_psh(cmd: str, log_file: str, cwd: str) -> int:
    """Run *cmd* via psh if available, otherwise fall back to subprocess.

    psh wraps the command and writes structured JSONL to *log_file*.
    Returns the exit code.
    """
    if tool_available("psh"):
        result = subprocess.run(
            ["psh", "-log-file", log_file, "-fail-on-error", "-c", cmd],
            cwd=cwd,
            check=False,
        )
    else:
        result = subprocess.run(cmd, shell=True, cwd=cwd, check=False)
    return result.returncode
