from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import tomllib


CONFIG_FILE_NAME = "pipery-action.toml"


@dataclass(slots=True)
class ActionConfig:
    owner: str
    action_name: str
    title: str
    description: str
    marketplace_category: str
    author: str
    action_type: str = "composite"
    default_branch: str = "main"
    version: str = "0.1.0"
    repository_visibility: str = "public"
    inputs: list[dict[str, Any]] = field(default_factory=list)
    outputs: list[dict[str, Any]] = field(default_factory=list)
    test_command: str = ""
    test_project_path: str = ""
    test_project_input: str = ""
    test_inputs: list[dict[str, str]] = field(default_factory=list)
    test_log_path: str = ""
    test_log_success_values: list[str] = field(default_factory=list)
    test_log_required_fields: list[dict[str, str]] = field(default_factory=list)
    test_cases: list[dict[str, Any]] = field(default_factory=list)
    cleanup_paths: list[str] = field(default_factory=lambda: ["pipery.jsonl"])
    docs_examples: list[dict[str, str]] = field(default_factory=list)

    @property
    def repo_name(self) -> str:
        return self.action_name

    @property
    def uses_slug(self) -> str:
        return f"{self.owner}/{self.repo_name}"

    @property
    def major_version(self) -> str:
        return self.version.split(".", maxsplit=1)[0]

    @property
    def minor_version(self) -> str:
        parts = self.version.split(".")
        return f"{parts[0]}.{parts[1]}"

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "ActionConfig":
        return cls(
            owner=str(data["owner"]),
            action_name=str(data["action_name"]),
            title=str(data["title"]),
            description=str(data["description"]),
            marketplace_category=str(data.get("marketplace_category", "continuous-integration")),
            author=str(data.get("author", data["owner"])),
            action_type=str(data.get("action_type", "composite")),
            default_branch=str(data.get("default_branch", "main")),
            version=str(data.get("version", "0.1.0")),
            repository_visibility=str(data.get("repository_visibility", "public")),
            inputs=list(data.get("inputs", [])),
            outputs=list(data.get("outputs", [])),
            test_command=str(data.get("test_command", "")),
            test_project_path=str(data.get("test_project_path", "")),
            test_project_input=str(data.get("test_project_input", "")),
            test_inputs=list(data.get("test_inputs", [])),
            test_log_path=str(data.get("test_log_path", "")),
            test_log_success_values=[str(item) for item in data.get("test_log_success_values", ["success"])],
            test_log_required_fields=list(data.get("test_log_required_fields", [])),
            test_cases=list(data.get("test_cases", [])),
            cleanup_paths=list(data.get("cleanup_paths", ["pipery.jsonl"])),
            docs_examples=list(data.get("docs_examples", [])),
        )


def load_config(repo_dir: Path) -> ActionConfig:
    path = repo_dir / CONFIG_FILE_NAME
    if not path.exists():
        raise FileNotFoundError(f"Missing config file: {path}")
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    return ActionConfig.from_mapping(data)
