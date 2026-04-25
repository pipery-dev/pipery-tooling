from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

SPEC_DIR = ".github/pipery"
SPEC_GLOB = "*_test.yaml"


@dataclass
class TestSpec:
    """A single test case loaded from a *_test.yaml file."""

    name: str
    source_path: str
    description: str = ""
    inputs: dict[str, str] = field(default_factory=dict)
    log_path: str = "pipery.jsonl"
    success_values: list[str] = field(
        default_factory=lambda: ["success", "succeeded", "passed", "ok"]
    )
    required_fields: list[dict[str, str]] = field(default_factory=list)
    expect_failure: bool = False


def discover_test_specs(repo_dir: Path) -> list[TestSpec]:
    """Return all TestSpec objects found in .github/pipery/*_test.yaml, sorted by filename."""
    spec_dir = repo_dir / SPEC_DIR
    if not spec_dir.is_dir():
        return []
    return [load_test_spec(p) for p in sorted(spec_dir.glob(SPEC_GLOB))]


def load_test_spec(path: Path) -> TestSpec:
    """Parse a single *_test.yaml file into a TestSpec."""
    data: dict = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    expect: dict = data.get("expect", {})
    return TestSpec(
        name=str(data.get("name", path.stem)),
        description=str(data.get("description", "")),
        source_path=str(data.get("source_path", ".")),
        inputs={str(k): str(v) for k, v in data.get("inputs", {}).items()},
        log_path=str(expect.get("log_path", "pipery.jsonl")),
        success_values=[
            str(v)
            for v in expect.get("success_values", ["success", "succeeded", "passed", "ok"])
        ],
        required_fields=[
            {str(k): str(v) for k, v in f.items()}
            for f in expect.get("required_fields", [])
        ],
        expect_failure=bool(expect.get("failure", False)),
    )
