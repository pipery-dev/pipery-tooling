from __future__ import annotations

from pathlib import Path

from .config import ActionConfig


def toml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def render_config(config: ActionConfig) -> str:
    lines = [
        f"owner = {toml_string(config.owner)}",
        f"action_name = {toml_string(config.action_name)}",
        f"title = {toml_string(config.title)}",
        f"description = {toml_string(config.description)}",
        f"marketplace_category = {toml_string(config.marketplace_category)}",
        f"author = {toml_string(config.author)}",
        f"action_type = {toml_string(config.action_type)}",
        f"default_branch = {toml_string(config.default_branch)}",
        f"version = {toml_string(config.version)}",
        f"repository_visibility = {toml_string(config.repository_visibility)}",
        f"icon = {toml_string(config.icon)}",
        f"test_command = {toml_string(config.test_command)}",
        f"test_project_path = {toml_string(config.test_project_path)}",
        f"test_project_input = {toml_string(config.test_project_input)}",
        f"test_log_path = {toml_string(config.test_log_path)}",
    ]
    success_values = ", ".join(toml_string(value) for value in config.test_log_success_values)
    lines.append(f"test_log_success_values = [{success_values}]")
    cleanup = ", ".join(toml_string(p) for p in config.cleanup_paths)
    lines.append(f"cleanup_paths = [{cleanup}]")
    for item in config.inputs:
        lines.extend(
            [
                "",
                "[[inputs]]",
                f"name = {toml_string(str(item['name']))}",
                f"description = {toml_string(str(item.get('description', '')))}",
                f"required = {'true' if item.get('required') else 'false'}",
                f"default = {toml_string(str(item.get('default', '')))}",
            ]
        )
    for item in config.outputs:
        lines.extend(
            [
                "",
                "[[outputs]]",
                f"name = {toml_string(str(item['name']))}",
                f"description = {toml_string(str(item.get('description', '')))}",
            ]
        )
    for item in config.test_inputs:
        lines.extend(
            [
                "",
                "[[test_inputs]]",
                f"name = {toml_string(str(item['name']))}",
                f"value = {toml_string(str(item.get('value', '')))}",
            ]
        )
    for item in config.test_log_required_fields:
        lines.extend(
            [
                "",
                "[[test_log_required_fields]]",
                f"name = {toml_string(str(item['name']))}",
                f"value = {toml_string(str(item.get('value', '')))}",
            ]
        )
    for case in config.test_cases:
        case_lines = [
            "",
            "[[test_cases]]",
            f"name = {toml_string(str(case.get('name', '')))}",
            f"test_project_path = {toml_string(str(case.get('test_project_path', '')))}",
            f"test_project_input = {toml_string(str(case.get('test_project_input', '')))}",
            f"test_log_path = {toml_string(str(case.get('test_log_path', '')))}",
        ]
        if case.get("test_log_success_values"):
            sv = ", ".join(toml_string(v) for v in case["test_log_success_values"])
            case_lines.append(f"test_log_success_values = [{sv}]")
        lines.extend(case_lines)
    for item in config.docs_examples:
        lines.extend(
            [
                "",
                "[[docs_examples]]",
                f"title = {toml_string(str(item['title']))}",
                f"body = {toml_string(str(item['body']))}",
            ]
        )
    return "\n".join(lines) + "\n"


def render_action_yaml(config: ActionConfig) -> str:
    input_lines: list[str] = []
    if config.inputs:
        input_lines.append("inputs:")
        for item in config.inputs:
            input_lines.extend(
                [
                    f"  {item['name']}:",
                    f"    description: {item.get('description', 'Input for the action')!r}",
                    f"    required: {'true' if item.get('required') else 'false'}",
                    f"    default: {str(item.get('default', ''))!r}",
                ]
            )
    output_lines: list[str] = []
    if config.outputs:
        output_lines.append("outputs:")
        for item in config.outputs:
            output_lines.extend(
                [
                    f"  {item['name']}:",
                    f"    description: {item.get('description', 'Action output')!r}",
                ]
            )
    runs_block = _render_runs_block(config)
    blocks = [
        f"name: {config.title!r}",
        f"description: {config.description!r}",
    ]
    blocks.extend(input_lines)
    blocks.extend(output_lines)
    blocks.append(runs_block.rstrip())
    blocks.append(f"branding:\n  icon: package\n  color: blue")
    return "\n".join(blocks) + "\n"


