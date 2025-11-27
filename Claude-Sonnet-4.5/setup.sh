#!/bin/bash
# Setup script for Appointment Booking System
# Installs dependencies and prepares environment

echo "========================================"
echo "Appointment Booking System Setup"
echo "Reliable_Appointment_Booking_v2"
echo "========================================"
echo ""

# Get project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$SCRIPT_DIR"

cd "$PROJECT_ROOT"

echo "📁 Project Root: $PROJECT_ROOT"
echo ""

# Check Python
echo "🔍 Checking Python installation..."
if ! command -v python &> /dev/null; then
    if ! command -v python3 &> /dev/null; then
        echo "❌ Python not found"
        echo "   Please install Python 3.8 or higher"
        echo "   Download from: https://www.python.org/downloads/"
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

# Check pip
echo "🔍 Checking pip..."
if ! $PYTHON_CMD -m pip --version &> /dev/null; then
    echo "❌ pip not found"
    echo "   Please install pip: $PYTHON_CMD -m ensurepip --upgrade"
    exit 1
fi

echo "✅ pip found"
$PYTHON_CMD -m pip --version
echo ""

# Install dependencies
echo "📦 Installing dependencies..."
if [ -f "requirements.txt" ]; then
    $PYTHON_CMD -m pip install -r requirements.txt
    echo "✅ Dependencies installed"
else
    echo "⚠️  requirements.txt not found, installing minimal dependencies..."
    $PYTHON_CMD -m pip install pyyaml
fi
echo ""

# Create necessary directories
echo "📁 Creating directory structure..."
mkdir -p logs
mkdir -p tests/integration
mkdir -p mocks
mkdir -p src/appointment
mkdir -p src/adapters
mkdir -p frontend/static
mkdir -p docs/screenshots
mkdir -p scripts

echo "✅ Directories created"
echo ""

# Verify project structure
echo "📋 Verifying project structure..."
REQUIRED_FILES=(
    "src/appointment/state_machine.py"
    "src/appointment/idempotency.py"
    "src/appointment/saga.py"
    "src/appointment/database.py"
    "src/appointment/audit_logger.py"
    "src/appointment/controller.py"
    "src/adapters/calendar_adapter.py"
    "mocks/mock_calendar_service.py"
    "tests/run_suite.py"
    "tests/integration/appointment_cases.yaml"
    "frontend/index.html"
    "logs/audit_schema.json"
)

MISSING_FILES=0
for file in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "$file" ]; then
        echo "❌ Missing: $file"
        MISSING_FILES=$((MISSING_FILES + 1))
    fi
done

if [ $MISSING_FILES -eq 0 ]; then
    echo "✅ All required files present"
else
    echo "⚠️  $MISSING_FILES file(s) missing"
fi
echo ""

# Test Python imports
echo "🔍 Testing Python imports..."
$PYTHON_CMD -c "
import sys
import os
sys.path.insert(0, os.getcwd())

try:
    from src.appointment.state_machine import AppointmentState
    from src.appointment.idempotency import IdempotencyManager
    from mocks.mock_calendar_service import MockCalendarService
    print('✅ All imports successful')
except ImportError as e:
    print(f'❌ Import error: {e}')
    sys.exit(1)
"

if [ $? -ne 0 ]; then
    echo "⚠️  Some imports failed. Please check your Python environment."
fi
echo ""

# Display setup summary
echo "========================================"
echo "✅ SETUP COMPLETE"
echo "========================================"
echo ""
echo "📋 Next Steps:"
echo "   1. Run tests: bash run_tests.sh"
echo "   2. Open frontend: open frontend/index.html"
echo "   3. View docs: docs/root_cause_analysis.md"
echo "   4. Check logs: logs/audit_schema.json"
echo ""
echo "🔧 Quick Test:"
echo "   bash scripts/run_appointment_suite.sh"
echo ""
echo "📚 Documentation:"
echo "   - Root Cause Analysis: docs/root_cause_analysis.md"
echo "   - Remediation Plan: docs/remediation_plan.md"
echo "   - Test Cases: tests/integration/appointment_cases.yaml"
echo "   - Audit Schema: logs/audit_schema.json"
echo ""
