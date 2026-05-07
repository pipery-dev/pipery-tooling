#!/bin/bash
# Example: Cross-platform repository synchronization
#
# This script demonstrates how to use organization secrets to sync repositories
# from GitHub to GitLab and Bitbucket using the pipery-actions CLI.
#
# Prerequisites:
# - pipery-tooling installed: pip install git+https://github.com/pipery-dev/pipery-tooling.git
# - GITLAB_TOKEN environment variable set (GitHub org secret)
# - BITBUCKET_TOKEN environment variable set (GitHub org secret)
# - BITBUCKET_WORKSPACE environment variable set (Bitbucket workspace name)
#
# Usage:
#   export GITLAB_TOKEN="glpat-xxxxxxxxxxxxx"
#   export BITBUCKET_TOKEN="xxxxxxxxxxxxxxxx"
#   export BITBUCKET_WORKSPACE="pipery"
#   ./scripts/sync-repos-example.sh [--repo REPO] [--platform PLATFORM] [--dry-run]

set -euo pipefail

# Configuration
DEFAULT_REPOS=(
    "pipery-python-ci"
    "pipery-rust-ci"
    "pipery-golang-ci"
)

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Parse arguments
REPO="${1:-}"
PLATFORM="${2:-all}"  # all, gitlab, or bitbucket
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --repo)
            REPO="$2"
            shift 2
            ;;
        --platform)
            PLATFORM="$2"
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
            shift
            ;;
    esac
done

show_help() {
    cat << 'EOF'
Cross-platform repository synchronization example

Usage:
  ./scripts/sync-repos-example.sh [--repo REPO] [--platform PLATFORM] [--dry-run]

Options:
  --repo REPO          Repository to sync (e.g., pipery-python-ci)
                       If not specified, syncs all default repos
  --platform PLATFORM  Target platform: github, gitlab, bitbucket, or all
                       Default: all
  --dry-run            Show what would be synced without making changes
  --help               Show this help message

Environment Variables Required:
  GITLAB_TOKEN         GitLab personal access token (glpat-...)
  BITBUCKET_TOKEN      Bitbucket app password
  BITBUCKET_WORKSPACE  Bitbucket workspace name (e.g., pipery)

Examples:
  # Sync single repo to all platforms
  ./scripts/sync-repos-example.sh --repo pipery-python-ci

  # Sync to specific platform
  ./scripts/sync-repos-example.sh --repo pipery-rust-ci --platform gitlab

  # Preview without making changes
  ./scripts/sync-repos-example.sh --dry-run

  # Use in GitHub Actions workflow
  env:
    GITLAB_TOKEN: ${{ secrets.GITLAB_TOKEN }}
    BITBUCKET_TOKEN: ${{ secrets.BITBUCKET_TOKEN }}
    BITBUCKET_WORKSPACE: pipery
  run: ./scripts/sync-repos-example.sh --repo ${{ matrix.repo }} --platform all
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

# Validate environment
check_tokens() {
    if [ -z "${GITLAB_TOKEN:-}" ]; then
        log_error "GITLAB_TOKEN not set"
        echo "  Set: export GITLAB_TOKEN='glpat-xxxxxxxxxxxxx'"
        return 1
    fi

    if [ -z "${BITBUCKET_TOKEN:-}" ]; then
        log_error "BITBUCKET_TOKEN not set"
        echo "  Set: export BITBUCKET_TOKEN='xxxxxxxxxxxxx'"
        return 1
    fi

    if [ -z "${BITBUCKET_WORKSPACE:-}" ]; then
        log_error "BITBUCKET_WORKSPACE not set"
        echo "  Set: export BITBUCKET_WORKSPACE='pipery'"
        return 1
    fi

    log_success "All required tokens configured"
    return 0
}

check_cli() {
    if ! command -v pipery-actions &> /dev/null; then
        log_error "pipery-actions CLI not found"
        echo "  Install: pip install git+https://github.com/pipery-dev/pipery-tooling.git"
        return 1
    fi
    log_success "pipery-actions CLI found: $(pipery-actions --version 2>/dev/null || echo 'installed')"
    return 0
}

# Sync operations
sync_repo() {
    local repo=$1
    local platform=$2

    log_info "Syncing $repo to $platform..."

    if [ $DRY_RUN = true ]; then
        log_info "[DRY-RUN] Would sync: $repo → $platform"
        return 0
    fi

    # Use pipery-actions sync command
    if pipery-actions sync \
        --repos "$repo" \
        --platforms "$platform" \
        --gitlab-token "$GITLAB_TOKEN" \
        --bitbucket-token "$BITBUCKET_TOKEN" \
        --bitbucket-workspace "$BITBUCKET_WORKSPACE"; then
        log_success "Synced: $repo → $platform"
        return 0
    else
        log_error "Failed to sync: $repo → $platform"
        return 1
    fi
}

sync_all_repos() {
    local platform=$1
    local success_count=0
    local fail_count=0

    log_info "Starting cross-platform sync..."
    echo

    for repo in "${DEFAULT_REPOS[@]}"; do
        if sync_repo "$repo" "$platform"; then
            ((success_count++))
        else
            ((fail_count++))
        fi
    done

    echo
    log_info "Sync Summary:"
    log_success "$success_count repositories synced successfully"
    if [ $fail_count -gt 0 ]; then
        log_warning "$fail_count repositories failed"
    fi

    return 0
}

main() {
    echo
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}Cross-Platform Repository Synchronization${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo

    # Preflight checks
    log_info "Running preflight checks..."
    check_tokens || exit 1
    check_cli || exit 1
    echo

    # Perform sync
    if [ -n "$REPO" ]; then
        # Single repo
        log_info "Syncing single repository: $REPO"
        sync_repo "$REPO" "$PLATFORM"
    else
        # All default repos
        sync_all_repos "$PLATFORM"
    fi

    echo
    if [ $DRY_RUN = true ]; then
        log_warning "DRY-RUN MODE: No changes were made"
    else
        log_success "Synchronization complete"
    fi

    echo
    log_info "For more information, see docs/GITHUB_ORG_SECRETS.md"
    echo
}

main "$@"
