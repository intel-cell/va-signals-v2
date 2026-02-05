#!/bin/bash
# OWASP ZAP Security Scan Runner
#
# Usage:
#   ./scripts/run_zap_scan.sh [baseline|full|api] [target_url]
#
# Examples:
#   ./scripts/run_zap_scan.sh baseline
#   ./scripts/run_zap_scan.sh full https://staging.example.com
#   ./scripts/run_zap_scan.sh api https://localhost:8000

set -e

SCAN_TYPE="${1:-baseline}"
TARGET_URL="${2:-https://va-signals-dashboard-595196122440.us-central1.run.app}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
REPORTS_DIR="$PROJECT_ROOT/zap-reports"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== OWASP ZAP Security Scan ===${NC}"
echo "Scan Type: $SCAN_TYPE"
echo "Target: $TARGET_URL"
echo ""

# Create reports directory
mkdir -p "$REPORTS_DIR"

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker is required but not installed.${NC}"
    echo "Install Docker from https://docs.docker.com/get-docker/"
    exit 1
fi

# Pull the latest ZAP image
echo "Pulling latest OWASP ZAP Docker image..."
docker pull ghcr.io/zaproxy/zaproxy:stable

# Run the appropriate scan
case "$SCAN_TYPE" in
    baseline)
        echo -e "${YELLOW}Running ZAP Baseline Scan...${NC}"
        docker run --rm -v "$REPORTS_DIR:/zap/wrk:rw" \
            -t ghcr.io/zaproxy/zaproxy:stable \
            zap-baseline.py \
            -t "$TARGET_URL" \
            -g gen.conf \
            -r zap-baseline-report.html \
            -J zap-baseline-report.json \
            -w zap-baseline-report.md \
            -a \
            || true
        ;;

    full)
        echo -e "${YELLOW}Running ZAP Full Scan (this may take a while)...${NC}"
        docker run --rm -v "$REPORTS_DIR:/zap/wrk:rw" \
            -t ghcr.io/zaproxy/zaproxy:stable \
            zap-full-scan.py \
            -t "$TARGET_URL" \
            -g gen.conf \
            -r zap-full-report.html \
            -J zap-full-report.json \
            -w zap-full-report.md \
            -a \
            -m 30 \
            || true
        ;;

    api)
        echo -e "${YELLOW}Running ZAP API Scan...${NC}"
        docker run --rm -v "$REPORTS_DIR:/zap/wrk:rw" \
            -t ghcr.io/zaproxy/zaproxy:stable \
            zap-api-scan.py \
            -t "${TARGET_URL}/openapi.json" \
            -f openapi \
            -r zap-api-report.html \
            -J zap-api-report.json \
            -w zap-api-report.md \
            || true
        ;;

    *)
        echo -e "${RED}Unknown scan type: $SCAN_TYPE${NC}"
        echo "Valid options: baseline, full, api"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}=== Scan Complete ===${NC}"
echo "Reports saved to: $REPORTS_DIR"
echo ""

# List generated reports
if [ -d "$REPORTS_DIR" ]; then
    echo "Generated reports:"
    ls -la "$REPORTS_DIR"
fi

# Print summary from JSON report if available
JSON_REPORT="$REPORTS_DIR/zap-${SCAN_TYPE}-report.json"
if [ -f "$JSON_REPORT" ]; then
    echo ""
    echo -e "${YELLOW}=== Alert Summary ===${NC}"
    if command -v jq &> /dev/null; then
        echo "High Risk: $(jq '.site[0].alerts | map(select(.riskcode == "3")) | length' "$JSON_REPORT" 2>/dev/null || echo "N/A")"
        echo "Medium Risk: $(jq '.site[0].alerts | map(select(.riskcode == "2")) | length' "$JSON_REPORT" 2>/dev/null || echo "N/A")"
        echo "Low Risk: $(jq '.site[0].alerts | map(select(.riskcode == "1")) | length' "$JSON_REPORT" 2>/dev/null || echo "N/A")"
        echo "Informational: $(jq '.site[0].alerts | map(select(.riskcode == "0")) | length' "$JSON_REPORT" 2>/dev/null || echo "N/A")"
    else
        echo "(Install jq for detailed summary: brew install jq)"
    fi
fi

echo ""
echo "View HTML report: open $REPORTS_DIR/zap-${SCAN_TYPE}-report.html"
