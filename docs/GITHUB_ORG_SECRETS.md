# GitHub Organization Secrets for Cross-Platform CI/CD

This document describes the GitHub organization-level secrets used for cross-platform repository synchronization and releases across GitHub, GitLab, and Bitbucket.

## Secrets Configuration

### Overview

Organization-level secrets are centrally managed and can be referenced by any repository within the `pipery` GitHub organization. These secrets enable cross-platform CI/CD workflows without storing sensitive credentials in individual repositories.

### Secret Details

#### 1. GITLAB_TOKEN

**Purpose**: GitLab personal access token for cross-platform repository synchronization and release tag creation

**Type**: Personal Access Token (PAT)

**Scope**: GitLab namespace/organization operations
- Repository creation
- Tag creation
- Branch management
- File updates via git push

**Expiration**: May 7, 2027

**Added via GitHub CLI**:
```bash
gh secret set GITLAB_TOKEN --org pipery --body "glpat-xxxxxxxxxxxxx"
```

**Referenced in**:
- `pipery-tooling` release workflows
- Cross-platform sync operations
- GitLab repository mirroring

---

#### 2. BITBUCKET_TOKEN

**Purpose**: Bitbucket app password for cross-platform repository synchronization and release tag creation

**Type**: App Password (Bitbucket)

**Scope**: Bitbucket workspace operations
- Repository creation
- Tag creation
- Branch management
- File updates via git push

**Expiration**: May 7, 2027

**Added via GitHub CLI**:
```bash
gh secret set BITBUCKET_TOKEN --org pipery --body "xxxxxxxxxxxxxxxx"
```

**Referenced in**:
- `pipery-tooling` release workflows
- Cross-platform sync operations
- Bitbucket repository mirroring

---

## Usage in Workflows

### GitHub Actions Workflow Pattern

Organization secrets are referenced in GitHub Actions workflows using the standard secrets context:

```yaml
name: Release

on:
  workflow_dispatch:
    inputs:
      bump:
        description: Semver bump kind
        required: true

permissions:
  contents: write

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      
      - name: Install pipery-tooling
        run: pip install git+https://github.com/pipery-dev/pipery-tooling.git
      
      - name: Configure credentials
        env:
          GITLAB_TOKEN: ${{ secrets.GITLAB_TOKEN }}
          BITBUCKET_TOKEN: ${{ secrets.BITBUCKET_TOKEN }}
        run: |
          echo "Credentials configured for cross-platform sync"
      
      - name: Release with cross-platform sync
        env:
          GITLAB_TOKEN: ${{ secrets.GITLAB_TOKEN }}
          BITBUCKET_TOKEN: ${{ secrets.BITBUCKET_TOKEN }}
        run: pipery-actions release --repo . --bump ${{ inputs.bump }} --push
```

### Environment Variable Export

Secrets are exported as environment variables in bash scripts:

```bash
#!/bin/bash
set -euo pipefail

# Tokens are available as environment variables from GitHub Actions
GITLAB_TOKEN="${GITLAB_TOKEN:-}"
BITBUCKET_TOKEN="${BITBUCKET_TOKEN:-}"

if [ -z "$GITLAB_TOKEN" ]; then
    echo "ERROR: GITLAB_TOKEN not set"
    exit 1
fi

if [ -z "$BITBUCKET_TOKEN" ]; then
    echo "ERROR: BITBUCKET_TOKEN not set"
    exit 1
fi

# Use tokens in git operations
git push https://oauth2:${GITLAB_TOKEN}@gitlab.com/pipery-dev/repo.git main
```

---

## Workflows Using These Secrets

### 1. pipery-tooling Release Workflow

**File**: `.github/workflows/pipery-release.yml`

**Trigger**: Called from individual repository release workflows

**Used for**:
- Creating releases across multiple platforms
- Synchronizing tags to GitLab and Bitbucket
- Pushing commits to remote repositories

**Environment Variables Passed**:
```yaml
env:
  GITLAB_TOKEN: ${{ secrets.GITLAB_TOKEN }}
  BITBUCKET_TOKEN: ${{ secrets.BITBUCKET_TOKEN }}
```

### 2. Cross-Platform Sync Operations

**Triggered by**: `pipery-actions sync` command

**Used for**:
- Syncing repositories from GitHub to GitLab
- Syncing repositories from GitHub to Bitbucket
- Creating matching projects on target platforms
- Pushing branches and tags to alternative platforms

---

## Token Lifecycle & Security

### Expiration Schedule

| Token | Expires | Days Until Expiration (as of 2026-05-07) |
|-------|---------|-------------------------------------------|
| GITLAB_TOKEN | 2027-05-07 | 365 |
| BITBUCKET_TOKEN | 2027-05-07 | 365 |

### Rotation Procedure

Before token expiration:

1. **Generate new tokens** on GitLab and Bitbucket
2. **Update org secrets** using GitHub CLI:
   ```bash
   gh secret set GITLAB_TOKEN --org pipery --body "new_token_value"
   gh secret set BITBUCKET_TOKEN --org pipery --body "new_token_value"
   ```
