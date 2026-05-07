"""
Script inlining for GitLab CI and Bitbucket Pipelines.

Replaces bash script calls with actual script content, properly indented for YAML.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

Platform = Literal["github", "gitlab", "bitbucket"]


def inline_scripts(platform: Platform, pipeline_file: Path) -> None:
    """
    Inline all script references in a pipeline configuration file.

    Finds all lines that call bash scripts (e.g., "bash ./src/step-*.sh")
    and replaces them with the actual script content, properly indented.

    Args:
        platform: Platform type (gitlab or bitbucket)
        pipeline_file: Path to the pipeline YAML file

    Raises:
        FileNotFoundError: If pipeline file or referenced scripts don't exist.
        ValueError: If script inlining fails.
    """
    if not pipeline_file.exists():
        raise FileNotFoundError(f"Pipeline file not found: {pipeline_file}")

    content = pipeline_file.read_text(encoding="utf-8")
    repo_dir = pipeline_file.parent

    # Pattern to match bash script calls:
    # - bash ./src/step-*.sh
    # - bash ./src/script-name.sh
    # - bash src/step-*.sh
    pattern = r"^\s*-\s+bash\s+\./?src/([a-z0-9\-_.]+\.sh)\s*$"

    lines = content.split("\n")
    modified_lines = []

    for i, line in enumerate(lines):
        match = re.match(pattern, line)
        if match:
            script_name = match.group(1)
            script_path = repo_dir / "src" / script_name

            if not script_path.exists():
                raise FileNotFoundError(
                    f"Referenced script not found: {script_path}\n"
                    f"In line {i + 1} of {pipeline_file.name}"
                )

            # Get indentation from the original line
            indent_match = re.match(r"^(\s*)-", line)
            base_indent = indent_match.group(1) if indent_match else "  "

            # Read script content
            script_content = script_path.read_text(encoding="utf-8").rstrip()

            # For YAML, we need to use literal block scalar syntax (|) to preserve formatting
            # Replace the script call with a literal block scalar
            modified_lines.append(f'{base_indent}- |')

            # Add script content with proper indentation
            for script_line in script_content.split("\n"):
                # Add two more spaces of indentation for the content inside the block scalar
                modified_lines.append(f'{base_indent}  {script_line}')
        else:
            modified_lines.append(line)

    # Write back the modified content
    pipeline_file.write_text("\n".join(modified_lines), encoding="utf-8")


def inline_scripts_in_directory(
    platform: Platform,
    repo_dir: Path,
) -> int:
    """
    Inline scripts in all pipeline files of a given platform.

    Args:
        platform: Platform type (gitlab or bitbucket)
        repo_dir: Path to the repository root

    Returns:
        Number of files processed.

    Raises:
        FileNotFoundError: If pipeline files don't exist.
    """
    if platform == "gitlab":
        pipeline_file = repo_dir / ".gitlab-ci.yml"
    elif platform == "bitbucket":
        pipeline_file = repo_dir / "bitbucket-pipelines.yml"
    else:
        raise ValueError(f"Unsupported platform for inlining: {platform}")

    if not pipeline_file.exists():
        raise FileNotFoundError(f"Pipeline file not found: {pipeline_file}")

    try:
        inline_scripts(platform, pipeline_file)
        return 1
    except (FileNotFoundError, ValueError) as e:
        raise ValueError(
            f"Failed to inline scripts in {pipeline_file.name}: {e}"
        ) from e


def validate_pipeline_file(pipeline_file: Path) -> bool:
    """
    Validate that a pipeline file doesn't have broken script references.

    Args:
        pipeline_file: Path to the pipeline YAML file

    Returns:
        True if all script references are valid, False otherwise.
    """
    if not pipeline_file.exists():
        return False

    content = pipeline_file.read_text(encoding="utf-8")
    repo_dir = pipeline_file.parent
    pattern = r"^\s*-\s+bash\s+\./?src/([a-z0-9\-_.]+\.sh)\s*$"

    lines = content.split("\n")
    for i, line in enumerate(lines):
        match = re.match(pattern, line)
        if match:
            script_name = match.group(1)
            script_path = repo_dir / "src" / script_name
            if not script_path.exists():
                return False

    return True
