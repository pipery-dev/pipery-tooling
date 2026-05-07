#!/bin/bash
# Setup script for GitHub organization secrets
#
# This script configures GitHub organization-level secrets for cross-platform CI/CD
# Used by: pipery-tooling release workflows and cross-platform sync operations
#
# Prerequisites:
# - GitHub CLI (gh) installed and authenticated
# - User has organization admin permissions for 'pipery'
#
# Usage:
#   ./scripts/setup-org-secrets.sh [--gitlab-token TOKEN] [--bitbucket-token TOKEN] [--dry-run]
#
# Examples:
#   # Interactive prompts for tokens
#   ./scripts/setup-org-secrets.sh
#
#   # Provide tokens as arguments
#   ./scripts/setup-org-secrets.sh --gitlab-token glpat-xxx --bitbucket-token yyy
#
#   # Preview what would be done without making changes
#   ./scripts/setup-org-secrets.sh --dry-run

set -euo pipefail

# Configuration
ORGANIZATION="pipery"
GITLAB_TOKEN_NAME="GITLAB_TOKEN"
BITBUCKET_TOKEN_NAME="BITBUCKET_TOKEN"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse command line arguments
DRY_RUN=false
GITLAB_TOKEN=""
BITBUCKET_TOKEN=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --gitlab-token)
            GITLAB_TOKEN="$2"
            shift 2
            ;;
        --bitbucket-token)
            BITBUCKET_TOKEN="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --help)
            show_help
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

show_help() {
    cat << 'EOF'
Setup GitHub organization secrets for cross-platform CI/CD

Usage:
  ./scripts/setup-org-secrets.sh [options]

Options:
  --gitlab-token TOKEN        GitLab personal access token (glpat-...)
  --bitbucket-token TOKEN     Bitbucket app password
  --dry-run                   Show what would be done without making changes
  --help                      Show this help message

Examples:
  # Interactive mode (prompts for tokens)
  ./scripts/setup-org-secrets.sh

  # Provide tokens as arguments
  ./scripts/setup-org-secrets.sh \
    --gitlab-token glpat-1234567890 \
    --bitbucket-token MyAppPassword123

  # Preview without making changes
  ./scripts/setup-org-secrets.sh --dry-run

Tokens:
  GITLAB_TOKEN
    - Type: GitLab Personal Access Token
    - Format: glpat-xxxxxxxxxxxxxxx
    - Expires: May 7, 2027
    - Scopes: api, read_user, read_repository, write_repository

  BITBUCKET_TOKEN
    - Type: Bitbucket App Password
    - Format: Base64-encoded string
    - Expires: May 7, 2027
    - Scopes: repository:write, repositories:admin

For more information, see docs/GITHUB_ORG_SECRETS.md
EOF
}

# Utility functions
log_info() {
    echo -e "${BLUE}ℹ${NC} $*"
}

log_success() {
    echo -e "${GREEN}✓${NC} $*"
}

log_warning() {
    echo -e "${YELLOW}⚠${NC} $*"
}

log_error() {
    echo -e "${RED}✗${NC} $*"
}

check_gh_installed() {
    if ! command -v gh &> /dev/null; then
        log_error "GitHub CLI (gh) is not installed"
        echo "  Install from: https://cli.github.com"
        exit 1
    fi
    log_success "GitHub CLI found: $(gh --version)"
}

check_gh_auth() {
    if ! gh auth status --hostname github.com &> /dev/null; then
        log_error "Not authenticated with GitHub CLI"
        echo "  Run: gh auth login"
        exit 1
    fi
    log_success "GitHub CLI authenticated"
}

check_org_access() {
    if ! gh org list --limit 100 | grep -q "^$ORGANIZATION$"; then
        log_error "No access to organization '$ORGANIZATION'"
        echo "  You must have admin access to the organization to manage secrets"
        exit 1
    fi
    log_success "Access to organization '$ORGANIZATION' confirmed"
}

prompt_for_token() {
    local token_name=$1
    local token_description=$2
    local token_format=$3

    echo
    log_info "Enter $token_name"
    echo "  Description: $token_description"
    echo "  Format: $token_format"
    read -sp "  Value (input hidden): " token_value
    echo

    if [ -z "$token_value" ]; then
        log_warning "No value provided for $token_name, skipping"
        return 1
    fi

    echo "$token_value"
    return 0
}

