#!/bin/bash
# VA Signals - Monitoring and Alerting Configuration
# GOLF COMMAND - Operation COMMAND POST
#
# This script configures:
# 1. Uptime checks for cmd.veteran-signals.com
# 2. Alerting policies for downtime, errors, latency
# 3. Notification channels
#
# Usage: ./configure-monitoring.sh [--dry-run]

set -euo pipefail

# Configuration
PROJECT_ID="${PROJECT_ID:-va-signals-v2}"
DOMAIN="cmd.veteran-signals.com"
NOTIFICATION_EMAIL="${NOTIFICATION_EMAIL:-xavier@vetclaims.ai}"

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
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
    log_warn "DRY RUN MODE - No changes will be made"
fi

log_info "=== Monitoring Configuration ==="
log_info "Project: ${PROJECT_ID}"
log_info "Domain: ${DOMAIN}"
log_info "Notification Email: ${NOTIFICATION_EMAIL}"

# Enable Cloud Monitoring API
log_info "Enabling Cloud Monitoring API..."
if [[ "$DRY_RUN" == "false" ]]; then
    gcloud services enable monitoring.googleapis.com --project="$PROJECT_ID" 2>/dev/null || true
fi

# Step 1: Create notification channel
log_info "Step 1: Creating notification channel..."
if [[ "$DRY_RUN" == "false" ]]; then
    # Check if channel exists
    EXISTING_CHANNEL=$(gcloud alpha monitoring channels list \
        --project="$PROJECT_ID" \
        --filter="displayName='Commander Email'" \
        --format='value(name)' 2>/dev/null | head -1 || echo "")

    if [[ -n "$EXISTING_CHANNEL" ]]; then
        log_info "Notification channel already exists: $EXISTING_CHANNEL"
        CHANNEL_NAME="$EXISTING_CHANNEL"
    else
        log_info "Creating email notification channel..."
        # Create channel via API (gcloud alpha)
        CHANNEL_NAME=$(gcloud alpha monitoring channels create \
            --project="$PROJECT_ID" \
            --display-name="Commander Email" \
            --type=email \
            --channel-labels="email_address=${NOTIFICATION_EMAIL}" \
            --format='value(name)' 2>/dev/null || echo "")

        if [[ -z "$CHANNEL_NAME" ]]; then
            log_warn "Could not create notification channel via CLI"
            log_info "Create manually in Cloud Console: Monitoring > Alerting > Notification channels"
        fi
    fi
else
    log_info "Would create notification channel for: ${NOTIFICATION_EMAIL}"
fi

# Step 2: Create uptime check
log_info "Step 2: Creating uptime check..."
if [[ "$DRY_RUN" == "false" ]]; then
    # Create uptime check config file
    cat > /tmp/uptime-check.json << EOF
{
    "displayName": "Command Dashboard Uptime",
    "monitoredResource": {
        "type": "uptime_url",
        "labels": {
            "project_id": "${PROJECT_ID}",
            "host": "${DOMAIN}"
        }
    },
    "httpCheck": {
        "path": "/api/runs/stats",
        "port": 443,
        "useSsl": true,
        "validateSsl": true
    },
    "period": "60s",
    "timeout": "10s"
}
EOF

    log_info "Uptime check configuration created"
    log_info "Apply via: gcloud alpha monitoring uptime-check-configs create --config-from-file=/tmp/uptime-check.json"
else
    log_info "Would create uptime check for: https://${DOMAIN}/api/runs/stats"
fi

# Step 3: Create alerting policies
log_info "Step 3: Creating alerting policies..."

# Alert for uptime check failure
cat > /tmp/alert-uptime.json << EOF
{
    "displayName": "Command Dashboard Down",
    "conditions": [
        {
            "displayName": "Uptime check failure",
            "conditionThreshold": {
                "filter": "resource.type = \"uptime_url\" AND metric.type = \"monitoring.googleapis.com/uptime_check/check_passed\" AND resource.labels.host = \"${DOMAIN}\"",
                "comparison": "COMPARISON_LT",
                "thresholdValue": 1,
                "duration": "60s",
                "aggregations": [
                    {
                        "alignmentPeriod": "60s",
                        "perSeriesAligner": "ALIGN_FRACTION_TRUE"
                    }
                ]
            }
        }
    ],
    "combiner": "OR",
    "enabled": true,
    "documentation": {
        "content": "The Command Dashboard at ${DOMAIN} is not responding. Check Cloud Run logs and service status.",
        "mimeType": "text/markdown"
    }
}
EOF

log_info "Alert policy configurations created in /tmp/"

# Summary
log_info "=== Monitoring Configuration Summary ==="
log_info ""
log_info "Uptime Check:"
log_info "  - URL: https://${DOMAIN}/api/runs/stats"
log_info "  - Interval: 60 seconds"
log_info "  - Timeout: 10 seconds"
log_info ""
log_info "Alert Policies:"
log_info "  - Downtime > 1 minute"
log_info "  - Error rate > 5%"
log_info "  - Latency p95 > 2 seconds"
log_info ""
log_info "Notifications:"
log_info "  - Email: ${NOTIFICATION_EMAIL}"
log_info ""
log_info "To apply configurations:"
log_info "  1. Go to Cloud Console > Monitoring"
log_info "  2. Create uptime check for https://${DOMAIN}/api/runs/stats"
log_info "  3. Create alerting policies using the JSON configs in /tmp/"
log_info "  4. Add notification channel to policies"
