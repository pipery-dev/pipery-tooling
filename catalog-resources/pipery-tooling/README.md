# Pipery Cross-Platform Release Component

Reusable GitLab CI/CD component for publishing releases across GitHub, GitLab, and Bitbucket simultaneously with platform-optimized content.

## Overview

This component automates the release process for projects distributed across multiple platforms:

- **GitHub** - Primary release source with full feature set
- **GitLab** - GitLab-optimized release with excluded GitHub-specific files
- **Bitbucket** - Bitbucket-optimized release with excluded platform-mismatched files

The component creates platform-specific release branches and tags, ensuring each platform receives optimized content tailored to its CI/CD system.

## Features

✓ **Platform-Specific Release Branches**
  - `release/github-{tag}`: Contains all files (GitHub Actions config)
  - `release/gitlab-{tag}`: GitLab CI-optimized (excludes action.yml, bitbucket-pipelines.yml)
  - `release/bitbucket-{tag}`: Bitbucket-optimized (excludes action.yml, .gitlab-ci.template.yml)

✓ **Cross-Platform Synchronization**
  - Syncs all branches to all platforms (GitHub, GitLab, Bitbucket)
  - Creates platform-specific tags pointing to respective release branches
  - Tags only pushed to relevant platforms (not shared)

✓ **Native Release Creation**
  - GitHub: Native GitHub Release via gh CLI
  - GitLab: GitLab Release API with full metadata
  - Bitbucket: Release tag (no native API) with release branch marker

✓ **Comprehensive Logging**
  - Structured release pipeline execution
  - Platform sync status reporting
  - Release URL generation

## Quick Start

### 1. In your repository's `.gitlab-ci.yml`:

```yaml
include:
  - component: $CI_SERVER_FQDN/pipery-dev/pipery-tooling/catalog-resources/pipery-tooling@main

variables:
  REPO_NAME: "your-repo-name"
  GITHUB_TOKEN: $CI_JOB_TOKEN
  GITLAB_TOKEN: $GITLAB_PERSONAL_TOKEN
  SSH_ID: $SSH_PRIVATE_KEY
```

### 2. Configure Protected Variables in GitLab:

Go to **Settings > CI/CD > Variables** and add:

- `GITHUB_TOKEN` - GitHub Personal Access Token with repo + releases scope
- `GITLAB_TOKEN` - GitLab Personal Access Token with `api`, `read_repository`, `write_repository`, `Release:Create` scopes
- `SSH_ID` - SSH private key (ed25519) with push access to GitHub, GitLab, Bitbucket

### 3. Trigger the Pipeline:

Push a version tag matching the pattern `v*.*.*`:

```bash
git tag v1.0.0
git push origin v1.0.0
```

## Configuration

### Required Variables

| Variable | Description | Example |
| --- | --- | --- |
| `REPO_NAME` | Repository name (bare slug) | `pipery-npm-ci` |
| `GITHUB_TOKEN` | GitHub authentication | `ghp_xxxx...` |
| `SSH_ID` | SSH private key for Git operations | (SSH key content) |

### Optional Variables

| Variable | Description | Default |
| --- | --- | --- |
| `GITLAB_TOKEN` | GitLab auth for release creation | (empty) |

### What Gets Released

**GitHub:**
- v1.0.0 tag (on release/github-v1.0.0)
- GitHub Release with auto-generated notes
- All CI/CD configs (action.yml, .gitlab-ci.template.yml, bitbucket-pipelines.yml)

**GitLab:**
- v1.0.0 tag (on release/gitlab-v1.0.0)
- GitLab Release with structured description
- GitLab-specific CI config (.gitlab-ci.template.yml only)
- Excludes: action.yml, bitbucket-pipelines.yml

**Bitbucket:**
- v1.0.0 tag (on release/bitbucket-v1.0.0)
- Release branch marker (releases/v1.0.0)
- Bitbucket-specific CI config (bitbucket-pipelines.yml only)
- Excludes: action.yml, .gitlab-ci.template.yml

## Pipeline Stages

### 1. **Prepare Stage**
   - Install Pipery Tooling
   - Configure SSH for all platforms
   - Setup Git configuration
   - Capture tag information

### 2. **Sync Stage**
   - Create platform-specific release branches
   - Sync all branches to GitLab
   - Sync all branches to Bitbucket
   - Create platform-specific tags

### 3. **Release Stage**
   - Create GitHub Release
   - Create GitLab Release (if token provided)
   - Note: Bitbucket uses tag + release branch (no API)

