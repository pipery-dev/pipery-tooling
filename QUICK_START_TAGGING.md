# Quick Start: Version Tagging

## Quick Examples

### Example 1: Release v1.2.3 to GitHub

```bash
cd /path/to/repo
COMMIT=$(git rev-parse HEAD)

pipery-actions tag --repo . create-version \
  --version 1.2.3 \
  --commit $COMMIT \
  --push
```

Results in tags:
- `v1.2.3` → points to HEAD
- `v1` → points to HEAD (rolling, updated)
- `v1.2` → points to HEAD (rolling, updated)
- `latest` → points to HEAD (rolling, updated)

### Example 2: Release v1.2.3 to Multiple Platforms

```bash
COMMIT=$(git rev-parse HEAD)

# GitHub
pipery-actions tag --repo . create-version \
  --version 1.2.3 \
  --commit $COMMIT \
  --push

# GitLab
pipery-actions tag --repo . create-version \
  --version 1.2.3 \
  --commit $COMMIT \
  --platform gitlab \
  --push

# Bitbucket
pipery-actions tag --repo . create-version \
  --version 1.2.3 \
  --commit $COMMIT \
  --platform bitbucket \
  --push
```

### Example 3: Tag Without Pushing (Dry Run)

```bash
pipery-actions tag --repo . create-version \
  --version 1.2.3 \
  --commit abc123def456
```

Verify the tags locally, then push later:

```bash
git push origin v1.2.3 v1 v1.2 latest
git push origin v1.2.3-gitlab v1-gitlab v1.2-gitlab latest-gitlab --force
```

### Example 4: List Current Tags

```bash
pipery-actions tag --repo . list --platform gitlab
```

Output shows tags organized by version series:
```
v1.2:
  v1.2-gitlab               abc123ab
  v1.2.3-gitlab             abc123ab
  v1.2.2-gitlab             def456de

v1.1:
  v1.1-gitlab               ghi789gi
  v1.1.4-gitlab             ghi789gi
```

### Example 5: Validate Tags

Check if all tags are valid:

```bash
pipery-actions tag --repo . validate --platform gitlab
```

Check a specific tag:

```bash
pipery-actions tag --repo . validate --tag v1.2.3-gitlab
```

### Example 6: Cleanup Invalid Tags

Remove tags that don't follow conventions:

```bash
pipery-actions tag --repo . cleanup \
  --remove-orphaned \
  --platform gitlab \
  --push
```

### Example 7: Update Rolling Tags for Existing Version

If you already have tags but want to update the rolling tags:

```bash
pipery-actions tag --repo . update-rolling \
  --version 1.2.3 \
  --commit abc123def456 \
  --platform gitlab \
  --push
```

This will:
- Update `v1-gitlab` if 1.2.3 > current v1-gitlab version
- Update `v1.2-gitlab` if 1.2.3 > current v1.2-gitlab version
- Update `latest-gitlab` if 1.2.3 >= current latest-gitlab version

### Example 8: Reconcile All Tags

Ensure all rolling tags point to the correct versions:

```bash
pipery-actions tag --repo . reconcile --platform gitlab --push
```

This scans all version tags and fixes any misaligned rolling tags.

## Understanding Rolling Tags

Rolling tags automatically update. Here's how it works:

**Initial release of v1.0.0:**
```
v1 → abc123 (v1.0.0)
v1.0 → abc123
latest → abc123
```

**Release v1.1.0 (at def456):**
```
v1 → def456 (updated! now points to v1.1.0)
v1.0 → abc123 (unchanged, still points to v1.0.0)
v1.1 → def456
latest → def456 (updated!)
```

**Release v1.1.2 (at ghi789):**
```
v1 → ghi789 (updated! now points to v1.1.2)
v1.0 → abc123 (unchanged)
v1.1 → ghi789 (updated! now points to v1.1.2)
latest → ghi789 (updated!)
```

If you later release v1.0.5 (at jkl012):
```
v1 → ghi789 (unchanged! v1.0.5 < v1.1.2)
v1.0 → jkl012 (updated! v1.0.5 > v1.0.0)
v1.1 → ghi789 (unchanged)
latest → ghi789 (unchanged!)
```

## Integration with Release Workflow

