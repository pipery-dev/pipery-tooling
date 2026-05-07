# Cross-Platform Repository Synchronization

The pipery-tooling now supports synchronizing repositories across multiple platforms: GitHub, GitLab, and Bitbucket. This enables maintaining synchronized mirrors of Pipery repositories on alternative platforms.

## Features

### Repository Synchronization

- **Multi-platform support**: Sync to GitLab, Bitbucket, or both
- **Selective syncing**: Sync all repos or specific repositories
- **File filtering**: Automatically excludes GitHub-specific files and configuration
- **Platform-specific config**: Preserves `.gitlab-ci.yml` and `bitbucket-pipelines.yml`
- **Error handling**: Graceful failure handling - one repo failure doesn't stop others

### Tag Management

- **Automatic tag detection**: Finds release branches and creates corresponding tags
- **Rolling version tags**: Maintains major, minor, and latest tags
- **Version parsing**: Extracts versions from release branch names (e.g., `release/v1.2.3`)

## Installation

The sync functionality requires the `requests` library, which is included in the dependencies:

```bash
uv sync  # Install all dependencies
```

## Usage

### Sync Repositories to GitLab

Sync all default Pipery repos to GitLab:

```bash
GITLAB_TOKEN=your-token pipery-actions sync --platform gitlab
```

Sync specific repositories:

```bash
GITLAB_TOKEN=your-token pipery-actions sync \
  --platform gitlab \
  --repos pipery-dev/pipery-python-ci,pipery-dev/pipery-npm-ci
```

### Sync Repositories to Bitbucket

```bash
BITBUCKET_TOKEN=your-token \
BITBUCKET_WORKSPACE=your-workspace \
pipery-actions sync --platform bitbucket
```

### Sync to All Platforms

```bash
GITLAB_TOKEN=gitlab-token \
BITBUCKET_TOKEN=bitbucket-token \
BITBUCKET_WORKSPACE=workspace \
pipery-actions sync --platform all
```

### Save Sync Report

```bash
pipery-actions sync \
  --platform gitlab \
  --report sync-report.json \
  --gitlab-token $GITLAB_TOKEN
```

## Tag Management

### Create Missing Tags

Create version tags based on release branches:

```bash
GITLAB_TOKEN=your-token pipery-actions create-tags --platform gitlab
```

This command:
1. Finds all release branches (e.g., `release/v1.2.3`)
2. Extracts the version number
3. Creates the following tags:
   - `v1.2.3` - Exact version tag
   - `v1-gitlab` - Major version tag (rolling)
   - `v1.2-gitlab` - Minor version tag (rolling)
   - `latest-gitlab` - Latest version tag (rolling)

### Create Tags for Specific Repositories

```bash
GITLAB_TOKEN=your-token pipery-actions create-tags \
  --platform gitlab \
  --repos pipery-python-ci,pipery-npm-ci
```

## Configuration

### Environment Variables

The sync tools support the following environment variables:

- `GITLAB_TOKEN`: GitLab personal access token (with API access)
- `BITBUCKET_TOKEN`: Bitbucket app password
- `BITBUCKET_WORKSPACE`: Bitbucket workspace name
- `GITHUB_TOKEN`: GitHub token (optional, for authenticated cloning)

### Command-line Options

#### sync command

```
--platform {gitlab,bitbucket,all}    Target platform(s). Default: all
--repos REPOS                         Comma-separated list of repos (owner/repo)
--gitlab-token TOKEN                 GitLab authentication token
--bitbucket-token TOKEN              Bitbucket authentication token
--bitbucket-workspace WORKSPACE      Bitbucket workspace
--report FILE                        Save sync report to JSON file
-v, --verbose                        Enable verbose logging
```

#### create-tags command

```
--platform {gitlab,bitbucket,all}    Target platform(s). Default: all
--repos REPOS                         Comma-separated list of repos
--gitlab-token TOKEN                 GitLab authentication token
--bitbucket-token TOKEN              Bitbucket authentication token
--bitbucket-workspace WORKSPACE      Bitbucket workspace
--report FILE                        Save tag report to JSON file
-v, --verbose                        Enable verbose logging
```

## File Synchronization

### Excluded from Sync

The following files and directories are excluded from synchronization:

