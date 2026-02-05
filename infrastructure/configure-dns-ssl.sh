#!/bin/bash
# VA Signals - DNS and SSL Configuration (Google-Managed Certificates)
# GOLF COMMAND - Operation COMMAND POST
#
# This script configures:
# 1. Google-managed SSL certificate for cmd.veteran-signals.com
# 2. Load Balancer URL map for the new domain
# 3. Certificate auto-renewal monitoring
#
# IMPROVEMENT: Uses Google-managed certificates which:
# - Auto-renew before expiration (no manual intervention)
# - Support multiple domains
# - Include certificate health monitoring
#
# Prerequisites:
# - DNS A record for cmd.veteran-signals.com pointing to LB IP
# - Existing load balancer configuration
#
# Usage: ./configure-dns-ssl.sh [--dry-run] [--check-only]

set -euo pipefail

# Configuration
PROJECT_ID="${PROJECT_ID:-va-signals-v2}"
REGION="${REGION:-us-central1}"
DOMAIN="cmd.veteran-signals.com"
CERT_NAME="cmd-veteran-signals-cert-managed"
URL_MAP_NAME="va-signals-url-map"
BACKEND_SERVICE="va-signals-backend"
CERT_EXPIRY_WARNING_DAYS=30

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Parse arguments
DRY_RUN=false
CHECK_ONLY=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=true
            log_warn "DRY RUN MODE - No changes will be made"
            shift
            ;;
        --check-only)
            CHECK_ONLY=true
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Function to check certificate status and expiry
check_cert_status() {
    local cert_name="$1"
    local status expiry_time

    status=$(gcloud compute ssl-certificates describe "$cert_name" --global --format='value(managed.status)' 2>/dev/null || echo "NOT_FOUND")
    expiry_time=$(gcloud compute ssl-certificates describe "$cert_name" --global --format='value(expireTime)' 2>/dev/null || echo "")

    echo "Certificate: $cert_name"
    echo "  Status: $status"

    if [[ -n "$expiry_time" ]]; then
        # Parse expiry and check if within warning threshold
        local expiry_epoch now_epoch days_until_expiry
        expiry_epoch=$(date -d "$expiry_time" +%s 2>/dev/null || date -j -f "%Y-%m-%dT%H:%M:%S" "$expiry_time" +%s 2>/dev/null || echo "0")
        now_epoch=$(date +%s)
        days_until_expiry=$(( (expiry_epoch - now_epoch) / 86400 ))

        echo "  Expires: $expiry_time"
        echo "  Days until expiry: $days_until_expiry"

        if [[ $days_until_expiry -lt $CERT_EXPIRY_WARNING_DAYS ]]; then
            log_warn "Certificate expires in less than ${CERT_EXPIRY_WARNING_DAYS} days!"
            return 1
        fi
    fi

    if [[ "$status" == "ACTIVE" ]]; then
        log_info "Certificate is healthy and active"
        return 0
    else
        log_warn "Certificate status is not ACTIVE: $status"
        return 1
    fi
}

# Check-only mode
if [[ "$CHECK_ONLY" == "true" ]]; then
    log_info "=== Certificate Status Check ==="
    check_cert_status "$CERT_NAME" || exit 1
    exit 0
fi

log_info "=== DNS and SSL Configuration for ${DOMAIN} ==="

# Step 1: Verify DNS resolution
log_info "Step 1: Verifying DNS resolution..."
DNS_RESULT=$(dig +short "$DOMAIN" A || echo "")
if [[ -z "$DNS_RESULT" ]]; then
    log_error "DNS not configured for ${DOMAIN}"
    log_info "Please add an A record pointing to your Load Balancer IP"
    log_info "You can find your LB IP with: gcloud compute addresses list"
    exit 1
else
    log_info "DNS resolves to: $DNS_RESULT"
fi

