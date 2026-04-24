# pipery-tooling

Internal Pipery tooling for scaffolding, testing, versioning, docs, and releases of `pipery-dev` GitHub Actions and their sister repositories.

## Purpose

This repository ships a Python CLI, `pipery-actions`, that sister repositories can use to:

- scaffold a new GitHub Action repository with Pipery conventions
- validate repository structure and required release metadata
- execute the action against a checked-in test project fixture
- validate build success from a `pipery.jsonl` log file
- bump semantic versions and keep generated files in sync
- regenerate README and usage docs
- prepare marketplace release notes and git tag instructions

## Requirements

- [uv](https://docs.astral.sh/uv/getting-started/installation/) — used for all dependency management and running the CLI

## Installation

```bash
uv tool install .
```

Or install into a project's environment:

```bash
uv add git+https://github.com/pipery-dev/pipery-tooling
```

## Commands

```bash
pipery-actions scaffold --repo ../my-action --owner pipery-dev --name my-action --title "My Action" --description "Example action"
pipery-actions test --repo ../my-action
pipery-actions version --repo ../my-action --bump minor
pipery-actions docs --repo ../my-action
pipery-actions release --repo ../my-action --bump patch --dry-run
```

## Sister Repo Contract

Each sister repo is expected to contain a `pipery-action.toml` file at its root. The tooling treats that file as the source of truth for:

- action metadata
- documentation generation
- version management
- release preparation
- test fixture configuration

The `test` command uses `test_project_path` to locate a representative source tree, exports that path to the configured input name, and then executes the action implementation locally.
If `test_log_path` is configured, it also parses the generated JSONL log and requires at least one successful build entry plus any configured required fields.

## Development

```bash
# Install dependencies (including dev group)
uv sync --group dev

# Run tests
uv run pytest -v

# Run the CLI locally
uv run pipery-actions --help
```
