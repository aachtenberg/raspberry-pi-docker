#!/bin/bash
#
# Test runner for AI Monitor - Autonomous SRE Agent
#
# Usage:
#   ./run_tests.sh              # Run all tests
#   ./run_tests.sh -v           # Verbose output
#   ./run_tests.sh --cov        # With coverage report
#   ./run_tests.sh -k "pattern" # Run tests matching pattern
#   ./run_tests.sh --fast       # Skip slow tests
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== AI Monitor Test Suite ===${NC}"
echo ""

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo -e "${YELLOW}pytest not found. Installing test dependencies...${NC}"
    pip install pytest pytest-cov pytest-mock
fi

# Default pytest args
PYTEST_ARGS="-v"

# Parse arguments
COVERAGE=false
FAST=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --cov|--coverage)
            COVERAGE=true
            shift
            ;;
        --fast)
            FAST=true
            shift
            ;;
        -v|--verbose)
            PYTEST_ARGS="$PYTEST_ARGS -v"
            shift
            ;;
        -k)
            PYTEST_ARGS="$PYTEST_ARGS -k $2"
            shift 2
            ;;
        --phase3)
            PYTEST_ARGS="$PYTEST_ARGS -m phase3"
            shift
            ;;
        -x|--exitfirst)
            PYTEST_ARGS="$PYTEST_ARGS -x"
            shift
            ;;
        --pdb)
            PYTEST_ARGS="$PYTEST_ARGS --pdb"
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --cov, --coverage    Generate coverage report"
            echo "  --fast               Skip slow tests"
            echo "  -v, --verbose        Verbose output"
            echo "  -k PATTERN           Run tests matching pattern"
            echo "  --phase3             Run only Phase 3 tests"
            echo "  -x, --exitfirst      Exit on first failure"
            echo "  --pdb                Drop into debugger on failure"
            echo "  -h, --help           Show this help"
            echo ""
            echo "Examples:"
            echo "  $0                            # Run all tests"
            echo "  $0 --cov                      # Run with coverage"
            echo "  $0 -k 'knowledge_base'        # Run knowledge base tests"
            echo "  $0 -k 'confidence'            # Run confidence-related tests"
            echo "  $0 --phase3                   # Run Phase 3 tests only"
            exit 0
            ;;
        *)
            PYTEST_ARGS="$PYTEST_ARGS $1"
            shift
            ;;
    esac
done

# Add fast mode exclusion
if [ "$FAST" = true ]; then
    PYTEST_ARGS="$PYTEST_ARGS -m 'not slow'"
fi

# Add coverage if requested
if [ "$COVERAGE" = true ]; then
    PYTEST_ARGS="$PYTEST_ARGS --cov=. --cov-report=term-missing --cov-report=html:coverage_html"
fi

# Set test environment
export KNOWLEDGE_BASE_DB_TYPE=sqlite
export AI_MONITOR_EXECUTE=false
export AI_MONITOR_KNOWLEDGE_BASE_ENABLED=true

echo -e "${YELLOW}Running: pytest $PYTEST_ARGS${NC}"
echo ""

# Run tests
pytest $PYTEST_ARGS

# Print summary
echo ""
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed!${NC}"
    if [ "$COVERAGE" = true ]; then
        echo -e "${GREEN}Coverage report generated: coverage_html/index.html${NC}"
    fi
else
    echo -e "${RED}✗ Some tests failed${NC}"
    exit 1
fi
