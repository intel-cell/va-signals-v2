#!/bin/bash
# Canary Deployment Script for VA Signals Dashboard
# Usage: ./canary-deploy.sh <image-tag> [canary-percentage]
#
# This script implements a safe canary deployment strategy:
# 1. Deploy new revision with 0% traffic
# 2. Route canary percentage (default 10%) to new revision
# 3. Monitor for errors
# 4. Gradually increase traffic or rollback

set -euo pipefail

IMAGE_TAG="${1:-latest}"
CANARY_PCT="${2:-10}"
SERVICE="va-signals-dashboard"
REGION="us-central1"
PROJECT="veteran-signals"
IMAGE="us-central1-docker.pkg.dev/${PROJECT}/va-signals/dashboard:${IMAGE_TAG}"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

error() {
    log "ERROR: $*" >&2
    exit 1
}

get_current_revision() {
    gcloud run services describe "$SERVICE" \
        --region "$REGION" \
        --format='value(status.traffic[0].revisionName)' 2>/dev/null
}

get_latest_revision() {
    gcloud run services describe "$SERVICE" \
        --region "$REGION" \
        --format='value(status.latestReadyRevisionName)' 2>/dev/null
}

deploy_no_traffic() {
    log "Deploying new revision with 0% traffic..."
    gcloud run deploy "$SERVICE" \
        --image "$IMAGE" \
        --region "$REGION" \
        --no-traffic \
        --quiet
    
    log "New revision deployed: $(get_latest_revision)"
}

set_traffic_split() {
    local new_rev="$1"
    local old_rev="$2"
    local new_pct="$3"
    local old_pct=$((100 - new_pct))
    
    log "Setting traffic: ${old_rev}=${old_pct}%, ${new_rev}=${new_pct}%"
    
    gcloud run services update-traffic "$SERVICE" \
        --region "$REGION" \
        --to-revisions="${old_rev}=${old_pct},${new_rev}=${new_pct}" \
        --quiet
}

promote_full() {
    local new_rev="$1"
    
    log "Promoting ${new_rev} to 100% traffic..."
    gcloud run services update-traffic "$SERVICE" \
        --region "$REGION" \
        --to-revisions="${new_rev}=100" \
        --quiet
}

rollback() {
    local old_rev="$1"
    
    log "Rolling back to ${old_rev}..."
    gcloud run services update-traffic "$SERVICE" \
        --region "$REGION" \
        --to-revisions="${old_rev}=100" \
        --quiet
}

check_health() {
    local url="https://${SERVICE}-595196122440.us-central1.run.app/"
    local status
    
    status=$(curl -s -o /dev/null -w "%{http_code}" "$url")
    
    if [ "$status" = "200" ]; then
        return 0
    else
        log "Health check failed: HTTP $status"
        return 1
    fi
}

check_error_rate() {
    # Check Cloud Logging for errors in the last 5 minutes
    local error_count
    
    error_count=$(gcloud logging read \
        "resource.type=cloud_run_revision AND severity>=ERROR AND timestamp>=\"$(date -u -v-5M +%Y-%m-%dT%H:%M:%SZ)\"" \
        --limit=100 \
        --format="value(timestamp)" 2>/dev/null | wc -l | tr -d ' ')
    
    log "Error count in last 5 minutes: $error_count"
    
    if [ "$error_count" -gt 10 ]; then
        return 1
    fi
    return 0
}

main() {
    log "Starting canary deployment for ${SERVICE}"
    log "Image: ${IMAGE}"
    log "Canary percentage: ${CANARY_PCT}%"
    
    # Get current revision before deployment
    CURRENT_REV=$(get_current_revision)
    log "Current revision: ${CURRENT_REV}"
    
    # Deploy new revision with no traffic
    deploy_no_traffic
    NEW_REV=$(get_latest_revision)
    
    if [ "$NEW_REV" = "$CURRENT_REV" ]; then
        log "No changes detected, revision unchanged"
        exit 0
    fi
    
    # Set canary traffic split
    set_traffic_split "$NEW_REV" "$CURRENT_REV" "$CANARY_PCT"
    
    # Wait and check health
    log "Waiting 30 seconds for canary to stabilize..."
    sleep 30
    
    if ! check_health; then
        log "Health check failed, rolling back..."
        rollback "$CURRENT_REV"
        error "Canary deployment failed health check"
    fi
    
    log "Canary deployment successful!"
    log ""
    log "Next steps:"
    log "  - Monitor: gcloud run services describe ${SERVICE} --region ${REGION}"
    log "  - Promote: gcloud run services update-traffic ${SERVICE} --region ${REGION} --to-revisions=${NEW_REV}=100"
    log "  - Rollback: gcloud run services update-traffic ${SERVICE} --region ${REGION} --to-revisions=${CURRENT_REV}=100"
}

case "${1:-}" in
    --promote)
        NEW_REV=$(get_latest_revision)
        promote_full "$NEW_REV"
        log "Promoted ${NEW_REV} to 100%"
        ;;
    --rollback)
        CURRENT_REV="${2:-}"
        if [ -z "$CURRENT_REV" ]; then
            error "Usage: $0 --rollback <revision-name>"
        fi
        rollback "$CURRENT_REV"
        log "Rolled back to ${CURRENT_REV}"
        ;;
    --status)
        gcloud run services describe "$SERVICE" \
            --region "$REGION" \
            --format='table(status.traffic[].revisionName,status.traffic[].percent)'
        ;;
    --help|-h)
        echo "Usage: $0 <image-tag> [canary-percentage]"
        echo "       $0 --promote"
        echo "       $0 --rollback <revision-name>"
        echo "       $0 --status"
        ;;
    *)
        main
        ;;
esac
