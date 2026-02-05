#!/bin/bash
# VA Signals - Cloud DNS Configuration
# GOLF COMMAND - Operation COMMAND POST
# FRAGO 003 Authorization
#
# This script configures Cloud DNS for cmd.veteran-signals.com
#
# Usage: ./configure-cloud-dns.sh [--dry-run]

set -euo pipefail

# Configuration
PROJECT_ID="${PROJECT_ID:-va-signals-v2}"
DOMAIN="cmd.veteran-signals.com"
ZONE_NAME="veteran-signals-com"  # Cloud DNS zone name (typically domain with dashes)
TTL=300  # 5 minutes - appropriate for initial setup

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_cmd() { echo -e "${BLUE}[CMD]${NC} $1"; }

# Parse arguments
DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
    log_warn "DRY RUN MODE - Commands will be displayed but not executed"
fi

log_info "=========================================="
log_info "GOLF COMMAND - Cloud DNS Configuration"
log_info "FRAGO 003 Authorization"
log_info "=========================================="
log_info ""
log_info "Project: ${PROJECT_ID}"
log_info "Domain: ${DOMAIN}"
log_info "Zone: ${ZONE_NAME}"
log_info "TTL: ${TTL} seconds"
log_info ""

# Step 1: Get Load Balancer IP
log_info "Step 1: Retrieving Load Balancer IP..."
if [[ "$DRY_RUN" == "false" ]]; then
    # Try to get forwarding rule IP
    LB_IP=$(gcloud compute forwarding-rules list \
        --project="$PROJECT_ID" \
        --format='value(IPAddress)' \
        --filter="name~va-signals" 2>/dev/null | head -1 || echo "")

    if [[ -z "$LB_IP" ]]; then
        # Try global addresses
        LB_IP=$(gcloud compute addresses list \
            --project="$PROJECT_ID" \
            --global \
            --format='value(address)' 2>/dev/null | head -1 || echo "")
    fi

    if [[ -z "$LB_IP" ]]; then
        log_error "Could not find Load Balancer IP"
        log_info "Please provide LB_IP environment variable"
        log_info "Example: LB_IP=34.120.xxx.xxx ./configure-cloud-dns.sh"
        exit 1
    fi

    log_info "Load Balancer IP: ${LB_IP}"
else
    LB_IP="<LB_IP_PLACEHOLDER>"
    log_info "Would retrieve Load Balancer IP"
fi

# Step 2: List existing DNS zones
log_info ""
log_info "Step 2: Checking DNS zone..."
if [[ "$DRY_RUN" == "false" ]]; then
    ZONE_EXISTS=$(gcloud dns managed-zones list \
        --project="$PROJECT_ID" \
        --filter="name=${ZONE_NAME}" \
        --format='value(name)' 2>/dev/null || echo "")

    if [[ -z "$ZONE_EXISTS" ]]; then
        log_warn "Zone ${ZONE_NAME} not found. Checking for alternatives..."
        gcloud dns managed-zones list --project="$PROJECT_ID" --format="table(name,dnsName)"
        log_info ""
        log_info "Please set ZONE_NAME to match your existing zone"
        log_info "Example: ZONE_NAME=my-zone-name ./configure-cloud-dns.sh"
        exit 1
    fi

    log_info "Found zone: ${ZONE_NAME}"
else
    log_info "Would verify zone ${ZONE_NAME} exists"
fi

# Step 3: Check for existing record
log_info ""
log_info "Step 3: Checking for existing A record..."
if [[ "$DRY_RUN" == "false" ]]; then
    EXISTING_RECORD=$(gcloud dns record-sets list \
        --project="$PROJECT_ID" \
        --zone="$ZONE_NAME" \
        --name="${DOMAIN}." \
        --type=A \
        --format='value(rrdatas)' 2>/dev/null || echo "")

    if [[ -n "$EXISTING_RECORD" ]]; then
        log_warn "A record already exists: ${EXISTING_RECORD}"
        log_info "Will update existing record"
        RECORD_ACTION="update"
    else
        log_info "No existing A record found. Will create new."
        RECORD_ACTION="create"
    fi
else
    log_info "Would check for existing A record"
    RECORD_ACTION="create"
fi

# Step 4: Create/Update DNS record
log_info ""
log_info "Step 4: Configuring A record..."
if [[ "$DRY_RUN" == "false" ]]; then
    # Start transaction
    gcloud dns record-sets transaction start \
        --project="$PROJECT_ID" \
        --zone="$ZONE_NAME"

    if [[ "$RECORD_ACTION" == "update" ]]; then
        # Remove existing record
        gcloud dns record-sets transaction remove "$EXISTING_RECORD" \
            --project="$PROJECT_ID" \
            --zone="$ZONE_NAME" \
            --name="${DOMAIN}." \
            --ttl="$TTL" \
            --type=A
    fi

    # Add new record
    gcloud dns record-sets transaction add "$LB_IP" \
        --project="$PROJECT_ID" \
        --zone="$ZONE_NAME" \
        --name="${DOMAIN}." \
        --ttl="$TTL" \
        --type=A

    # Execute transaction
    gcloud dns record-sets transaction execute \
        --project="$PROJECT_ID" \
        --zone="$ZONE_NAME"

    log_info "A record configured: ${DOMAIN} -> ${LB_IP}"
else
    log_cmd "gcloud dns record-sets transaction start --zone=${ZONE_NAME}"
    log_cmd "gcloud dns record-sets transaction add ${LB_IP} --name=${DOMAIN}. --ttl=${TTL} --type=A"
    log_cmd "gcloud dns record-sets transaction execute --zone=${ZONE_NAME}"
fi

# Step 5: Verify record
log_info ""
log_info "Step 5: Verifying DNS record..."
if [[ "$DRY_RUN" == "false" ]]; then
    sleep 2
    VERIFIED=$(gcloud dns record-sets list \
        --project="$PROJECT_ID" \
        --zone="$ZONE_NAME" \
        --name="${DOMAIN}." \
        --type=A \
        --format='value(rrdatas)' 2>/dev/null || echo "")

    if [[ "$VERIFIED" == "$LB_IP" ]]; then
        log_info "DNS record verified: ${DOMAIN} -> ${VERIFIED}"
    else
        log_warn "Verification returned: ${VERIFIED:-EMPTY}"
    fi
else
    log_info "Would verify DNS record"
fi

# Summary
log_info ""
log_info "=========================================="
log_info "DNS Configuration Complete"
log_info "=========================================="
log_info ""
log_info "Record: ${DOMAIN} -> ${LB_IP}"
log_info "TTL: ${TTL} seconds"
log_info ""
log_info "Next steps:"
log_info "1. Wait for DNS propagation (typically 1-5 minutes for Cloud DNS)"
log_info "2. Verify: dig ${DOMAIN}"
log_info "3. Run SSL configuration: ./configure-dns-ssl.sh"
log_info ""
log_info "External verification:"
log_info "  dig @8.8.8.8 ${DOMAIN}"
log_info "  nslookup ${DOMAIN}"
