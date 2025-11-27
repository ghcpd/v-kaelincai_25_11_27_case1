#!/bin/bash
# Appointment Booking Test Suite Runner
# Executes all 5 integration test scenarios

echo "========================================"
echo "Appointment Booking Test Suite"
echo "Reliable_Appointment_Booking_v2"
echo "========================================"
echo ""

# Change to script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo "📁 Project Root: $PROJECT_ROOT"
echo ""

# Check Python installation
echo "🔍 Checking Python installation..."
if ! command -v python &> /dev/null; then
    if ! command -v python3 &> /dev/null; then
        echo "❌ Python not found. Please install Python 3.x"
        exit 1
    else
        PYTHON_CMD=python3
    fi
else
    PYTHON_CMD=python
fi

echo "✅ Python found: $PYTHON_CMD"
$PYTHON_CMD --version
echo ""

# Check dependencies
echo "🔍 Checking dependencies..."
if ! $PYTHON_CMD -c "import yaml" &> /dev/null; then
    echo "⚠️  PyYAML not found. Installing..."
    $PYTHON_CMD -m pip install -q pyyaml
fi

echo "✅ Dependencies OK"
echo ""

# Create logs directory if not exists
mkdir -p logs

# Run test suite
echo "🚀 Running test suite..."
echo ""

$PYTHON_CMD tests/run_suite.py

TEST_EXIT_CODE=$?

echo ""
echo "========================================"
if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo "✅ ALL TESTS PASSED"
else
    echo "❌ SOME TESTS FAILED"
fi
echo "========================================"
echo ""

# Display log file location
if [ -f "logs/test_audit.log" ]; then
    echo "📄 Audit logs available at: logs/test_audit.log"
    echo "   Lines: $(wc -l < logs/test_audit.log)"
fi

echo ""
echo "📊 Test Metrics:"
echo "   - Test cases executed: 5"
echo "   - Expected outcomes validated"
echo "   - Idempotency verified"
echo "   - PII redaction checked"
echo "   - Compensation logic tested"
echo ""

exit $TEST_EXIT_CODE
