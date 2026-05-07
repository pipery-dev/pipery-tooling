# Integrating Organization Secrets into Workflows

Guide for integrating GitHub organization secrets (`GITLAB_TOKEN` and `BITBUCKET_TOKEN`) into GitHub Actions workflows.

## Overview

Organization-level secrets are:
- Centrally managed at the GitHub organization level
- Accessible to all repositories in the organization
- Secure (values never logged or displayed)
- Referenced using `${{ secrets.SECRET_NAME }}` syntax

## Basic Integration Pattern

### 1. Minimal Integration

For workflows that simply need the tokens available:

```yaml
name: Release

on:
  workflow_dispatch:
    inputs:
      bump:
        description: Version bump (patch, minor, major)
        required: true
        type: choice
        options: [patch, minor, major]

permissions:
  contents: write

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      
      - name: Install pipery-tooling
        run: pip install git+https://github.com/pipery-dev/pipery-tooling.git
      
      - name: Configure Git
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
      
      - name: Release
        env:
          GITLAB_TOKEN: ${{ secrets.GITLAB_TOKEN }}
          BITBUCKET_TOKEN: ${{ secrets.BITBUCKET_TOKEN }}
        run: pipery-actions release --repo . --bump ${{ inputs.bump }} --push
```

### 2. With Conditional Platform Logic

For workflows that sync to specific platforms:

```yaml
jobs:
  sync:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        platform: [gitlab, bitbucket]
    
    steps:
      - uses: actions/checkout@v4
      
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      
      - name: Install pipery-tooling
        run: pip install git+https://github.com/pipery-dev/pipery-tooling.git
      
      - name: Sync to GitLab
        if: matrix.platform == 'gitlab'
        env:
          GITLAB_TOKEN: ${{ secrets.GITLAB_TOKEN }}
        run: pipery-actions sync --repos my-repo --platforms gitlab
      
      - name: Sync to Bitbucket
        if: matrix.platform == 'bitbucket'
        env:
          BITBUCKET_TOKEN: ${{ secrets.BITBUCKET_TOKEN }}
          BITBUCKET_WORKSPACE: pipery
        run: pipery-actions sync --repos my-repo --platforms bitbucket
```

## Advanced Integration Patterns

### 3. Multi-Repository Sync with Matrix

For syncing multiple repositories to multiple platforms:

```yaml
name: Multi-Platform Sync

on:
  schedule:
    # Run daily at 2 AM UTC
    - cron: '0 2 * * *'
  workflow_dispatch:

jobs:
  sync:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        repo: [pipery-python-ci, pipery-rust-ci, pipery-golang-ci]
        platform: [gitlab, bitbucket]
      fail-fast: false  # Continue even if one fails
    
    steps:
      - uses: actions/checkout@v4
      
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      
      - name: Install pipery-tooling
        run: pip install git+https://github.com/pipery-dev/pipery-tooling.git
      
      - name: Sync ${{ matrix.repo }} to ${{ matrix.platform }}
        env:
          GITLAB_TOKEN: ${{ secrets.GITLAB_TOKEN }}
          BITBUCKET_TOKEN: ${{ secrets.BITBUCKET_TOKEN }}
          BITBUCKET_WORKSPACE: pipery
        run: |
          pipery-actions sync \
            --repos "${{ matrix.repo }}" \
            --platforms "${{ matrix.platform }}"
      
      - name: Notify on failure
        if: failure()
        uses: actions/github-script@v7
        with:
          script: |
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: 'Sync failed for ${{ matrix.repo }} → ${{ matrix.platform }}'
            })
```

### 4. Workflow Call Pattern (Reusable Workflow)

For creating reusable release workflows:

```yaml
# .github/workflows/release.yml (caller)
name: Release

on:
  workflow_dispatch:
    inputs:
      bump:
        description: Version bump
        required: true
        type: choice
        options: [patch, minor, major]

jobs:
  release:
    uses: pipery-dev/pipery-tooling/.github/workflows/pipery-release.yml@main
    with:
      bump: ${{ inputs.bump }}
    secrets:
      GITLAB_TOKEN: ${{ secrets.GITLAB_TOKEN }}
      BITBUCKET_TOKEN: ${{ secrets.BITBUCKET_TOKEN }}
```

