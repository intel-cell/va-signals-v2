#!/bin/bash
# VA Signals - Cloud Run Deployment Script
# GOLF COMMAND - Operation COMMAND POST
#
# Usage: ./deploy-cloud-run.sh [--dry-run]

set -euo pipefail

# Configuration
PROJECT_ID="${PROJECT_ID:-va-signals-v2}"
REGION="${REGION:-us-central1}"
SERVICE_NAME="va-signals-dashboard"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Parse arguments
DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
    log_warn "DRY RUN MODE - No changes will be made"
fi

# Verify prerequisites
log_info "Checking prerequisites..."
command -v gcloud >/dev/null 2>&1 || { log_error "gcloud CLI not found"; exit 1; }
command -v docker >/dev/null 2>&1 || { log_error "docker not found"; exit 1; }

# Set project
log_info "Setting project to ${PROJECT_ID}..."
if [[ "$DRY_RUN" == "false" ]]; then
    gcloud config set project "$PROJECT_ID"
fi

# Build container image
log_info "Building container image..."
if [[ "$DRY_RUN" == "false" ]]; then
    docker build -t "$IMAGE_NAME" .
fi

# Push to Container Registry
log_info "Pushing image to Container Registry..."
if [[ "$DRY_RUN" == "false" ]]; then
    docker push "$IMAGE_NAME"
fi

# Deploy to Cloud Run
log_info "Deploying to Cloud Run..."
DEPLOY_CMD="gcloud run deploy ${SERVICE_NAME} \
    --image=${IMAGE_NAME} \
    --region=${REGION} \
    --platform=managed \
    --allow-unauthenticated \
    --min-instances=1 \
    --max-instances=10 \
    --memory=512Mi \
    --cpu=1 \
    --timeout=300 \
    --set-env-vars=\"\
FIREBASE_PROJECT_ID=${PROJECT_ID},\
AUTH_ENABLED=true,\
ENV=production,\
CEO_BRIEF_OUTPUT_DIR=outputs/ceo_briefs,\
EVIDENCE_PACK_OUTPUT_DIR=outputs/evidence_packs\""

if [[ "$DRY_RUN" == "true" ]]; then
    log_info "Would run: $DEPLOY_CMD"
else
    eval "$DEPLOY_CMD"
fi

# Get service URL
if [[ "$DRY_RUN" == "false" ]]; then
    SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" --region="$REGION" --format='value(status.url)')
    log_info "Service deployed at: $SERVICE_URL"
fi

log_info "Deployment complete!"

# Verify deployment
if [[ "$DRY_RUN" == "false" ]]; then
    log_info "Verifying deployment..."
    HEALTH_URL="${SERVICE_URL}/api/runs/stats"
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$HEALTH_URL" || echo "000")

    if [[ "$HTTP_CODE" == "200" ]]; then
        log_info "Health check passed (HTTP $HTTP_CODE)"
    else
        log_warn "Health check returned HTTP $HTTP_CODE"
    fi
fi