set_secret() {
    local secret_name=$1
    local secret_value=$2
    local description=$3

    if [ $DRY_RUN = true ]; then
        log_info "[DRY-RUN] Would set secret: $secret_name"
        echo "  Description: $description"
        echo "  Value length: ${#secret_value} characters"
        return 0
    fi

    log_info "Setting secret: $secret_name"

    if gh secret set "$secret_name" --org "$ORGANIZATION" --body "$secret_value"; then
        log_success "Secret '$secret_name' configured"
        return 0
    else
        log_error "Failed to set secret '$secret_name'"
        return 1
    fi
}

list_secrets() {
    log_info "Current organization secrets:"
    if gh secret list --org "$ORGANIZATION" 2>/dev/null; then
        return 0
    else
        log_warning "Could not list secrets (may require org admin access)"
        return 1
    fi
}

validate_token_format() {
    local token=$1
    local token_type=$2

    case $token_type in
        gitlab)
            if [[ ! $token =~ ^glpat- ]]; then
                log_warning "GitLab token doesn't start with 'glpat-' (may still be valid)"
            fi
            ;;
        bitbucket)
            if [ ${#token} -lt 20 ]; then
                log_warning "Bitbucket token seems short (usually longer)"
            fi
            ;;
    esac
}

main() {
    echo
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}GitHub Organization Secrets Setup${NC}"
    echo -e "${BLUE}Organization: $ORGANIZATION${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo

    # Preflight checks
    log_info "Running preflight checks..."
    check_gh_installed
    check_gh_auth
    check_org_access
    echo

    # Get current secrets
    log_info "Current secrets in organization:"
    list_secrets || true
    echo

    # Collect tokens
    if [ -z "$GITLAB_TOKEN" ]; then
        GITLAB_TOKEN=$(prompt_for_token \
            "$GITLAB_TOKEN_NAME" \
            "GitLab personal access token" \
            "glpat-xxxxxxxxxxxxxxx") || GITLAB_TOKEN=""
    fi

    if [ -z "$BITBUCKET_TOKEN" ]; then
        BITBUCKET_TOKEN=$(prompt_for_token \
            "$BITBUCKET_TOKEN_NAME" \
            "Bitbucket app password" \
            "base64-encoded string") || BITBUCKET_TOKEN=""
    fi

    # Validate formats
    if [ -n "$GITLAB_TOKEN" ]; then
        validate_token_format "$GITLAB_TOKEN" "gitlab"
    fi
    if [ -n "$BITBUCKET_TOKEN" ]; then
        validate_token_format "$BITBUCKET_TOKEN" "bitbucket"
    fi

    # Set secrets
    echo
    log_info "Configuring secrets..."

    if [ -n "$GITLAB_TOKEN" ]; then
        set_secret "$GITLAB_TOKEN_NAME" "$GITLAB_TOKEN" \
            "GitLab personal access token (expires May 7, 2027)"
    else
        log_warning "Skipping GITLAB_TOKEN (not provided)"
    fi

    if [ -n "$BITBUCKET_TOKEN" ]; then
        set_secret "$BITBUCKET_TOKEN_NAME" "$BITBUCKET_TOKEN" \
            "Bitbucket app password (expires May 7, 2027)"
    else
        log_warning "Skipping BITBUCKET_TOKEN (not provided)"
    fi

    # Summary
    echo
    if [ $DRY_RUN = true ]; then
        log_warning "DRY-RUN MODE: No changes were made"
    else
        log_success "Organization secrets configured successfully"
    fi

    echo
    log_info "Next steps:"
    echo "  1. Verify secrets are accessible in workflows:"
    echo "     gh secret list --org $ORGANIZATION"
    echo
    echo "  2. Update workflow files to use secrets:"
    echo "     See docs/GITHUB_ORG_SECRETS.md for examples"
    echo
    echo "  3. Test with a workflow run:"
    echo "     pipery-actions release --repo . --bump patch"
    echo
    echo -e "${BLUE}Documentation: docs/GITHUB_ORG_SECRETS.md${NC}"
    echo
}

main "$@"