```yaml
# .github/workflows/pipery-release.yml (reusable)
name: Pipery Release

on:
  workflow_call:
    inputs:
      bump:
        type: string
        required: true
    secrets:
      GITLAB_TOKEN:
        required: true
      BITBUCKET_TOKEN:
        required: true

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      
      - name: Install pipery-tooling
        run: pip install git+https://github.com/pipery-dev/pipery-tooling.git
      
      - name: Configure Git
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
      
      - name: Release with cross-platform sync
        env:
          GITLAB_TOKEN: ${{ secrets.GITLAB_TOKEN }}
          BITBUCKET_TOKEN: ${{ secrets.BITBUCKET_TOKEN }}
        run: pipery-actions release --repo . --bump ${{ inputs.bump }} --push
```

### 5. Bash Script Integration

For complex operations in bash scripts:

```yaml
name: Complex Release

on:
  workflow_dispatch:

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      
      - name: Release script
        env:
          GITLAB_TOKEN: ${{ secrets.GITLAB_TOKEN }}
          BITBUCKET_TOKEN: ${{ secrets.BITBUCKET_TOKEN }}
          BITBUCKET_WORKSPACE: pipery
        run: |
          #!/bin/bash
          set -euo pipefail
          
          # Install dependencies
          pip install git+https://github.com/pipery-dev/pipery-tooling.git
          
          # Validate tokens are available
          if [ -z "$GITLAB_TOKEN" ]; then
            echo "ERROR: GITLAB_TOKEN not available"
            exit 1
          fi
          if [ -z "$BITBUCKET_TOKEN" ]; then
            echo "ERROR: BITBUCKET_TOKEN not available"
            exit 1
          fi
          
          # Configure git
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          
          # Perform release
          pipery-actions release --repo . --bump patch --push
          
          # Log success
          echo "Release completed successfully"
```

## Security Best Practices

### 1. Minimize Token Exposure

Always pass secrets as environment variables, never in command arguments:

```yaml
# ✓ GOOD - Token in environment variable
env:
  GITLAB_TOKEN: ${{ secrets.GITLAB_TOKEN }}
run: pipery-actions sync --repos my-repo

# ✗ BAD - Token visible in command history
run: pipery-actions sync --repos my-repo --token ${{ secrets.GITLAB_TOKEN }}
```

### 2. Limit Secret Scope

Only expose secrets to steps that need them:

```yaml
# ✓ GOOD - Only exposed to specific step
- name: Sync
  env:
    GITLAB_TOKEN: ${{ secrets.GITLAB_TOKEN }}
  run: pipery-actions sync --repos my-repo

- name: Other task
  # GITLAB_TOKEN not available here
  run: echo "No token in this step"

# ✗ BAD - Available to all subsequent steps
env:
  GITLAB_TOKEN: ${{ secrets.GITLAB_TOKEN }}
jobs:
  release:
    steps:
      - name: Any step can access the token
```

### 3. Use Masked Output

For logging token-related information, mask sensitive values:

```yaml
- name: Log sync status
  env:
    GITLAB_TOKEN: ${{ secrets.GITLAB_TOKEN }}
  run: |
    # Token is automatically masked in logs
    # Even if you echo it, GitHub Actions masks it
    echo "Token length: ${#GITLAB_TOKEN}"
    
    # Use ::add-mask to mask additional patterns
    echo "::add-mask::$(echo $GITLAB_TOKEN | head -c 10)***"
```

### 4. Audit Secret Access

Monitor which workflows use organization secrets:

```bash
# Check all workflow files that reference secrets
grep -r "secrets\." .github/workflows/ | grep -E "GITLAB|BITBUCKET"
```

## Testing Integration

### 1. Verify Secrets Are Available

```yaml
- name: Verify secrets available
  run: |
    if [ -z "$GITLAB_TOKEN" ]; then
      echo "ERROR: GITLAB_TOKEN not available"
      exit 1
    fi
    if [ -z "$BITBUCKET_TOKEN" ]; then
      echo "ERROR: BITBUCKET_TOKEN not available"
      exit 1
    fi
    echo "All secrets available"
  env:
    GITLAB_TOKEN: ${{ secrets.GITLAB_TOKEN }}
    BITBUCKET_TOKEN: ${{ secrets.BITBUCKET_TOKEN }}
```

### 2. Test Token Authentication

