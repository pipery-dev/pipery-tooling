# Version Tagging and Rolling Tag Management

This document describes the sophisticated version tagging and rolling tag management system implemented in pipery-tooling.

## Overview

The tagging system provides intelligent semantic versioning with rolling tag updates. When you release v1.2.3, it automatically manages:

- **Immutable version tag**: `v1.2.3` (or `v1.2.3-gitlab` for platform-specific tags)
- **Major version tag**: `v1` (or `v1-gitlab`) - always points to the latest v1.x.x
- **Minor version tag**: `v1.2` (or `v1.2-gitlab`) - always points to the latest v1.2.x
- **Latest tag**: `latest` (or `latest-gitlab`) - always points to the highest version

## Concepts

### Tag Naming Conventions

Tags follow these patterns:

- **Semver**: `v1`, `v1.2`, `v1.2.3`
- **Platform-suffixed**: `v1-gitlab`, `v1.2-gitlab`, `v1.2.3-gitlab`
- **Latest**: `latest` or `latest-gitlab`

### Rolling Tags

Rolling tags automatically update to point to the newest version in their series:

```
Release v1.0.0:
  v1 → commit ABC
  v1.0 → commit ABC
  latest → commit ABC

Release v1.2.0:
  v1 → commit XYZ (updated!)
  v1.0 → commit ABC (unchanged, older)
  v1.2 → commit XYZ
  latest → commit XYZ (updated!)

Release v1.2.3:
  v1 → commit PQR (updated!)
  v1.2 → commit PQR (updated!)
  latest → commit PQR (updated!)
```

## CLI Commands

### Create All Tags for a Version

Create the full set of tags for a new release:

```bash
pipery-actions tag --repo . create-version \
  --version 1.2.3 \
  --commit abc123def456 \
  --platform gitlab \
  --push
```

This creates:
- `v1.2.3-gitlab` (immutable)
- `v1-gitlab` (rolling, updated)
- `v1.2-gitlab` (rolling, updated)
- `latest-gitlab` (rolling, updated)

### Update Rolling Tags Only

If tags already exist and you want to update only the rolling tags:

```bash
pipery-actions tag --repo . update-rolling \
  --version 1.2.3 \
  --commit abc123def456 \
  --platform gitlab \
  --push
```

This updates rolling tags only if the version is newer than what they currently point to.

### Reconcile All Tags

Reconcile all tags for a platform, ensuring rolling tags point to the latest in each series:

```bash
pipery-actions tag --repo . reconcile \
  --platform gitlab \
  --push
```

This scans all release tags and updates major/minor/latest tags to point to the latest version in each series.

### List Tags

List all tags grouped by version:

```bash
pipery-actions tag --repo . list --platform gitlab
```

Output:
```
latest:
  latest-gitlab              abc123ab
  v1-gitlab                 abc123ab

v1.2:
  v1.2-gitlab               abc123ab
  v1.2.3-gitlab             abc123ab

v1.0:
  v1.0.0-gitlab             def456de
```

### Validate Tags

Validate all tags or a specific tag:

```bash
pipery-actions tag --repo . validate --platform gitlab
```

Or validate a specific tag:

```bash
pipery-actions tag --repo . validate --tag v1.2.3-gitlab
```

### Cleanup Tags

Remove orphaned or duplicate tags:

```bash
pipery-actions tag --repo . cleanup \
  --remove-orphaned \
  --platform gitlab \
  --push
```

Options:
- `--remove-orphaned`: Remove tags that don't follow naming conventions
- `--remove-duplicates`: Remove duplicate version tags
- `--push`: Push deletions to remote

## Version Parser

The `VersionParser` class handles semantic version parsing and comparison.

### Parsing

```python
from pipery_tooling.version_parser import VersionParser

# Parse various formats
v1 = VersionParser.parse_tag("v1.2.3-gitlab")      # ParsedVersion
v2 = VersionParser.parse_tag("latest-gitlab")      # ParsedVersion
v3 = VersionParser.parse_version_string("1.2.3")   # ParsedVersion

# Extract components
assert v1.major == 1
assert v1.minor == 2
assert v1.patch == 3
assert v1.platform == "gitlab"
```

### Comparison

```python
v1 = ParsedVersion(major=1, minor=2, patch=3)
v2 = ParsedVersion(major=1, minor=2, patch=0)

assert v1 > v2      # Semantic comparison
assert v2 < v1
assert v1 == v1     # Equality ignores platform
```

### Tag Generation

```python
from pipery_tooling.version_parser import VersionParser, ParsedVersion

v = ParsedVersion(major=1, minor=2, patch=3, platform="gitlab")

major_tag = VersionParser.get_major_tag(v)      # "v1-gitlab"
minor_tag = VersionParser.get_minor_tag(v)      # "v1.2-gitlab"
latest_tag = VersionParser.get_latest_tag("gitlab")  # "latest-gitlab"
```

## Rolling Tag Manager

The `TagManager` class in `rolling_tag_manager.py` implements the tag management operations.

### Creating Tags

```python
from pipery_tooling.rolling_tag_manager import TagManager
from pathlib import Path

manager = TagManager(Path("/repo"))

# Create all tags for a version
tags = manager.create_version_tags(
    version_str="1.2.3",
    commit="abc123def456",
    platform="gitlab",
    push_to_remote=True
)

# Result: {"version": "v1.2.3-gitlab", "major": "v1-gitlab", ...}
```

### Updating Rolling Tags

```python
# Update rolling tags only if version is newer
updated = manager.update_rolling_tags(
    version_str="1.2.3",
    commit="abc123def456",
    platform="gitlab",
    push_to_remote=True
)

# Returns dict of updated tags (empty if no updates needed)
```

