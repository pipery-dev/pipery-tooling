# Platform-Specific Release Branches and Script Inlining

This document describes the new platform-specific release functionality added to pipery-tooling for supporting GitHub, GitLab, and Bitbucket CI/CD platforms.

## Overview

The platform-specific release feature allows creating release branches tailored to each CI/CD platform with appropriate configurations:

- **GitHub**: `release/github-v${version}` - Maintains scripts separately in `src/`
- **GitLab**: `release/gitlab-v${version}` - Inlines scripts into `.gitlab-ci.yml`
- **Bitbucket**: `release/bitbucket-v${version}` - Inlines scripts into `bitbucket-pipelines.yml`

Each platform gets platform-specific version tags:
- Immutable version tag: `v${version}-${platform}` (e.g., `v1.0.0-gitlab`)
- Major version tag: `v${major}-${platform}` (e.g., `v1-gitlab`)
- Latest tag: `latest-${platform}`

## New Modules

### 1. `release_branches.py`

Handles creation of platform-specific release branches.

**Key Functions:**

- `generate_release_branches(repo_dir, version, platforms, dry_run=False)`
  - Generates platform-specific branches based on the current main branch
  - Optionally inlines scripts for GitLab and Bitbucket
  - Returns dict mapping platform names to branch names

**Example:**
```python
from pipery_tooling.release_branches import generate_release_branches

branches = generate_release_branches(
    repo_dir=Path("/path/to/repo"),
    version="1.0.0",
    platforms=["github", "gitlab", "bitbucket"],
    dry_run=False
)
# Returns: {
#   "github": "release/github-v1.0.0",
#   "gitlab": "release/gitlab-v1.0.0",
#   "bitbucket": "release/bitbucket-v1.0.0"
# }
```

### 2. `script_inliner.py`

Inlines bash script content into pipeline configuration files.

**Key Functions:**

- `inline_scripts(platform, pipeline_file)`
  - Replaces bash script calls with actual script content
  - Uses YAML literal block scalar syntax (`|`) for proper formatting
  - Supports GitLab and Bitbucket pipeline formats

- `validate_pipeline_file(pipeline_file)`
  - Validates that all script references exist
  - Returns True if valid, False otherwise

**How It Works:**

The inliner finds patterns like:
```yaml
script:
  - bash ./src/step-lint.sh
```

And replaces them with:
```yaml
script:
  - |
    #!/usr/bin/env psh
    set -euo pipefail
    # ... full script content here ...
```

**Example:**
```python
from pathlib import Path
from pipery_tooling.script_inliner import inline_scripts

pipeline_file = Path("/path/to/.gitlab-ci.yml")
inline_scripts("gitlab", pipeline_file)
# The file is now modified with inlined scripts
```

### 3. `version_tagger.py`

Creates platform-specific semantic version tags.

**Key Functions:**

- `create_platform_tags(repo_dir, version, platforms, target_commit, dry_run=False)`
  - Creates three types of tags for each platform:
    1. Immutable version tag: `v${version}-${platform}`
    2. Major version tag: `v${major}-${platform}` (can be updated)
    3. Latest tag: `latest-${platform}` (always updated)

- `push_platform_tags(repo_dir, version, platforms, remote="origin")`
  - Pushes all platform-specific tags to remote
  - Uses force-push for rolling tags (major, latest)

- `list_platform_tags(repo_dir, platform, version=None)`
  - Lists existing tags for a platform
  - Optionally filters by specific version

**Example:**
```python
from pathlib import Path
from pipery_tooling.version_tagger import create_platform_tags, push_platform_tags

# Create tags
tags = create_platform_tags(
    repo_dir=Path("/path/to/repo"),
    version="1.0.0",
    platforms=["gitlab", "bitbucket"],
    dry_run=False
)

# Push to remote
push_platform_tags(
    repo_dir=Path("/path/to/repo"),
    version="1.0.0",
    platforms=["gitlab", "bitbucket"]
)
```

## CLI Commands

### Release Command with Platform Options

The `release` command now supports platform-specific releases:

```bash
pipery-actions release \
  --repo <path> \
  --set-version 1.0.0 \
  --create-release-branches \
  --inline-scripts \
  --platform gitlab,bitbucket \
  --commit \
  --push
```

**New Arguments:**

- `--platform github|gitlab|bitbucket|all` (default: all)
  - Specifies which platforms to create release branches for

- `--create-release-branches`
  - Enable creation of platform-specific release branches

