#!/bin/bash
# Test runner wrapper
# Calls the main test suite

echo "Running Appointment Booking Tests..."
echo ""

bash scripts/run_appointment_suite.sh

exit $?