### Finding Latest Versions

```python
# Get latest version in v1.* series
latest_v1 = manager.get_latest_version_in_series(
    major=1,
    minor=None,
    platform="gitlab"
)
# ParsedVersion(major=1, minor=2, patch=3, platform="gitlab")

# Get latest in v1.2.* series
latest_v1_2 = manager.get_latest_version_in_series(
    major=1,
    minor=2,
    platform="gitlab"
)
# ParsedVersion(major=1, minor=2, patch=3, platform="gitlab")
```

### Validation and Cleanup

```python
# Validate a tag
errors = manager.validate_tag("v1.2.3-gitlab")
if errors:
    for error in errors:
        print(f"Validation error: {error}")

# Find orphaned tags
orphaned = manager.find_orphaned_tags()
# [(tag_name, parsed_version), ...]

# Find duplicate versions
duplicates = manager.find_duplicate_versions()
# {"1.2.3": ["v1.2.3-gitlab", "v1.2.3-github"], ...}
```

## Integration with Release Command

The version tagging system integrates with the existing `release` command. When releasing with tags:

```bash
pipery-actions release --repo . \
  --set-version 1.2.3 \
  --commit \
  --create-tags \
  --push
```

This will automatically create all appropriate version tags and rolling tags.

## Platform-Specific Tagging

For cross-platform deployments (e.g., releasing to both GitHub and GitLab):

### GitHub (no platform suffix)

```bash
pipery-actions tag --repo . create-version \
  --version 1.2.3 \
  --commit abc123 \
  --push
```

Creates: `v1.2.3`, `v1`, `v1.2`, `latest`

### GitLab

```bash
pipery-actions tag --repo . create-version \
  --version 1.2.3 \
  --commit abc123 \
  --platform gitlab \
  --push
```

Creates: `v1.2.3-gitlab`, `v1-gitlab`, `v1.2-gitlab`, `latest-gitlab`

### Bitbucket

```bash
pipery-actions tag --repo . create-version \
  --version 1.2.3 \
  --commit abc123 \
  --platform bitbucket \
  --push
```

Creates: `v1.2.3-bitbucket`, `v1-bitbucket`, `v1.2-bitbucket`, `latest-bitbucket`

## Reconciliation Workflow

For repositories with multiple releases and platforms:

```bash
# After syncing to multiple platforms
pipery-actions tag --repo . reconcile --platform gitlab --push
pipery-actions tag --repo . reconcile --platform bitbucket --push

# Or reconcile all at once
pipery-actions tag --repo . reconcile --push
```

This ensures all rolling tags (major, minor, latest) point to the correct newest versions.

## Error Handling

The system validates:

- **Tag format**: Ensures tags follow naming conventions
- **Version semantics**: Compares versions correctly (1.2.3 > 1.2.0)
- **Commit validity**: Verifies tags point to valid commits
- **Orphaned tags**: Identifies tags that don't match conventions
- **Duplicates**: Finds versions with multiple tags pointing to different commits

## Examples

### Scenario 1: Simple Release

Release v1.2.3 to GitHub only:

```bash
pipery-actions tag --repo . create-version \
  --version 1.2.3 \
  --commit $(git rev-parse HEAD) \
  --push
```

### Scenario 2: Multi-Platform Release

Release v1.2.3 to multiple platforms:

```bash
COMMIT=$(git rev-parse HEAD)

pipery-actions tag --repo . create-version \
  --version 1.2.3 \
  --commit $COMMIT \
  --push

pipery-actions tag --repo . create-version \
  --version 1.2.3 \
  --commit $COMMIT \
  --platform gitlab \
  --push

pipery-actions tag --repo . create-version \
  --version 1.2.3 \
  --commit $COMMIT \
  --platform bitbucket \
  --push
```

### Scenario 3: Fix and Update Tags

You released v1.2.3 but need to retroactively tag another platform:

```bash
# Find the commit that has v1.2.3
COMMIT=$(git rev-list -n 1 v1.2.3)

pipery-actions tag --repo . create-version \
  --version 1.2.3 \
  --commit $COMMIT \
  --platform gitlab \
  --push
```

### Scenario 4: Cleanup

Remove invalid or orphaned tags:

```bash
pipery-actions tag --repo . validate --platform gitlab
pipery-actions tag --repo . cleanup --remove-orphaned --platform gitlab --push
```

## Implementation Details

### Module: `version_parser.py`

Contains `ParsedVersion` and `VersionParser`:

- Parses tags into semantic version components
- Compares versions using semantic versioning rules
- Generates tag names for major/minor/latest
- Handles platform suffixes

### Module: `rolling_tag_manager.py`

Contains `TagManager`:

- Git operations (create, update, delete, push tags)
- Version series detection
- Rolling tag update logic
- Tag validation and cleanup
- Reconciliation across all versions

### Integration: `commands.py`

The `tag_command` function dispatches to:

- `_tag_create_version()` - Create all tags
- `_tag_update_rolling()` - Update rolling tags
- `_tag_reconcile()` - Reconcile all tags
- `_tag_list()` - List tags
- `_tag_validate()` - Validate tags
- `_tag_cleanup()` - Remove invalid tags

## Testing

Run the comprehensive test suite:

```bash
uv run pytest tests/test_version_tagging.py -v
```

Tests cover:

- Version parsing (all formats and edge cases)
- Version comparison (semantic ordering)
- Tag creation and updates
- Rolling tag logic
- Validation and cleanup
- Multi-platform scenarios