- `--inline-scripts`
  - When enabled for GitLab/Bitbucket, inlines scripts into pipeline files

### Tag Command Subcommands

The `tag` command provides several subcommands:

```bash
# Create tags for a specific version
pipery-actions tag create-version \
  --repo <path> \
  --version 1.0.0 \
  --commit <commit-hash> \
  --platform gitlab \
  --push

# Update rolling tags (major/latest)
pipery-actions tag update-rolling \
  --repo <path> \
  --version 1.0.0 \
  --commit <commit-hash> \
  --push

# List tags for a platform
pipery-actions tag list --repo <path> --platform gitlab

# Validate tags
pipery-actions tag validate --repo <path> --platform gitlab

# Reconcile all tags for a platform
pipery-actions tag reconcile --repo <path> --platform bitbucket --push
```

## Workflow Example

### Complete Release to Multiple Platforms

```bash
# 1. Prepare release with version bump
pipery-actions release \
  --repo ./my-action \
  --bump minor

# 2. Create platform-specific branches with inlined scripts
pipery-actions release \
  --repo ./my-action \
  --create-release-branches \
  --inline-scripts \
  --platform all \
  --commit \
  --push

# 3. Verify tags were created correctly
pipery-actions tag list --repo ./my-action

# 4. View specific platform release branch
git checkout release/gitlab-v1.1.0
cat .gitlab-ci.yml  # Scripts are now inlined
```

## Script Inlining Details

### Supported Script Patterns

The inliner recognizes these patterns:
- `- bash ./src/step-*.sh`
- `- bash src/step-*.sh`
- `- bash ./src/script-name.sh`
- Any bash script call indented as a list item

### Indentation Handling

Scripts are properly indented to match the YAML structure:
```yaml
# Input
script:
  - bash ./src/step-lint.sh

# Output (with proper YAML indentation)
script:
  - |
    #!/usr/bin/env psh
    # script content here
```

### Script File Requirements

- Scripts must exist in `./src/` relative to the pipeline file
- Scripts should start with a shebang (`#!/usr/bin/env bash` or similar)
- Script names follow pattern: `step-*.sh` or any `.sh` file

## Error Handling

The modules include comprehensive error handling:

**Script Inlining:**
- Raises `FileNotFoundError` if referenced script doesn't exist
- Raises `ValueError` if script inlining fails

**Version Tagging:**
- Raises `ValueError` if version format is invalid (not semver)
- Raises `RuntimeError` if git operations fail

**Release Branches:**
- Raises `RuntimeError` if git branch creation fails
- Logs errors but continues with other platforms

## Testing

Comprehensive test suite in `tests/test_platform_releases.py`:

```bash
# Run all platform release tests
pytest tests/test_platform_releases.py -v

# Run specific test class
pytest tests/test_platform_releases.py::PlatformReleasesTests -v

# Run with coverage
pytest tests/test_platform_releases.py --cov=pipery_tooling
```

**Test Coverage:**
- Script inlining for GitLab and Bitbucket
- Platform tag creation and listing
- Release branch generation
- Version extraction
- Error handling for missing scripts

## Integration with Existing Release Workflow

The platform-specific features integrate seamlessly with existing release commands:

1. **GitHub**: Traditional release process unchanged
   - Creates `releases/v${major}` branch
   - Uses composite action format

2. **GitLab/Bitbucket**: New platform-specific branches
   - Creates `release/platform-v${version}` branch
   - Inlines scripts for self-contained releases

3. **Version Tagging**: Enhanced with platform suffixes
   - Old tags: `v1.0.0`, `v1`, `latest`
   - New tags: `v1.0.0-gitlab`, `v1-gitlab`, `latest-gitlab`

## Best Practices

1. **Script Inlining**
   - Always validate pipeline files before pushing
   - Commit inlined changes to release branches separately

2. **Version Tags**
   - Never manually edit platform-specific tags
   - Always use `tag create-version` or `tag update-rolling`

3. **Release Branches**
   - Create release branches immediately before pushing
   - Use `--dry-run` to preview changes first

4. **Multi-Platform Releases**
   - Create all platform branches in single operation
   - Verify each platform branch independently

## Future Enhancements

Possible improvements for future versions:

- [ ] Support for GitHub Workflows script inlining
- [ ] Conditional script inlining based on markers in YAML
- [ ] Automatic platform detection from repository structure
- [ ] Rollback functionality for failed releases
- [ ] Release notes generation per platform
- [ ] Integration with platform-specific deployment tools
