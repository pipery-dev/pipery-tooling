# Token Rotation & Renewal Checklist

This document provides a step-by-step checklist for rotating and renewing GitHub organization secrets.

## Token Expiration Schedule

Current tokens expire **May 7, 2027**.

**Days remaining** (as of May 7, 2026): 365 days

### Timeline for Rotation

- **60-90 days before expiration**: Begin renewal process
- **30 days before expiration**: Generate new tokens
- **14 days before expiration**: Update GitHub org secrets
- **7 days before expiration**: Verify in test workflow
- **At expiration**: Old tokens automatically stop working

## Pre-Rotation Verification

- [ ] Have access to GitLab account (pipery organization)
- [ ] Have access to Bitbucket workspace
- [ ] Have GitHub CLI (`gh`) installed and authenticated
- [ ] Have organization admin access to `pipery` GitHub org
- [ ] Have current tokens documented for reference

## GITLAB_TOKEN Rotation Procedure

### Step 1: Generate New GitLab Token

- [ ] Log in to https://gitlab.com
- [ ] Navigate to: Settings → Access Tokens (top right user menu)
- [ ] Click "Add new token"
- [ ] Configure:
  - **Token name**: `GitHub CI - pipery (NEW-2027)`
  - **Expiration date**: May 7, 2027
  - **Scopes**:
    - [x] `api` — Full API access
    - [x] `read_user` — Read user information
    - [x] `read_repository` — Read repository contents
    - [x] `write_repository` — Push to repositories