Use with the existing release command:

```bash
# Bump version and create tags
pipery-actions release --repo . \
  --bump minor \
  --commit \
  --create-tags \
  --push
```

This automatically creates:
- v1.1.0 (immutable)
- v1, v1.1 (rolling)
- latest (rolling)

## Troubleshooting

### Check current tag status

```bash
git tag -l | sort -V
```

### See what commit a tag points to

```bash
git rev-list -n 1 v1.2.3
```

### Compare tag commits

```bash
git rev-list -n 1 v1-gitlab    # v1 rolling tag commit
git rev-list -n 1 v1.2.3-gitlab  # v1.2.3 immutable tag commit
```

### Manually fix a tag

```bash
# Force update a rolling tag to a specific commit
git tag -f v1-gitlab abc123def456
git push origin v1-gitlab --force
```

## Common Patterns

### Pattern: Always Tag on Release

In your CI/CD release workflow:

```bash
#!/bin/bash
set -e

VERSION=$1
PLATFORM=${2:-""}
PUSH=${3:-false}

COMMIT=$(git rev-parse HEAD)

pipery-actions tag --repo . create-version \
  --version $VERSION \
  --commit $COMMIT \
  $([ -n "$PLATFORM" ] && echo "--platform $PLATFORM") \
  $([ "$PUSH" = "true" ] && echo "--push")
```

Usage:
```bash
./tag-release.sh 1.2.3           # Create tags, don't push
./tag-release.sh 1.2.3 gitlab true  # Create gitlab tags and push
```

### Pattern: Multi-Platform Release

```bash
#!/bin/bash
set -e

VERSION=$1
COMMIT=$(git rev-parse HEAD)

for platform in github gitlab bitbucket; do
  echo "Tagging for $platform..."
  
  if [ "$platform" = "github" ]; then
    pipery-actions tag --repo . create-version \
      --version $VERSION \
      --commit $COMMIT \
      --push
  else
    pipery-actions tag --repo . create-version \
      --version $VERSION \
      --commit $COMMIT \
      --platform $platform \
      --push
  fi
done

echo "Release v$VERSION complete!"
```

Usage:
```bash
./multi-platform-release.sh 1.2.3
```

### Pattern: Post-Release Validation

```bash
#!/bin/bash
set -e

VERSION=$1

# Validate all platforms
for platform in "" gitlab bitbucket; do
  if [ -z "$platform" ]; then
    echo "Validating GitHub tags..."
    pipery-actions tag --repo . validate
  else
    echo "Validating $platform tags..."
    pipery-actions tag --repo . validate --platform $platform
  fi
done

echo "All tags validated!"
```

## Architecture

```
version_parser.py
├── ParsedVersion (dataclass)
│   ├── major, minor, patch, platform
│   ├── version comparison (<, >, ==, etc)
│   └── tag name generation
└── VersionParser (static methods)
    ├── parse_tag(tag)
    ├── parse_version_string(version)
    ├── get_major_tag()
    ├── get_minor_tag()
    └── get_latest_tag()

rolling_tag_manager.py
└── TagManager
    ├── Git operations (create, update, delete, push tags)
    ├── create_version_tags() - create all tags for a version
    ├── update_rolling_tags() - update only rolling tags
    ├── get_latest_version_in_series() - find newest in series
    ├── reconcile_all_tags() - fix all rolling tags
    ├── validate_tag() - check tag validity
    ├── find_orphaned_tags() - invalid format tags
    └── find_duplicate_versions() - same version, different commits

commands.py
└── tag_command() and helpers
    ├── _tag_create_version()
    ├── _tag_update_rolling()
    ├── _tag_reconcile()
    ├── _tag_list()
    ├── _tag_validate()
    └── _tag_cleanup()

cli.py
└── build_parser()
    └── tag subcommand with 6 subactions
```

## Testing

Run the test suite:

```bash
# All tests
uv run pytest tests/ -v

# Just tagging tests
uv run pytest tests/test_version_tagging.py -v

# Specific test
uv run pytest tests/test_version_tagging.py::VersionParserTests::test_version_comparison_greater -v
```

## Reference

For detailed documentation, see [TAG_MANAGEMENT.md](TAG_MANAGEMENT.md)