def _render_runs_block(config: ActionConfig) -> str:
    if config.action_type == "docker":
        return (
            "runs:\n"
            "  using: docker\n"
            "  image: Dockerfile\n"
        )
    if config.action_type == "javascript":
        return (
            "runs:\n"
            "  using: node20\n"
            "  main: dist/index.js\n"
        )
    return (
        "runs:\n"
        "  using: composite\n"
        "  steps:\n"
        "    - id: main\n"
        "      shell: bash\n"
        "      run: |\n"
        "        set -euo pipefail\n"
        "        project_path=\"${INPUT_PROJECT_PATH:-${PIPERY_TEST_PROJECT_PATH:-.}}\"\n"
        "        log_path=\"${PIPERY_LOG_PATH:-pipery.jsonl}\"\n"
        "        if [ ! -d \"$project_path\" ]; then\n"
        "          echo \"Expected project path to exist: $project_path\" >&2\n"
        "          exit 1\n"
        "        fi\n"
        "        printf '{\"event\":\"build\",\"status\":\"success\",\"project_path\":\"%s\"}\\n' \"$project_path\" > \"$log_path\"\n"
        "        echo \"Implement your action logic here for $project_path.\"\n"
    )


def render_readme(config: ActionConfig) -> str:
    input_table = _render_input_table(config)
    output_table = _render_output_table(config)
    example = _render_usage_example(config)
    return f"""# {config.title}

{config.description}

## Status

- Owner: `{config.owner}`
- Repository: `{config.repo_name}`
- Marketplace category: `{config.marketplace_category}`
- Current version: `{config.version}`

## Usage

```yaml
{example}
```

## Inputs

{input_table}

## Outputs

{output_table}

## Development

This repository is managed with `pipery-tooling`.

```bash
pipery-actions test --repo .
pipery-actions docs --repo .
pipery-actions release --repo . --dry-run
```

By default, `pipery-actions test --repo .` executes the action against `{config.test_project_path or 'the configured test project path'}` and validates `{config.test_log_path or 'the configured JSONL log'}`.

## Marketplace Release Flow

1. Update the implementation and changelog.
2. Run `pipery-actions release --repo .`.
3. Push the created git tag and major tag alias.
4. Publish the GitHub release.
"""


def render_usage_doc(config: ActionConfig) -> str:
    sections = [
        f"# Using {config.title}",
        "",
        config.description,
        "",
        "## Recommended workflow",
        "",
        "1. Pin the action to a major tag in production workflows.",
        "2. Keep a representative test project in the repository and point `test_project_path` at it.",
        "3. Emit a `pipery.jsonl` build log during the action run and keep `test_log_path` pointed at it.",
        "4. Make the action consume that path via the configured test input.",
        "5. Keep changelog entries under `## [Unreleased]` until you cut a release.",
        "6. Regenerate docs before publishing a new version.",
        "",
        "## Example",
        "",
        "```yaml",
        _render_usage_example(config),
        "```",
    ]
    for example in config.docs_examples:
        sections.extend(
            [
                "",
                f"## {example['title']}",
                "",
                example["body"],
            ]
        )
    return "\n".join(sections) + "\n"


def render_changelog() -> str:
    return """# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

- Initial scaffold.
"""


def render_ci_workflow(config: ActionConfig) -> str:
    return f"""name: CI

on:
  push:
    branches:
      - {config.default_branch}
  pull_request:

jobs:
  test:
    uses: {config.owner}/pipery-tooling/.github/workflows/pipery-test.yml@v0
"""


def render_release_workflow(config: ActionConfig) -> str:
    build_command_line = (
        "\n      build-command: \"npm ci && npm run build\""
        if config.action_type == "javascript"
        else ""
    )
    return f"""name: Release

on:
  workflow_dispatch:
    inputs:
      bump:
        description: Semver bump kind
        required: true
        default: patch
        type: choice
        options:
          - patch
          - minor
          - major

permissions:
  contents: write

jobs:
  release:
    uses: {config.owner}/pipery-tooling/.github/workflows/pipery-release.yml@v0
    with:
      bump: ${{{{ inputs.bump }}}}{build_command_line}
"""


def render_test_spec(config: ActionConfig) -> str:
    test_project = config.test_project_path or "test-project"
    input_name = config.test_project_input or "project_path"
    log_path = config.test_log_path or "pipery.jsonl"
    return (
        f"name: basic-test\n"
        f"description: Run action against the bundled test fixture.\n"
        f"\n"
        f"source_path: {test_project}\n"
        f"\n"
        f"inputs:\n"
        f"  {input_name}: {test_project}\n"
        f"\n"
        f"expect:\n"
        f"  log_path: {log_path}\n"
        f"  success_values:\n"
        f"    - success\n"
        f"    - succeeded\n"
        f"    - passed\n"
        f"    - ok\n"
        f"  required_fields:\n"
        f"    - name: event\n"
        f"      value: build\n"
    )


