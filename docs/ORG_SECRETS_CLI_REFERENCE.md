# GitHub CLI Commands for Organization Secrets

Quick reference for managing organization-level secrets in the `pipery` GitHub organization.

## Add Secrets

### Method 1: Using gh CLI directly

```bash
# Add GitLab token
gh secret set GITLAB_TOKEN --org pipery --body "glpat-xxxxxxxxxxxxx"

# Add Bitbucket token
gh secret set BITBUCKET_TOKEN --org pipery --body "xxxxxxxxxxxxxxxx"
```

### Method 2: Using the setup script

```bash
# Interactive mode (prompts for each token)
./scripts/setup-org-secrets.sh

# With arguments
./scripts/setup-org-secrets.sh \
  --gitlab-token "glpat-xxxxxxxxxxxxx" \
  --bitbucket-token "xxxxxxxxxxxxxxxx"

# Dry-run (preview without making changes)
./scripts/setup-org-secrets.sh --dry-run
```

## View/Manage Secrets

### List all organization secrets

```bash
gh secret list --org pipery
```

Output shows secret name and last updated date (not the value).

### View metadata for a specific secret

```bash
gh secret view GITLAB_TOKEN --org pipery
gh secret view BITBUCKET_TOKEN --org pipery
```

### Update a secret

```bash
gh secret set GITLAB_TOKEN --org pipery --body "new_glpat_value"
gh secret set BITBUCKET_TOKEN --org pipery --body "new_password"
```

### Delete a secret

```bash
gh secret delete GITLAB_TOKEN --org pipery
gh secret delete BITBUCKET_TOKEN --org pipery
```

Confirmation will be prompted.

## Secret Details

| Secret Name | Type | Expiration | Added Date | Purpose |
|-------------|------|------------|------------|---------|
| GITLAB_TOKEN | GitLab PAT | 2027-05-07 | 2026-05-07 | GitLab API access for repo sync and releases |
| BITBUCKET_TOKEN | Bitbucket App Password | 2027-05-07 | 2026-05-07 | Bitbucket API access for repo sync and releases |

## Using Secrets in Workflows

```yaml
jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - name: Sync and Release
        env:
          GITLAB_TOKEN: ${{ secrets.GITLAB_TOKEN }}
          BITBUCKET_TOKEN: ${{ secrets.BITBUCKET_TOKEN }}
        run: |
          pipery-actions release --repo . --bump patch --push
```

## Batch Setup from Environment Variables

If you have tokens in your shell environment:

```bash
# Export tokens
export GITLAB_TOKEN="glpat-xxxxxxxxxxxxx"
export BITBUCKET_TOKEN="xxxxxxxxxxxxxxxx"

# Set both secrets
gh secret set GITLAB_TOKEN --org pipery --body "$GITLAB_TOKEN"
gh secret set BITBUCKET_TOKEN --org pipery --body "$BITBUCKET_TOKEN"
```

## Pre-flight Checks

```bash
# Verify gh is installed and authenticated
gh auth status

# Verify access to pipery organization
gh org list | grep pipery

# Verify GitHub CLI version
gh --version
```

## Troubleshooting

### Error: "Invalid authentication credentials"

```bash
# Re-authenticate
gh auth logout
gh auth login
```

### Error: "Organization not found"

Ensure you have access to the organization and the name is correct:

```bash
# List your organizations
gh org list

# The organization must be "pipery" (case-sensitive)
```

### Error: "You do not have permission to perform this operation"

You need to be an organization member with sufficient permissions:

```bash
# Check current organization role
gh api orgs/pipery/members --query '[].[]' -H "Accept: application/vnd.github.v3+json"
```

### Verify secrets were set

```bash
# List secrets
gh secret list --org pipery

# You should see:
# GITLAB_TOKEN     Updated 2026-05-07T12:00:00Z
# BITBUCKET_TOKEN  Updated 2026-05-07T12:00:00Z
```

## Related Documentation

- Full documentation: [GITHUB_ORG_SECRETS.md](GITHUB_ORG_SECRETS.md)
- Cross-platform sync: [../src/pipery_tooling/cross_platform_sync.py](../src/pipery_tooling/cross_platform_sync.py)
- Release workflow: [../.github/workflows/pipery-release.yml](../.github/workflows/pipery-release.yml)
- GitHub documentation: https://docs.github.com/en/actions/security-guides/using-secrets-in-github-actions
- GitLab tokens: https://docs.gitlab.com/ee/user/profile/personal_access_tokens.html
- Bitbucket app passwords: https://support.atlassian.com/bitbucket-cloud/docs/app-passwords/
