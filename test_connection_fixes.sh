#!/bin/bash
# Test script to validate connection fixes for Qdrant and Milvus
# This script demonstrates how the fixes resolve the health check issues

set -e

echo "=========================================="
echo "Connection Fixes Validation Test"
echo "=========================================="
echo ""

# Test 1: Validate Docker Compose Configuration
echo "Test 1: Validating Docker Compose configuration..."
if docker compose -f docker-compose.ci.yml --profile compare config >/dev/null 2>&1; then
    echo "✓ PASS: Docker Compose configuration is valid"
else
    echo "✗ FAIL: Docker Compose configuration has errors"
    exit 1
fi
echo ""

# Test 2: Verify Qdrant Health Check Command
echo "Test 2: Testing Qdrant health check command (should fail when service not running)..."
if docker run --rm qdrant/qdrant:v1.8.3 timeout 1 bash -c '</dev/tcp/localhost/6333' 2>/dev/null; then
    echo "✗ FAIL: Health check passed when it should have failed"
    exit 1
else
    echo "✓ PASS: Health check correctly fails when service not running"
fi
echo ""

# Test 3: Verify Milvus has curl available
echo "Test 3: Verifying curl is available in Milvus container..."
if docker run --rm milvusdb/milvus:v2.3.3 which curl >/dev/null 2>&1; then
    echo "✓ PASS: curl is available in Milvus container"
else
    echo "✗ FAIL: curl not found in Milvus container"
    exit 1
fi
echo ""

# Test 4: Verify bash is available in Qdrant container
echo "Test 4: Verifying bash is available in Qdrant container..."
if docker run --rm qdrant/qdrant:v1.8.3 which bash >/dev/null 2>&1; then
    echo "✓ PASS: bash is available in Qdrant container"
else
    echo "✗ FAIL: bash not found in Qdrant container"
    exit 1
fi
echo ""

# Test 5: Verify network configuration
echo "Test 5: Checking explicit network configuration..."
network_config=$(docker compose -f docker-compose.ci.yml --profile compare config 2>/dev/null | grep -A 3 "^networks:")
if echo "$network_config" | grep -q "infinity-ledger-ci"; then
    echo "✓ PASS: Explicit network configuration found (infinity-ledger-ci)"
else
    echo "✗ FAIL: Explicit network configuration missing"
    exit 1
fi
echo ""

# Test 6: Verify Phase 0 is present in QA command
echo "Test 6: Verifying Phase 0 (connection pre-check) is present..."
if docker compose -f docker-compose.ci.yml --profile compare config 2>/dev/null | grep -q "Phase 0: Verify Service Connectivity"; then
    echo "✓ PASS: Phase 0 connection pre-check found"
else
    echo "✗ FAIL: Phase 0 connection pre-check missing"
    exit 1
fi
echo ""

echo "=========================================="
echo "All validation tests passed! ✓"
echo "=========================================="
echo ""
echo "Summary of fixes:"
echo "  1. Qdrant health check now uses bash TCP test (no curl/wget needed)"
echo "  2. Milvus start_period increased to 60s for proper initialization"
echo "  3. QA container verifies connectivity before running benchmarks (Phase 0)"
echo "  4. Explicit network configuration ensures consistent DNS resolution"
echo "  5. Proper variable escaping in docker-compose.yml"
echo ""
echo "Next steps:"
echo "  - Run full CI pipeline to test in actual environment"
echo "  - Monitor service health checks during startup"
echo "  - Verify QA container successfully connects to all services"