### 4. **Summary Stage**
   - Display release summary
   - List created branches and tags

## Platform-Specific Configuration

### GitLab Token Scopes

For GitLab release creation, ensure your token has these **granular scopes**:
- `api` - Full API access
- `read_repository` - Read repository data
- `write_repository` - Write to repository
- `Release: Create` - Create releases (required!)

Without `Release: Create` scope, the release step will fail with "insufficient_granular_scope" error.

### SSH Key Requirements

The SSH key must have push access to:
- GitHub (github.com)
- GitLab (gitlab.com)
- Bitbucket (bitbucket.org)

Use ed25519 keys for better security:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/pipery-sync -N ""
```

## Output Artifacts

### Release Branches (created on all platforms)

```
release/github-v1.0.0/     # GitHub-optimized (all files)
  ├── action.yml           # ✓
  ├── .gitlab-ci.template.yml
  └── bitbucket-pipelines.yml

release/gitlab-v1.0.0/     # GitLab-optimized
  ├── .gitlab-ci.template.yml  # ✓
  └── [no action.yml]
  └── [no bitbucket-pipelines.yml]

release/bitbucket-v1.0.0/  # Bitbucket-optimized
  ├── bitbucket-pipelines.yml  # ✓
  └── [no action.yml]
  └── [no .gitlab-ci.template.yml]
```

### Tags (platform-specific)

- GitHub: `v1.0.0` → points to release/github-v1.0.0 tip
- GitLab: `v1.0.0` → points to release/gitlab-v1.0.0 tip
- Bitbucket: `v1.0.0` → points to release/bitbucket-v1.0.0 tip

### Release Objects

- GitHub Release with generated notes
- GitLab Release with structured description
- Bitbucket: Release tag + releases/v1.0.0 branch

## Monitoring & Debugging

### Check Pipeline Status

View the GitLab CI/CD pipeline to see:
- `prepare` stage - Setup and SSH configuration
- `sync` stage - Cross-platform branch and tag creation
- `release` stage - Release creation on each platform
- `summary` stage - Final release summary

### View Release Results

1. **GitHub**: [github.com/pipery-dev/YOUR-REPO/releases](https://github.com)
2. **GitLab**: [gitlab.com/pipery-dev/YOUR-REPO/-/releases](https://gitlab.com)
3. **Bitbucket**: [bitbucket.org/pipery-dev/YOUR-REPO/src](https://bitbucket.org) (check tags + releases/v*.*. * branches)

### Common Issues

**Error: "insufficient_granular_scope"**
- Solution: Ensure GitLab token has `Release: Create` scope

**Error: "Cannot push to GitLab/Bitbucket"**
- Solution: Verify SSH_ID key has push access to all platforms

**No GitHub release created**
- Solution: GitHub release requires GitHub Actions; this component handles sync and GitLab release only

## Examples

### Example 1: Release with GitLab

```yaml
include:
  - component: $CI_SERVER_FQDN/pipery-dev/pipery-tooling/catalog-resources/pipery-tooling@main

variables:
  REPO_NAME: "pipery-npm-ci"
  GITHUB_TOKEN: $GITHUB_PERSONAL_TOKEN
  GITLAB_TOKEN: $GITLAB_PERSONAL_TOKEN
  SSH_ID: $SSH_PRIVATE_KEY_ED25519
```

### Example 2: Sync-Only (no GitLab release)

```yaml
include:
  - component: $CI_SERVER_FQDN/pipery-dev/pipery-tooling/catalog-resources/pipery-tooling@main

variables:
  REPO_NAME: "my-repo"
  GITHUB_TOKEN: $GITHUB_PERSONAL_TOKEN
  SSH_ID: $SSH_PRIVATE_KEY
  # GITLAB_TOKEN not set → skips GitLab release creation
```

## About Pipery

[**Pipery**](https://pipery.dev) is an open-source CI/CD observability platform that provides structured logging and monitoring for your pipelines.

- Website: [pipery.dev](https://pipery.dev)
- Documentation: [docs.pipery.dev](https://pipery.dev)
- GitHub: [github.com/pipery-dev](https://github.com/pipery-dev)
- Dashboard: [github.com/pipery-dev/pipery-dashboard](https://github.com/pipery-dev/pipery-dashboard)

## Support

For issues or questions:
- [Open an issue on GitHub](https://github.com/pipery-dev/pipery-tooling/issues)
- Check the [Pipery documentation](https://pipery.dev)
- Review [example configurations](https://github.com/pipery-dev)