3. **Verify** tokens work in a test workflow run
4. **Document** the rotation in this file
5. **Revoke old tokens** on GitLab/Bitbucket after verification

### Security Best Practices

- **Never commit credentials** to repositories
- **Use org-level secrets** rather than repo-level where possible
- **Minimize token scope** to only required permissions
- **Rotate tokens** well before expiration
- **Monitor token usage** through GitLab/Bitbucket audit logs
- **Restrict access** to organization secret management (GitHub)

---

## Affected Repositories

Workflows in these repositories reference the organization secrets:

- `pipery-tooling` — Cross-platform sync and release operations
- `pipery-cpp-ci`
- `pipery-golang-ci`
- `pipery-java-ci`
- `pipery-npm-ci`
- `pipery-python-ci`
- `pipery-rust-ci`
- `pipery-docker-ci`
- `pipery-terraform-ci`
- All deployment repositories (ansible-cd, argocd-cd, cloudrun-cd, docker-cd, helm-cd, terraform-cd)

---

## Implementation in pipery-tooling

### Python Module: `cross_platform_sync.py`

The `RepositorySynchronizer` class automatically reads tokens from environment variables:

```python
class GitLabAPI:
    def __init__(self, base_url: str = "https://gitlab.com", token: str | None = None):
        self.token = token or os.getenv("GITLAB_TOKEN")
        if not self.token:
            raise ValueError("GitLab token not provided...")

class BitbucketAPI:
    def __init__(self, workspace: str, token: str | None = None):
        self.token = token or os.getenv("BITBUCKET_TOKEN")
        if not self.token:
            raise ValueError("Bitbucket token not provided...")
```

### Commands That Use Secrets

#### Sync Command
```bash
pipery-actions sync --repos pipery-python-ci --platforms gitlab,bitbucket
```

Requirements:
- `GITLAB_TOKEN` environment variable set
- `BITBUCKET_TOKEN` environment variable set
- `BITBUCKET_WORKSPACE` environment variable set (for Bitbucket)

#### Release Command
```bash
pipery-actions release --repo . --bump patch --push
```

When executed in a GitHub Actions workflow with org secrets configured, automatically syncs releases across platforms.

---

## GitHub CLI Commands Reference

### List Organization Secrets

```bash
gh secret list --org pipery
```

### View Secret Details (metadata only)

```bash
gh secret view GITLAB_TOKEN --org pipery
```

### Update/Replace a Secret

```bash
gh secret set GITLAB_TOKEN --org pipery --body "new_token_value"
gh secret set BITBUCKET_TOKEN --org pipery --body "new_token_value"
```

### Remove a Secret

```bash
gh secret delete GITLAB_TOKEN --org pipery
gh secret delete BITBUCKET_TOKEN --org pipery
```

### Set Multiple Secrets from a File

```bash
# Create a .env file with TOKEN=value pairs
cat << EOF > secrets.env
GITLAB_TOKEN=glpat-xxxxxxxxxxxxx
BITBUCKET_TOKEN=xxxxxxxxxxxxxxxx
EOF

# Set each secret (parse the file)
while IFS='=' read -r key value; do
    gh secret set "$key" --org pipery --body "$value"
done < secrets.env

# Clean up
rm secrets.env
```

---

## Troubleshooting

### Issue: "GITLAB_TOKEN not provided"

**Solution**: Ensure the secret is set and accessible:
```bash
gh secret list --org pipery | grep GITLAB
```

### Issue: "401 Unauthorized" on GitLab API calls

**Possible causes**:
- Token is expired (check expiration date)
- Token has insufficient scope
- Token has been revoked on GitLab

**Fix**: Generate a new token and update the secret:
```bash
gh secret set GITLAB_TOKEN --org pipery --body "new_token"
```

### Issue: Authentication fails for Bitbucket

**Possible causes**:
- App password is incorrect or revoked
- Workspace name is wrong
- Bitbucket account permissions changed

**Fix**: Verify credentials and regenerate app password if needed:
```bash
gh secret set BITBUCKET_TOKEN --org pipery --body "new_app_password"
```

---

## Related Documentation

- [Cross-Platform Sync Implementation](../src/pipery_tooling/cross_platform_sync.py)
- [Release Workflow](../.github/workflows/pipery-release.yml)
- [Tag Management](../TAG_MANAGEMENT.md)
- [GitHub Secrets Documentation](https://docs.github.com/en/actions/security-guides/using-secrets-in-github-actions)
- [GitLab Personal Access Tokens](https://docs.gitlab.com/ee/user/profile/personal_access_tokens.html)
- [Bitbucket App Passwords](https://support.atlassian.com/bitbucket-cloud/docs/app-passwords/)

---

## Last Updated

- 2026-05-07: Initial documentation
- Token Expiration Dates: May 7, 2027
