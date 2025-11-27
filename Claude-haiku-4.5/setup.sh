#!/bin/bash

# Setup script for Appointment Booking System v2
# Creates virtual environment, installs dependencies, initializes directories

set -e

echo "=== Reliable Appointment Booking v2 - Setup ===" 

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
echo "[*] Python version: $PYTHON_VERSION"

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "[*] Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo "[*] Installing dependencies from requirements.txt..."
pip install -q -r requirements.txt

# Create necessary directories
echo "[*] Creating directories..."
mkdir -p logs
mkdir -p docs/screenshots
mkdir -p tests/integration
mkdir -p src/__pycache__
mkdir -p mocks/__pycache__

# Initialize logs
echo "[*] Initializing audit log directory..."
touch logs/appointment_audit.log

echo ""
echo "=== Setup Complete ==="
echo ""
echo "To activate the virtual environment, run:"
echo "  source venv/bin/activate"
echo ""
echo "To run integration tests, run:"
echo "  bash run_tests.sh"
echo ""
