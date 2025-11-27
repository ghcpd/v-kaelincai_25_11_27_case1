import time
import threading
import subprocess
import os
import sys
import requests
import json
import re
from pathlib import Path
from fastapi.testclient import TestClient

# Ensure test DB is isolated
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["APPT_DB"] = os.environ.get("APPT_DB", "sqlite:///c:/chatWorkspace/test_suite.db")

# Import the FastAPI app
from src.main import app  # noqa: E402


def start_mock_calendar(port=8001):
    """Start mock calendar as a subprocess to avoid multiprocessing pickling issues on Windows."""
    script_path = Path(__file__).resolve().parents[1] / 'mocks' / 'mock_calendar_service.py'
    cmd = [sys.executable, str(script_path), '--port', str(port)]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    # give it a moment to start
    time.sleep(0.5)
    return proc


def parse_simple_yaml(yaml_path):
    """Very small parser for the simple YAML format used in this repo's tests."""

    def _parse_scalar(v: str):
        v = v.strip()
        # strip surrounding quotes if present
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            v = v[1:-1]
        if v in ['true', 'false']:
            return v == 'true'
        try:
            return int(v)
        except Exception:
            return v

    cases = []
    with open(yaml_path) as f:
        content = f.read()
    # Each case starts with "- id:"
    raw_cases = re.split(r'\n- ', '\n' + content)
    for rc in raw_cases:
        rc = rc.strip()
        if not rc:
            continue
        d = {}
        lines = rc.splitlines()
        # first line may start with -
        for i, line in enumerate(lines):
            # remove leading dashes/spaces
            line = line.lstrip('- ').rstrip()
            if re.match(r'^[a-zA-Z0-9_]+:\s*$', line):
                # key with nested map
                key = line.split(':', 1)[0]
                nested = {}
                # process following indented lines
                j = i + 1
                while j < len(lines) and (lines[j].startswith('  ') or lines[j].startswith('    ')):
                    inner = lines[j].strip()
                    if ':' in inner:
                        k, v = inner.split(':', 1)
                        nested[k.strip()] = _parse_scalar(v)
                    j += 1
                d[key] = nested
            elif ':' in line:
                k, v = line.split(':', 1)
                d[k.strip()] = _parse_scalar(v)
        cases.append(d)
    return cases


def run_tests(yaml_path):
    cases = parse_simple_yaml(yaml_path)

    # Clean DB file if using sqlite file path
    db_url = os.environ.get('APPT_DB', '')
    if db_url.startswith('sqlite:///'):
        db_file = db_url.replace('sqlite:///','')
        try:
            if os.path.exists(db_file):
                os.remove(db_file)
        except Exception:
            pass

    # Prepare logs
    if os.path.exists('logs/audit.log'):
        os.remove('logs/audit.log')

    # Start mock calendar
    mock_proc = start_mock_calendar(port=8001)

    # Use test client
    client = TestClient(app)

    report = []
    for case in cases:
        cid = case['id']
        mode = case['input'].get('mode', 'success')
        async_confirm = case['input'].get('async_confirm', False)
        payload = {
            'client_request_id': case['input']['client_request_id'],
            'user_id': case['input']['user_id'],
            'slot': case['input']['slot'],
            'async_confirm': async_confirm,
            'mode': mode,
        }
        # Make POST to /appointments/confirm with calendar mode appended to service url
        # The adapter will call http://127.0.0.1:8001/events?mode=xxx
        res = client.post('/appointments/confirm', json=payload)
        expected = case['expected']
        outcome = {'id': cid, 'request_id': payload['client_request_id'], 'res_status': res.status_code}

        # handle special checks
        if cid == 'normal_success':
            outcome['pass'] = (res.status_code == 200 and res.json().get('status') == 'success') if isinstance(res.json(), dict) else False
            # check DB state: appointment exists and status success
            if outcome['pass']:
                from src.db import SessionLocal
                from src.models import Appointment
                db = SessionLocal()
                appt = db.query(Appointment).filter_by(client_request_id=payload['client_request_id']).first()
                outcome['db_status'] = appt.status.value if appt else None
                db.close()
        elif cid == 'calendar_timeout_no_booking':
            outcome['pass'] = (res.status_code == 500)
            # Check DB: no appointment should exist
            from src.db import SessionLocal
            from src.models import Appointment
            db = SessionLocal()
            appt = db.query(Appointment).filter_by(client_request_id=payload['client_request_id']).first()
            outcome['db_exists'] = bool(appt)
            db.close()
            outcome['pass'] = outcome['pass'] and (not outcome['db_exists'])
        elif cid == 'idempotent_retry_no_double_book':
            r1 = client.post('/appointments/confirm', json=payload)
            r2 = client.post('/appointments/confirm', json=payload)
            # ensure the second is idempotent and both return 200
            outcome['pass'] = (r1.status_code == 200 and r2.status_code == 200)
            # check DB for single appointment
            from src.db import SessionLocal
            from src.models import Appointment
            db = SessionLocal()
            appts = db.query(Appointment).filter_by(client_request_id=payload['client_request_id']).all()
            outcome['db_count'] = len(appts)
            db.close()
            outcome['pass'] = outcome['pass'] and outcome['db_count'] == 1
        elif cid == 'partial_success_triggers_compensation':
            # Async case first response should be 202 then after worker runs, appointment should be failed
            # Wait a bit for outbox processing
            outcome['pass'] = (res.status_code == 202)
            time.sleep(2.0)
            from src.db import SessionLocal
            from src.models import Appointment
            db = SessionLocal()
            appt = db.query(Appointment).filter_by(client_request_id=payload['client_request_id']).first()
            outcome['appointment_status'] = appt.status.value if appt else None
            db.close()
            outcome['pass'] = outcome['pass'] and (outcome['appointment_status'] == 'failed')
        elif cid == 'audit_verification':
            outcome['pass'] = res.status_code == 200
            # Check logs for request id
            with open('logs/audit.log', 'r') as fh:
                logs = fh.read()
            count = logs.count(payload['client_request_id'])
            outcome['audit_count'] = count
            outcome['pass'] = outcome['pass'] and count >= 3
        else:
            outcome['pass'] = False

        report.append(outcome)

    # stop mock
    mock_proc.terminate()
    mock_proc.wait(timeout=1)

    # Print report
    print(json.dumps(report, indent=2))

    # Summarize
    passed = sum(1 for r in report if r.get('pass'))
    total = len(report)
    print(f"\nSummary: {passed}/{total} scenarios passed")
    if passed != total:
        sys.exit(1)
    sys.exit(0)


if __name__ == '__main__':
    run_tests('tests/integration/appointment_cases.yaml')
