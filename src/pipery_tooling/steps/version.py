from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from .runner import run_via_psh


SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:[-+].+)?$")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run(
    language: str,
    project_path: str,
    bump: str,
    log_file: str,
    version_file: str | None = None,
) -> int:
    """Bump the version for *language* project at *project_path*.

    Prints the new version to stdout and writes a JSONL entry.
    Returns 0 on success, 1 on failure.
    """
    root = Path(project_path).resolve()

    try:
        old_version, new_version = _bump_for_language(language, root, bump, version_file)
    except Exception as exc:
        print(f"Error bumping version: {exc}", file=sys.stderr)
        return 1

    print(new_version)

    entry = json.dumps(
        {
            "event": "version",
            "status": "success",
            "language": language,
            "old_version": old_version,
            "new_version": new_version,
        }
    )
    try:
        with open(log_file, "a", encoding="utf-8") as fh:
            fh.write(entry + "\n")
    except OSError as exc:
        print(f"Warning: could not write log entry: {exc}", file=sys.stderr)

    return 0


# ---------------------------------------------------------------------------
# Language-specific bump logic
# ---------------------------------------------------------------------------

def _bump_for_language(
    language: str, root: Path, bump: str, version_file: str | None
) -> tuple[str, str]:
    if language == "python":
        return _bump_python(root, bump, version_file)
    if language == "golang":
        return _bump_golang(root, bump, version_file)
    if language == "javascript":
        return _bump_javascript(root, bump)
    if language == "docker":
        return _bump_docker(root, bump, version_file)
    raise ValueError(f"Unsupported language: {language}")


# --- Python ---

def _bump_python(root: Path, bump: str, version_file: str | None) -> tuple[str, str]:
    if version_file:
        path = root / version_file
        return _bump_plain_version_file(path, bump)

    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        return _bump_pyproject(pyproject, bump)

    setup_cfg = root / "setup.cfg"
    if setup_cfg.exists():
        return _bump_setup_cfg(setup_cfg, bump)

    setup_py = root / "setup.py"
    if setup_py.exists():
        return _bump_setup_py(setup_py, bump)

    raise FileNotFoundError(
        "Could not find pyproject.toml, setup.cfg, or setup.py in " + str(root)
    )


def _bump_pyproject(path: Path, bump: str) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8")
    # Match `version = "X.Y.Z"` in [project] or [tool.poetry] sections
    pattern = re.compile(r'^(version\s*=\s*["\'])([^"\']+)(["\'])', re.MULTILINE)
    match = pattern.search(text)
    if not match:
        raise ValueError(f"Could not find version field in {path}")
    old = match.group(2)
    new = bump_semver(old, bump)
    new_text = text[: match.start(2)] + new + text[match.end(2) :]
    path.write_text(new_text, encoding="utf-8")
    return old, new


def _bump_setup_cfg(path: Path, bump: str) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(r'^(version\s*=\s*)(.+)$', re.MULTILINE)
    match = pattern.search(text)
    if not match:
        raise ValueError(f"Could not find version field in {path}")
    old = match.group(2).strip()
    new = bump_semver(old, bump)
    new_text = text[: match.start(2)] + new + text[match.end(2) :]
    path.write_text(new_text, encoding="utf-8")
    return old, new


def _bump_setup_py(path: Path, bump: str) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(r'(version\s*=\s*["\'])([^"\']+)(["\'])')
    match = pattern.search(text)
    if not match:
        raise ValueError(f"Could not find version= in {path}")
    old = match.group(2)
    new = bump_semver(old, bump)
    new_text = text[: match.start(2)] + new + text[match.end(2) :]
    path.write_text(new_text, encoding="utf-8")
    return old, new


# --- Go ---

def _bump_golang(root: Path, bump: str, version_file: str | None) -> tuple[str, str]:
    # Prefer explicit version_file
    if version_file:
        path = root / version_file
        return _bump_plain_version_file(path, bump)

    # Try VERSION file
    version_path = root / "VERSION"
    if version_path.exists():
        return _bump_plain_version_file(version_path, bump)

    # Try version.go with a const
    version_go = root / "version.go"
    if version_go.exists():
        return _bump_version_go(version_go, bump)

    raise FileNotFoundError(
        "Could not find VERSION or version.go in " + str(root)
    )


def _bump_version_go(path: Path, bump: str) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(r'(Version\s*=\s*["\'])([^"\']+)(["\'])')
    match = pattern.search(text)
    if not match:
        raise ValueError(f"Could not find Version const in {path}")
    old = match.group(2)
    new = bump_semver(old, bump)
    new_text = text[: match.start(2)] + new + text[match.end(2) :]
    path.write_text(new_text, encoding="utf-8")
    return old, new


# --- JavaScript ---

def _bump_javascript(root: Path, bump: str) -> tuple[str, str]:
    import json as _json

    pkg_json = root / "package.json"
    if not pkg_json.exists():
        raise FileNotFoundError(f"package.json not found in {root}")
    data = _json.loads(pkg_json.read_text(encoding="utf-8"))
    old = data.get("version", "0.0.0")
    new = bump_semver(old, bump)
    data["version"] = new
    pkg_json.write_text(_json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return old, new


# --- Docker ---

def _bump_docker(root: Path, bump: str, version_file: str | None) -> tuple[str, str]:
    if version_file:
        path = root / version_file
        return _bump_plain_version_file(path, bump)

    version_path = root / "VERSION"
    if version_path.exists():
        return _bump_plain_version_file(version_path, bump)

    dockerfile = root / "Dockerfile"
    if dockerfile.exists():
        return _bump_dockerfile(dockerfile, bump)

    raise FileNotFoundError("Could not find VERSION or Dockerfile in " + str(root))


def _bump_dockerfile(path: Path, bump: str) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8")
    # Try LABEL version="X.Y.Z" first
    label_pattern = re.compile(r'(LABEL\s+version=["\'])([^"\']+)(["\'])')
    match = label_pattern.search(text)
    if not match:
        # Try ARG VERSION=X.Y.Z
        arg_pattern = re.compile(r'(ARG\s+VERSION=)([^\s]+)')
        match = arg_pattern.search(text)
        if not match:
            raise ValueError(f"Could not find version label or ARG VERSION in {path}")
    old = match.group(2)
    new = bump_semver(old, bump)
    new_text = text[: match.start(2)] + new + text[match.end(2) :]
    path.write_text(new_text, encoding="utf-8")
    return old, new


# --- Shared helpers ---

def _bump_plain_version_file(path: Path, bump: str) -> tuple[str, str]:
    old = path.read_text(encoding="utf-8").strip()
    new = bump_semver(old, bump)
    path.write_text(new + "\n", encoding="utf-8")
    return old, new


def bump_semver(current: str, bump: str) -> str:
    """Apply a semver bump (patch / minor / major) to *current*."""
    match = SEMVER_RE.match(current)
    if not match:
        raise ValueError(f"Not a valid semver: {current!r}")
    major, minor, patch = (int(g) for g in match.groups())
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    if bump == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"Unsupported bump kind: {bump!r}")
