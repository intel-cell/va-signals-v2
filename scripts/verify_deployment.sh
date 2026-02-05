#!/bin/bash
# Deployment Verification Script
#
# Verifies all VA Signals components are functioning correctly.
# Run after deployments or as part of health checks.
#
# Usage: ./scripts/verify_deployment.sh [--verbose]

set -e

VERBOSE=${1:-""}
SERVICE_URL="${SERVICE_URL:-https://va-signals-dashboard-595196122440.us-central1.run.app}"
REGION="${REGION:-us-central1}"
PROJECT="${PROJECT:-veteran-signals}"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Counters
PASSED=0
FAILED=0
WARNINGS=0

log_pass() {
    echo -e "${GREEN}✓${NC} $1"
    ((PASSED++))
}

log_fail() {
    echo -e "${RED}✗${NC} $1"
    ((FAILED++))
}

log_warn() {
    echo -e "${YELLOW}⚠${NC} $1"
    ((WARNINGS++))
}

log_info() {
    if [ "$VERBOSE" == "--verbose" ]; then
        echo "  → $1"
    fi
}

echo "============================================"
echo "VA Signals Deployment Verification"
echo "============================================"
echo "Service URL: $SERVICE_URL"
echo "Region: $REGION"
echo "Time: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo ""

# 1. Cloud Run Service Health
echo "1. Cloud Run Service"
echo "--------------------"

# Check if service is reachable
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$SERVICE_URL/" --max-time 10 2>/dev/null || echo "000")
if [ "$HTTP_CODE" == "200" ] || [ "$HTTP_CODE" == "401" ]; then
    log_pass "Service reachable (HTTP $HTTP_CODE)"
else
    log_fail "Service unreachable (HTTP $HTTP_CODE)"
fi

# Check health endpoint
HEALTH_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$SERVICE_URL/api/auth/me" --max-time 10 2>/dev/null || echo "000")
log_info "Auth endpoint: HTTP $HEALTH_CODE"

# Check metrics endpoint
METRICS_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$SERVICE_URL/metrics" --max-time 10 2>/dev/null || echo "000")
if [ "$METRICS_CODE" == "200" ]; then
    log_pass "Prometheus metrics endpoint active"
else
    log_warn "Metrics endpoint returned HTTP $METRICS_CODE"
fi

# Check OpenAPI docs
DOCS_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$SERVICE_URL/docs" --max-time 10 2>/dev/null || echo "000")
if [ "$DOCS_CODE" == "200" ]; then
    log_pass "Swagger docs accessible"
else
    log_fail "Swagger docs inaccessible (HTTP $DOCS_CODE)"
fi

echo ""

# 2. Database Connectivity
echo "2. Database Connectivity"
echo "------------------------"

# This would require auth, so we'll check via Cloud SQL directly
if command -v gcloud &> /dev/null; then
    DB_STATUS=$(gcloud sql instances describe va-signals-db --project=$PROJECT --format="get(state)" 2>/dev/null || echo "UNKNOWN")
    if [ "$DB_STATUS" == "RUNNABLE" ]; then
        log_pass "Cloud SQL instance running"
    else
        log_fail "Cloud SQL status: $DB_STATUS"
    fi
else
    log_warn "gcloud not available, skipping DB check"
fi

echo ""

# 3. Cloud Run Jobs
echo "3. Cloud Run Jobs"
echo "-----------------"

if command -v gcloud &> /dev/null; then
    JOBS=("fr-delta" "bills" "hearings" "oversight" "state-monitor")
    for job in "${JOBS[@]}"; do
        JOB_EXISTS=$(gcloud run jobs describe $job --region=$REGION --project=$PROJECT --format="get(name)" 2>/dev/null || echo "")
        if [ -n "$JOB_EXISTS" ]; then
            log_pass "Job exists: $job"
        else
            log_warn "Job not found: $job"
        fi
    done
else
    log_warn "gcloud not available, skipping jobs check"
fi

echo ""

# 4. External APIs
echo "4. External API Connectivity"
echo "----------------------------"

# Federal Register API
FR_CODE=$(curl -s -o /dev/null -w "%{http_code}" "https://www.federalregister.gov/api/v1/documents?per_page=1" --max-time 10 2>/dev/null || echo "000")
if [ "$FR_CODE" == "200" ]; then
    log_pass "Federal Register API accessible"
else
    log_warn "Federal Register API: HTTP $FR_CODE"
fi

# Congress.gov API (requires API key, just check reachability)
CONGRESS_CODE=$(curl -s -o /dev/null -w "%{http_code}" "https://api.congress.gov" --max-time 10 2>/dev/null || echo "000")
if [ "$CONGRESS_CODE" == "200" ] || [ "$CONGRESS_CODE" == "401" ] || [ "$CONGRESS_CODE" == "403" ]; then
    log_pass "Congress.gov API reachable"
else
    log_warn "Congress.gov API: HTTP $CONGRESS_CODE"
fi

echo ""

# 5. GitHub Repository
echo "5. Source Repository"
echo "--------------------"

GH_CODE=$(curl -s -o /dev/null -w "%{http_code}" "https://github.com/intel-cell/va-signals-v2" --max-time 10 2>/dev/null || echo "000")
if [ "$GH_CODE" == "200" ]; then
    log_pass "GitHub repository accessible"
else
    log_fail "GitHub repository: HTTP $GH_CODE"
fi

echo ""

# 6. Cloud Storage (Backups)
echo "6. Backup Storage"
echo "-----------------"

if command -v gsutil &> /dev/null; then
    BUCKET_EXISTS=$(gsutil ls gs://va-signals-backups 2>/dev/null || echo "ERROR")
    if [[ "$BUCKET_EXISTS" != "ERROR" ]]; then
        log_pass "Backup bucket accessible"

        # Check for recent backups
        LATEST_BACKUP=$(gsutil ls -l gs://va-signals-backups/daily/ 2>/dev/null | tail -2 | head -1 || echo "")
        if [ -n "$LATEST_BACKUP" ]; then
            log_info "Latest backup: $LATEST_BACKUP"
            log_pass "Recent backups found"
        else
            log_warn "No recent backups found"
        fi
    else
        log_warn "Backup bucket not accessible"
    fi
else
    log_warn "gsutil not available, skipping backup check"
fi

echo ""

# 7. Summary
echo "============================================"
echo "Verification Summary"
echo "============================================"
echo -e "${GREEN}Passed:${NC}   $PASSED"
echo -e "${RED}Failed:${NC}   $FAILED"
echo -e "${YELLOW}Warnings:${NC} $WARNINGS"
echo ""

if [ $FAILED -gt 0 ]; then
    echo -e "${RED}DEPLOYMENT VERIFICATION FAILED${NC}"
    echo "Review failed checks above and take corrective action."
    exit 1
elif [ $WARNINGS -gt 0 ]; then
    echo -e "${YELLOW}DEPLOYMENT VERIFICATION PASSED WITH WARNINGS${NC}"
    echo "Review warnings above."
    exit 0
else
    echo -e "${GREEN}DEPLOYMENT VERIFICATION PASSED${NC}"
    exit 0
fi
