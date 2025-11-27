import subprocess
import sys
import time
import requests
import yaml
import os
import signal
from pathlib import Path

# Configure paths
ROOT = Path(__file__).resolve().parents[1]
MOCK = ROOT / 'mocks' / 'mock_calendar_service.py'
API = ROOT / 'src' / 'app.py'
YAML = ROOT / 'tests' / 'integration' / 'appointment_cases.yaml'
LOGS = ROOT / 'logs' / 'appointments.jsonl'

# Start the mock calendar and API
python = sys.executable
mock_proc = subprocess.Popen([python, '-m', 'mocks.mock_calendar_service'], stdout=sys.stdout, stderr=sys.stderr)
api_proc = subprocess.Popen([python, '-m', 'src.app'], stdout=sys.stdout, stderr=sys.stderr)

# Give services a moment
time.sleep(1)

# Load tests
with open(YAML, 'r') as f:
    cases = yaml.safe_load(f)

results = []
for c in cases:
    case_id = c['id']
    simulate = c.get('simulate')
    retries = c.get('retries', 1)
    print(f"Running test: {case_id}, simulate={simulate}")
    idempotency_key = f"test-{case_id}-{int(time.time()*1000)}"
    headers = {'Content-Type': 'application/json', 'Idempotency-Key': idempotency_key}
    if c.get('prefer_async'):
        headers['Prefer'] = 'respond-async'
    payload = {'client_id':'client-1','slot':'2025-12-01T10:00:00Z'}
    if simulate:
        payload['simulate'] = simulate

    status = None
    resp_json = None
    appointment_ids = []
    appt_id = None
    for attempt in range(retries):
        resp = requests.post('http://127.0.0.1:5000/api/appointments', json=payload, headers=headers, timeout=10)
        status = resp.status_code
        try:
            resp_json = resp.json()
        except Exception:
            resp_json = {'raw': resp.text}
        if status == c['expected_status']:
            break
        time.sleep(0.5)

    # Inspect DB state by calling API inspection endpoints
    time.sleep(0.2)
    # Read last lines from log
    last_lines = []
    if LOGS.exists():
        with open(LOGS, 'r', encoding='utf-8') as f:
            last_lines = f.read().splitlines()[-20:]

    # Query appointment state if appointment id returned
    appt_state = None
    if resp_json and resp_json.get('appointment_id'):
        appt_id = resp_json.get('appointment_id')
        appointment_ids.append(appt_id)
        try:
            aresp = requests.get(f'http://127.0.0.1:5000/api/appointments/{appt_id}', timeout=5)
            appt_state = aresp.json()
        except Exception as e:
            appt_state = {'error': str(e)}

    # Validate expected state
    expected_state = c.get('expected_state')
    passed = False
    if expected_state:
        if appt_state and appt_state.get('state') == expected_state:
            passed = True
        else:
            passed = False

    # If we expect async confirmation, poll for a while for final state
    if c.get('prefer_async') and appt_id:
        for _ in range(10):
            time.sleep(0.5)
            aresp = requests.get(f'http://127.0.0.1:5000/api/appointments/{appt_id}', timeout=5)
            if aresp.status_code == 200 and aresp.json().get('state') == 'CONFIRMED':
                appt_state = aresp.json()
                break

    outcome = {'case_id': case_id, 'status':status, 'resp': resp_json, 'appointment_state': appt_state, 'expected_state': expected_state, 'pass': passed, 'logs_snippet': last_lines}
    # idempotency double booking assertions
    if case_id == 'idempotency_retry' and resp_json and resp_json.get('appointment_id'):
        slot = payload.get('slot')
        listed = requests.get(f'http://127.0.0.1:5000/api/appointments?slot={slot}').json()
        outcome['found_appointments_for_slot'] = len(listed)
        outcome['listed'] = listed
    if retries > 1:
        outcome['appointment_ids'] = appointment_ids
    results.append(outcome)
    print('Result:', outcome)

# Kill processes (use terminate for cross-platform compatibility)
api_proc.terminate()
mock_proc.terminate()

print('\nSummary:')
for r in results:
    ok = 'PASS' if r['status'] == next(c for c in cases if c['id']==r['case_id'])['expected_status'] else 'FAIL'
    print(f"{r['case_id']}: {ok} (status {r['status']})")

# Simple metrics
passes = sum(1 for r in results if r['status'] == next(c for c in cases if c['id']==r['case_id'])['expected_status'])
print(f"Passed {passes}/{len(results)} tests")