- `.git` - Git metadata
- `.github` - GitHub-specific files
- `action.yml` - GitHub Actions metadata
- `.releases`, `.tags` - Release/tag metadata
- `.gitlab-ci.yml` - Kept as platform-specific config
- `bitbucket-pipelines.yml` - Kept as platform-specific config

### Included in Sync

All other files are synchronized, including:

- Source code
- README.md
- LICENSE
- Test files
- Documentation

## Default Repositories

When no `--repos` parameter is specified, the following 14 repositories are synced:

**CI Repositories:**
- pipery-cpp-ci
- pipery-golang-ci
- pipery-java-ci
- pipery-npm-ci
- pipery-python-ci
- pipery-rust-ci
- pipery-docker-ci
- pipery-terraform-ci

**CD Repositories:**
- pipery-ansible-cd
- pipery-argocd-cd
- pipery-cloudrun-cd
- pipery-docker-cd
- pipery-helm-cd
- pipery-terraform-cd

## Examples

### Complete Workflow: Sync and Create Tags

```bash
#!/bin/bash

# Set up credentials
export GITLAB_TOKEN="glpat-your-token"
export BITBUCKET_TOKEN="your-app-password"
export BITBUCKET_WORKSPACE="your-workspace"

# Sync all repos to both platforms
pipery-actions sync --platform all --report sync-report.json

# Create tags on both platforms
pipery-actions create-tags --platform all --report tags-report.json

# Check reports
cat sync-report.json
cat tags-report.json
```

### Scheduled Synchronization

Use system scheduling (cron, GitHub Actions, etc.) to run syncs periodically:

```bash
# Run daily sync at 2 AM
0 2 * * * cd /path/to/pipery-tooling && \
  GITLAB_TOKEN=$GITLAB_TOKEN \
  BITBUCKET_TOKEN=$BITBUCKET_TOKEN \
  BITBUCKET_WORKSPACE=$WORKSPACE \
  uv run pipery-actions sync --platform all >> /var/log/pipery-sync.log 2>&1
```

## Troubleshooting

### Authentication Errors

**Error**: `GitLab token not provided`

**Solution**: Ensure `GITLAB_TOKEN` environment variable is set or use `--gitlab-token` flag.

**Error**: `Bitbucket token not provided`

**Solution**: Ensure `BITBUCKET_TOKEN` and `BITBUCKET_WORKSPACE` are set.

### Repository Not Found

**Error**: `Project ... not found on GitLab`

**Solution**: The repository will be automatically created if it doesn't exist. Ensure your token has permission to create projects.

### Tag Already Exists

Tag creation will skip existing tags. To update rolling tags, manually delete and re-run the command, or use the rolling tag manager.

## API Details

### GitLabAPI

Provides GitLab API v4 integration:
- `get_project(project_id)` - Fetch project details
- `create_project(name, description, visibility, group_id)` - Create new project
- `get_project_url(project_id)` - Get clone URL
- `push_branch(project_id, branch_name, local_repo_path)` - Push branch
- `create_tag(project_id, tag_name, ref, message)` - Create tag
- `list_branches(project_id)` - List all branches

### BitbucketAPI

Provides Bitbucket Cloud API integration:
- `get_repository(repo_slug)` - Fetch repository details
- `create_repository(repo_slug, description, is_private)` - Create new repository
- `get_repository_url(repo_slug)` - Get clone URL
- `push_branch(repo_slug, branch_name, local_repo_path)` - Push branch
- `create_tag(repo_slug, tag_name, commit_hash)` - Create tag
- `list_branches(repo_slug)` - List all branches

### RepositorySynchronizer

Main synchronization orchestrator:
- `sync_to_platform(github_repo, platform, auth_token, platform_config)` - Sync single repo
- `sync_all_platforms(repos, platforms, gitlab_token, bitbucket_token, bitbucket_workspace)` - Sync multiple repos

### TagManager

Tag management and versioning:
- `create_missing_tags_gitlab(project_id)` - Create tags on GitLab
- `create_missing_tags_bitbucket(repo_slug)` - Create tags on Bitbucket

## Testing

Run the test suite:

```bash
uv run pytest tests/test_cross_platform_sync.py tests/test_tag_manager.py -v
```

## Contributing

When adding new sync functionality:

1. Add support for the platform's API in the appropriate API class
2. Implement platform-specific sync logic in `RepositorySynchronizer`
3. Add comprehensive tests in `tests/test_cross_platform_sync.py`
4. Update this documentation with examples and troubleshooting
