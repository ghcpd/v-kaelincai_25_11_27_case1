import requests
import yaml
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
YAML = ROOT / 'tests' / 'integration' / 'appointment_cases.yaml'

with open(YAML, 'r') as f:
    cases = yaml.safe_load(f)

for c in cases:
    case_id = c['id']
    simulate = c.get('simulate')
    retries = c.get('retries', 1)
    print(f"Running test: {case_id}, simulate={simulate}")
    idempotency_key = f"test-{case_id}-{int(time.time()*1000)}"
    headers = {'Content-Type': 'application/json', 'Idempotency-Key': idempotency_key}
    payload = {'client_id':'client-1','slot':'2025-12-01T10:00:00Z'}
    if simulate:
        payload['simulate'] = simulate

    resp = requests.post('http://127.0.0.1:5000/api/appointments', json=payload, headers=headers, timeout=10)
    print('Status:', resp.status_code, 'Body:', resp.json())
    if 'appointment_id' in resp.json():
        appt_id = resp.json()['appointment_id']
        st = requests.get(f'http://127.0.0.1:5000/api/appointments/{appt_id}').json()
        print('Appointment state:', st)

print('Test run complete')
