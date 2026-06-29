#!/usr/bin/env bash
# Health check script for CoachIQ deployment
# Can be used by NixOS for service health monitoring

set -euo pipefail

# Configuration
HOST="${COACHIQ_SERVER__HOST:-localhost}"
PORT="${COACHIQ_SERVER__PORT:-8000}"
TIMEOUT="${HEALTH_CHECK_TIMEOUT:-5}"

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "CoachIQ Health Check"
echo "===================="
echo "Target: http://${HOST}:${PORT}"
echo

# Function to check endpoint
check_endpoint() {
    local endpoint=$1
    local description=$2

    printf "%-40s" "$description:"

    if curl -sf -m "$TIMEOUT" "http://${HOST}:${PORT}${endpoint}" > /dev/null; then
        echo -e "${GREEN}✓ OK${NC}"
        return 0
    else
        echo -e "${RED}✗ FAILED${NC}"
        return 1
    fi
}

# Track overall health
HEALTHY=true

# Check main health endpoint
if ! check_endpoint "/health" "Main health endpoint"; then
    HEALTHY=false
fi

# Check API documentation
check_endpoint "/docs" "API documentation" || true

# Check Domain API v1 endpoints
if check_endpoint "/api/v1/entities/health" "Domain API v1 - Entities"; then
    echo "  → Domain API v1 is active"
else
    echo "  → Domain API v1 not available"
fi

# Check WebSocket endpoint
printf "%-40s" "WebSocket endpoint:"
if curl -sf -m "$TIMEOUT" \
    -H "Upgrade: websocket" \
    -H "Connection: Upgrade" \
    "http://${HOST}:${PORT}/ws" 2>&1 | grep -q "400"; then
    echo -e "${GREEN}✓ OK${NC} (upgrade required)"
else
    echo -e "${YELLOW}? UNKNOWN${NC}"
fi

# Check metrics endpoint if enabled
if curl -sf -m "$TIMEOUT" "http://${HOST}:${PORT}/metrics" > /dev/null 2>&1; then
    echo -e "Metrics endpoint:                        ${GREEN}✓ ENABLED${NC}"
fi

echo
echo "Summary:"
echo "--------"

if [ "$HEALTHY" = true ]; then
    echo -e "${GREEN}Service is healthy${NC}"
    exit 0
else
    echo -e "${RED}Service is unhealthy${NC}"
    exit 1
fi