def render_gitignore(config: ActionConfig) -> str:
    lines = [
        "__pycache__/",
        ".pytest_cache/",
        ".venv/",
        ".DS_Store",
    ]
    if config.action_type == "javascript":
        lines.extend(["node_modules/", "dist/"])
    return "\n".join(lines) + "\n"


def render_impl_file(config: ActionConfig) -> tuple[Path, str]:
    if config.action_type == "docker":
        return (
            Path("Dockerfile"),
            "FROM alpine:3.20\nRUN apk add --no-cache bash\nCOPY entrypoint.sh /entrypoint.sh\nENTRYPOINT [\"/entrypoint.sh\"]\n",
        )
    if config.action_type == "javascript":
        return (
            Path("dist/index.js"),
            "const fs = require('fs');\n"
            "const projectPath = process.env.INPUT_PROJECT_PATH || process.env.PIPERY_TEST_PROJECT_PATH || '.';\n"
            "const logPath = process.env.PIPERY_LOG_PATH || 'pipery.jsonl';\n"
            "if (!fs.existsSync(projectPath)) {\n"
            "  console.error(`Expected project path to exist: ${projectPath}`);\n"
            "  process.exit(1);\n"
            "}\n"
            "fs.writeFileSync(logPath, `${JSON.stringify({ event: 'build', status: 'success', project_path: projectPath })}\\n`, 'utf8');\n"
            "console.log(`Implement your GitHub Action logic here for ${projectPath}.`);\n",
        )
    return (
        Path("src/main.sh"),
        "#!/usr/bin/env bash\nset -euo pipefail\n\nproject_path=\"${INPUT_PROJECT_PATH:-${PIPERY_TEST_PROJECT_PATH:-.}}\"\nlog_path=\"${PIPERY_LOG_PATH:-pipery.jsonl}\"\nif [ ! -d \"$project_path\" ]; then\n  echo \"Expected project path to exist: $project_path\" >&2\n  exit 1\nfi\nprintf '{\"event\":\"build\",\"status\":\"success\",\"project_path\":\"%s\"}\\n' \"$project_path\" > \"$log_path\"\necho \"Implement your action logic here for $project_path.\"\n",
    )


def render_entrypoint_script() -> str:
    return "#!/usr/bin/env bash\nset -euo pipefail\n\nproject_path=\"${INPUT_PROJECT_PATH:-${PIPERY_TEST_PROJECT_PATH:-.}}\"\nlog_path=\"${PIPERY_LOG_PATH:-pipery.jsonl}\"\nif [ ! -d \"$project_path\" ]; then\n  echo \"Expected project path to exist: $project_path\" >&2\n  exit 1\nfi\nprintf '{\"event\":\"build\",\"status\":\"success\",\"project_path\":\"%s\"}\\n' \"$project_path\" > \"$log_path\"\necho \"Implement your Docker action logic here for $project_path.\"\n"


def render_test_project_readme(config: ActionConfig) -> str:
    return f"""# Test Project

This fixture project exists so `{config.repo_name}` can be executed against a real source tree during `pipery-actions test`.

Replace this directory with a representative source sample for the action.
"""


def _render_input_table(config: ActionConfig) -> str:
    if not config.inputs:
        return "No inputs."
    rows = ["| Name | Required | Default | Description |", "| --- | --- | --- | --- |"]
    for item in config.inputs:
        rows.append(
            f"| `{item['name']}` | {'yes' if item.get('required') else 'no'} | `{item.get('default', '')}` | {item.get('description', '')} |"
        )
    return "\n".join(rows)


def _render_output_table(config: ActionConfig) -> str:
    if not config.outputs:
        return "No outputs."
    rows = ["| Name | Description |", "| --- | --- |"]
    for item in config.outputs:
        rows.append(f"| `{item['name']}` | {item.get('description', '')} |")
    return "\n".join(rows)


def _render_usage_example(config: ActionConfig) -> str:
    lines = [
        "name: Example",
        "on: [push]",
        "",
        "jobs:",
        "  run-action:",
        "    runs-on: ubuntu-latest",
        "    steps:",
        "      - uses: actions/checkout@v4",
        f"      - uses: {config.uses_slug}@v{config.major_version}",
    ]
    if config.inputs:
        lines.append("        with:")
        for item in config.inputs:
            lines.append(f"          {item['name']}: {item.get('default', 'value')}")
    return "\n".join(lines)
