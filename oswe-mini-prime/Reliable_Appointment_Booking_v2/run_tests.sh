#!/usr/bin/env bash
# Wrapper that starts services and runs the integration test harness
set -e
# Start mock calendar service and API in background, then run test suite
python -u mocks/mock_calendar_service.py &
CAL_PID=$!
python -u src/app.py &
API_PID=$!
# Give them a moment
sleep 1
python tests/run_suite.py
# Kill background services
kill $CAL_PID $API_PID || true