```yaml
- name: Test GitLab token
  env:
    GITLAB_TOKEN: ${{ secrets.GITLAB_TOKEN }}
  run: |
    curl -s -H "PRIVATE-TOKEN: $GITLAB_TOKEN" \
      https://gitlab.com/api/v4/user | jq '.username'

- name: Test Bitbucket token
  env:
    BITBUCKET_TOKEN: ${{ secrets.BITBUCKET_TOKEN }}
  run: |
    curl -s -u "x-token-auth:$BITBUCKET_TOKEN" \
      https://api.bitbucket.org/2.0/user | jq '.username'
```

### 3. Integration Test Workflow

```yaml
name: Test Secret Integration

on:
  pull_request:
  workflow_dispatch:

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      
      - name: Install pipery-tooling
        run: pip install git+https://github.com/pipery-dev/pipery-tooling.git
      
      - name: Test GitLab token
        env:
          GITLAB_TOKEN: ${{ secrets.GITLAB_TOKEN }}
        run: |
          python3 << 'EOF'
          import os
          import requests
          
          token = os.getenv("GITLAB_TOKEN")
          if not token:
            print("ERROR: GITLAB_TOKEN not available")
            exit(1)
          
          headers = {"PRIVATE-TOKEN": token}
          try:
            response = requests.get(
              "https://gitlab.com/api/v4/user",
              headers=headers,
              timeout=10
            )
            if response.status_code == 200:
              print(f"✓ GitLab auth successful: {response.json()['username']}")
            else:
              print(f"✗ GitLab auth failed: {response.status_code}")
              exit(1)
          except Exception as e:
            print(f"✗ GitLab connection failed: {e}")
            exit(1)
          EOF
      
      - name: Test Bitbucket token
        env:
          BITBUCKET_TOKEN: ${{ secrets.BITBUCKET_TOKEN }}
        run: |
          python3 << 'EOF'
          import os
          import requests
          
          token = os.getenv("BITBUCKET_TOKEN")
          if not token:
            print("ERROR: BITBUCKET_TOKEN not available")
            exit(1)
          
          try:
            response = requests.get(
              "https://api.bitbucket.org/2.0/user",
              auth=("x-token-auth", token),
              timeout=10
            )
            if response.status_code == 200:
              print(f"✓ Bitbucket auth successful: {response.json()['username']}")
            else:
              print(f"✗ Bitbucket auth failed: {response.status_code}")
              exit(1)
          except Exception as e:
            print(f"✗ Bitbucket connection failed: {e}")
            exit(1)
          EOF
```

## Troubleshooting

### Secret Not Available in Workflow

**Problem**: Workflow fails with "token not set" error

**Solutions**:
1. Verify secret is set in organization:
   ```bash
   gh secret list --org pipery | grep TOKEN_NAME
   ```
2. Ensure `env:` section includes the secret:
   ```yaml
   env:
     GITLAB_TOKEN: ${{ secrets.GITLAB_TOKEN }}
   ```
3. Check organization permissions (requires admin access to manage secrets)

### Authentication Fails in Workflow

**Problem**: API calls return 401 Unauthorized

**Solutions**:
1. Verify token is not expired
2. Check token scope on platform (GitLab/Bitbucket)
3. Test token manually:
   ```bash
   export GITLAB_TOKEN="your_token"
   curl -H "PRIVATE-TOKEN: $GITLAB_TOKEN" https://gitlab.com/api/v4/user
   ```

### Workflow Logs Show Secret Value

**Problem**: Token appears in workflow logs

**Solution**: GitHub Actions automatically masks known secrets. If custom format appears in logs:
1. Use `::add-mask::` to mask the pattern
2. Avoid echoing secrets unnecessarily
3. Check for custom output formatting that bypasses masking

## Related Documentation

- [GITHUB_ORG_SECRETS.md](GITHUB_ORG_SECRETS.md) — Main documentation
- [ORG_SECRETS_CLI_REFERENCE.md](ORG_SECRETS_CLI_REFERENCE.md) — GitHub CLI commands
- [TOKEN_ROTATION_CHECKLIST.md](TOKEN_ROTATION_CHECKLIST.md) — Token renewal procedures
- [GitHub Actions Secrets Documentation](https://docs.github.com/en/actions/security-guides/using-secrets-in-github-actions)

---

**Last Updated**: 2026-05-07
