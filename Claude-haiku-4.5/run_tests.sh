#!/bin/bash
# Run full integration test suite
set -e

echo "=== Running Appointment Booking Integration Tests ==="
echo ""

cd "$(dirname "$0")"

# Ensure venv is activated (or activate if not)
if [ -z "$VIRTUAL_ENV" ]; then
    if [ -d "venv" ]; then
        echo "[*] Activating virtual environment..."
        source venv/bin/activate
    else
        echo "[-] Virtual environment not found. Run setup.sh first."
        exit 1
    fi
fi

# Run the test suite
python3 tests/run_suite.py

echo ""
echo "=== Tests Complete ==="