- [ ] Click "Create personal access token"
- [ ] Copy the token immediately (you won't see it again)
- [ ] **Store securely** (password manager, secure document, etc.)

### Step 2: Update GitHub Organization Secret

```bash
# Set the new token
gh secret set GITLAB_TOKEN --org pipery --body "glpat-new_token_value"
```

- [ ] Token updated successfully
- [ ] Verify: `gh secret list --org pipery | grep GITLAB`

### Step 3: Verify Token Works

```bash
# Trigger a test workflow that uses GITLAB_TOKEN
# Or run manually:
gh workflow run pipery-release.yml \
  -f bump=patch \
  --repo pipery-dev/pipery-tooling
```

- [ ] Workflow completes successfully
- [ ] Check logs for: "GITLAB_TOKEN authenticated"
- [ ] Verify GitLab shows recent API activity

### Step 4: Revoke Old Token

- [ ] Log in to https://gitlab.com
- [ ] Navigate to: Settings → Access Tokens
- [ ] Find token: `GitHub CI - pipery (OLD-2026)`
- [ ] Click "Revoke"
- [ ] Confirm revocation
- [ ] Wait 30 seconds for immediate effect
- [ ] Verify old token no longer works (optional test)

### Step 5: Document Update

- [ ] Update this file with new expiration date
- [ ] Update [GITHUB_ORG_SECRETS.md](GITHUB_ORG_SECRETS.md):
  - Token expiration date
  - Last rotation date
  - Any scope changes
- [ ] Commit changes to repository

---

## BITBUCKET_TOKEN Rotation Procedure

### Step 1: Generate New Bitbucket App Password

- [ ] Log in to https://bitbucket.org
- [ ] Navigate to: Personal Settings → App passwords (or Account Settings → Security)
- [ ] Click "Create app password"
- [ ] Configure:
  - **Label**: `GitHub CI - pipery (NEW-2027)`
  - **Expiration**: May 7, 2027
  - **Permissions**:
    - [x] `repository:write` — Push code
    - [x] `repositories:admin` — Manage repositories
- [ ] Click "Create"
- [ ] Copy the password immediately (you won't see it again)
- [ ] **Store securely** (password manager, secure document, etc.)

### Step 2: Update GitHub Organization Secret

```bash
# Set the new token
gh secret set BITBUCKET_TOKEN --org pipery --body "new_app_password"
```

- [ ] Token updated successfully
- [ ] Verify: `gh secret list --org pipery | grep BITBUCKET`

### Step 3: Verify Token Works

```bash
# Trigger a test workflow that uses BITBUCKET_TOKEN
# Or run a sync operation:
pipery-actions sync \
  --repos pipery-python-ci \
  --platforms bitbucket
```

- [ ] Sync/workflow completes successfully
- [ ] Check logs for: "Bitbucket authenticated"
- [ ] Verify Bitbucket shows recent API activity

### Step 4: Revoke Old App Password

- [ ] Log in to https://bitbucket.org
- [ ] Navigate to: Personal Settings → App passwords
- [ ] Find password: `GitHub CI - pipery (OLD-2026)`
- [ ] Click the delete/trash icon
- [ ] Confirm deletion
- [ ] Wait for immediate effect
- [ ] Verify old password no longer works (optional test)

### Step 5: Document Update

- [ ] Update this file with new expiration date
- [ ] Update [GITHUB_ORG_SECRETS.md](GITHUB_ORG_SECRETS.md):
  - Token expiration date
  - Last rotation date
  - Any scope changes
- [ ] Commit changes to repository

---

## Emergency Token Revocation

If a token is suspected to be compromised:

### Immediate Actions

1. **Revoke compromised token immediately**
   - GitLab: Settings → Access Tokens → Revoke
   - Bitbucket: Settings → App passwords → Delete

2. **Generate replacement token**
   - Follow the respective rotation procedure above
   - Use same scopes as original

3. **Update GitHub org secret**
   ```bash
   gh secret set TOKEN_NAME --org pipery --body "new_value"
   ```

4. **Verify in workflows**
   - Trigger test workflow
   - Check for successful authentication

5. **Audit activity** (optional)
   - Review recent API calls on GitLab/Bitbucket
   - Check for unauthorized activities
   - Document any suspicious activity

---

## Rotation History

| Date | Token | Old Expiration | New Expiration | Status | Notes |
|------|-------|-----------------|-----------------|--------|-------|
| 2026-05-07 | GITLAB_TOKEN | N/A | 2027-05-07 | Initial Setup | Created for cross-platform sync |
| 2026-05-07 | BITBUCKET_TOKEN | N/A | 2027-05-07 | Initial Setup | Created for cross-platform sync |

## Affected Workflows/Scripts

The following will stop working when tokens expire:

1. **pipery-tooling release workflow**
   - `.github/workflows/pipery-release.yml`
   - Cross-platform sync operations
   - Tag synchronization

2. **All CI repository releases**
   - pipery-python-ci, pipery-rust-ci, etc.
   - Uses pipery-tooling release workflow

3. **Repository synchronization**
   - Cross-platform sync operations
   - GitHub → GitLab, GitHub → Bitbucket

4. **Cross-platform CI/CD operations**
   - Tag creation across platforms
   - Branch synchronization
   - Release coordination

## Monitoring for Upcoming Expirations

### GitHub Actions Reminder (Automated)

Consider setting up a scheduled workflow:

```yaml
name: Token Expiration Reminder

on:
  schedule:
    # Runs on the first day of every month
    - cron: '0 9 1 * *'

jobs:
  check-expiration:
    runs-on: ubuntu-latest
    steps:
      - name: Check token expiration
        env:
          GITLAB_EXPIRE: '2027-05-07'
          BITBUCKET_EXPIRE: '2027-05-07'
        run: |
          # Check if tokens expire within 90 days
          TODAY=$(date +%s)
          EXPIRE=$(date -d "$GITLAB_EXPIRE" +%s)
          DAYS=$((($EXPIRE - $TODAY) / 86400))
          if [ $DAYS -lt 90 ]; then
            echo "WARNING: GITLAB_TOKEN expires in $DAYS days"
          fi
```

### Manual Monitoring

Set calendar reminders:
- [ ] 90 days before expiration (Feb 7, 2027)
- [ ] 60 days before expiration (Mar 8, 2027)
- [ ] 30 days before expiration (Apr 7, 2027)
- [ ] 14 days before expiration (Apr 23, 2027)
- [ ] 7 days before expiration (Apr 30, 2027)

---

## Rollback Procedure

If a new token causes issues:

1. **Identify the issue**
   - Check workflow logs for authentication errors
   - Verify token scope permissions

2. **Revert to previous token**
   ```bash
   # If you have the old token still available
   gh secret set TOKEN_NAME --org pipery --body "old_token_value"
   ```

3. **Investigate the problem**
   - Check token scopes
   - Verify platform API changes
   - Test token on its respective platform

4. **Fix and re-apply**
   - Generate new token with correct scopes
   - Update secret again
   - Test thoroughly before finalizing

---

## Contact & Escalation

For issues with token rotation:

1. Check [GITHUB_ORG_SECRETS.md](GITHUB_ORG_SECRETS.md) troubleshooting section
2. Verify GitHub CLI is up to date: `gh upgrade`
3. Verify organization admin access
4. Contact GitHub Support if unable to access organization secrets

---

## Documentation Links

- Main guide: [GITHUB_ORG_SECRETS.md](GITHUB_ORG_SECRETS.md)
- CLI reference: [ORG_SECRETS_CLI_REFERENCE.md](ORG_SECRETS_CLI_REFERENCE.md)
- Setup script: [../scripts/setup-org-secrets.sh](../scripts/setup-org-secrets.sh)
- GitLab PAT docs: https://docs.gitlab.com/ee/user/profile/personal_access_tokens.html
- Bitbucket app passwords: https://support.atlassian.com/bitbucket-cloud/docs/app-passwords/

---

**Last Updated**: 2026-05-07

Next Review Date: 2026-08-07 (90 days before expiration)
