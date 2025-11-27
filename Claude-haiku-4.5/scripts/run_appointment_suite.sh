#!/bin/bash

# Run appointment booking integration test suite
# Single-command harness for executing all 5 scenarios

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo ""
echo "╔════════════════════════════════════════════════════════════════════════════════╗"
echo "║     Reliable Appointment Booking v2 - Integration Test Suite                   ║"
echo "╚════════════════════════════════════════════════════════════════════════════════╝"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: python3 not found"
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1)
echo "[*] $PYTHON_VERSION"
echo ""

# Create output directory
mkdir -p "$PROJECT_ROOT/logs"
mkdir -p "$PROJECT_ROOT/test_results"

# Run test suite
cd "$PROJECT_ROOT"

echo "[*] Running integration test suite..."
echo ""

python3 -u tests/run_suite.py

TEST_EXIT_CODE=$?

echo ""
echo "╔════════════════════════════════════════════════════════════════════════════════╗"
echo "║                          Test Run Complete                                     ║"
echo "╚════════════════════════════════════════════════════════════════════════════════╝"
echo ""

if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo "✓ All tests passed!"
    echo ""
    echo "Artifacts:"
    echo "  - Audit log: logs/appointment_audit.log"
    echo "  - Integration tests: tests/run_suite.py"
    echo ""
else
    echo "✗ Some tests failed"
    echo ""
    exit 1
fi

exit 0