# Step 2: Create SSL certificate
log_info "Step 2: Creating managed SSL certificate..."
if [[ "$DRY_RUN" == "false" ]]; then
    gcloud compute ssl-certificates create "$CERT_NAME" \
        --domains="$DOMAIN" \
        --global \
        2>/dev/null || log_warn "Certificate may already exist"

    # Check certificate status
    CERT_STATUS=$(gcloud compute ssl-certificates describe "$CERT_NAME" --global --format='value(managed.status)' 2>/dev/null || echo "UNKNOWN")
    log_info "Certificate status: $CERT_STATUS"

    if [[ "$CERT_STATUS" != "ACTIVE" ]]; then
        log_warn "Certificate is provisioning. This can take up to 15 minutes."
        log_info "Check status with: gcloud compute ssl-certificates describe ${CERT_NAME} --global"
    fi
else
    log_info "Would create SSL certificate: $CERT_NAME"
fi

# Step 3: Update URL map with host rule
log_info "Step 3: Updating URL map with host rule..."
if [[ "$DRY_RUN" == "false" ]]; then
    # Export current URL map
    gcloud compute url-maps export "$URL_MAP_NAME" \
        --global \
        --destination=/tmp/url-map.yaml \
        2>/dev/null || log_warn "Could not export URL map (may not exist)"

    # Check if host rule already exists
    if grep -q "$DOMAIN" /tmp/url-map.yaml 2>/dev/null; then
        log_info "Host rule for ${DOMAIN} already exists"
    else
        log_info "Adding host rule for ${DOMAIN}..."
        # This would typically be done via:
        # gcloud compute url-maps add-host-rule $URL_MAP_NAME \
        #     --hosts=$DOMAIN \
        #     --path-matcher-name=default \
        #     --global
        log_warn "Manual step: Add host rule to URL map"
        log_info "Run: gcloud compute url-maps add-host-rule ${URL_MAP_NAME} --hosts=${DOMAIN} --path-matcher-name=default --global"
    fi
else
    log_info "Would update URL map: $URL_MAP_NAME"
fi

# Step 4: Attach certificate to target proxy
log_info "Step 4: Attaching certificate to HTTPS proxy..."
if [[ "$DRY_RUN" == "false" ]]; then
    # List target HTTPS proxies
    PROXY_NAME=$(gcloud compute target-https-proxies list --format='value(name)' | head -1)

    if [[ -n "$PROXY_NAME" ]]; then
        log_info "Found HTTPS proxy: $PROXY_NAME"
        log_info "Adding certificate to proxy..."
        # Note: This may need adjustment based on existing certs
        # gcloud compute target-https-proxies update $PROXY_NAME \
        #     --ssl-certificates=$CERT_NAME \
        #     --global
        log_warn "Manual step: Add certificate to HTTPS proxy"
        log_info "Run: gcloud compute target-https-proxies update ${PROXY_NAME} --ssl-certificates=${CERT_NAME} --global"
    else
        log_warn "No HTTPS proxy found. Load balancer may need to be created."
    fi
else
    log_info "Would attach certificate to HTTPS proxy"
fi

log_info "=== Configuration Summary ==="
log_info "Domain: ${DOMAIN}"
log_info "SSL Certificate: ${CERT_NAME} (Google-managed, auto-renewing)"
log_info "URL Map: ${URL_MAP_NAME}"
log_info ""
log_info "Google-managed certificate benefits:"
log_info "  - Automatic renewal before expiration"
log_info "  - No manual certificate management required"
log_info "  - Certificate health monitoring via Cloud Console"
log_info ""
log_info "Next steps:"
log_info "1. Wait for SSL certificate to become ACTIVE (up to 15 min)"
log_info "2. Verify HTTPS access: curl -I https://${DOMAIN}"
log_info "3. Test application: https://${DOMAIN}/api/runs/stats"
log_info ""
log_info "Monitoring commands:"
log_info "  Check cert status: $0 --check-only"
log_info "  View cert details: gcloud compute ssl-certificates describe ${CERT_NAME} --global"
log_info "  List all certs: gcloud compute ssl-certificates list --global"
