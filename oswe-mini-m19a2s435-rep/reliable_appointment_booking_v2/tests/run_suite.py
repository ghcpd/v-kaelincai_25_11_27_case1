import subprocess
import sys
import time
import requests
import yaml
import os
import signal
import sqlite3

ROOT = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.path.join(ROOT, 'appointments.db')


def start_process(cmd, env=None, cwd=ROOT):
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, cwd=cwd)
    return proc


def wait_for_port(url, timeout=20):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            resp = requests.get(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.2)
    return False


def read_yaml():
    with open(os.path.join(os.path.dirname(__file__), 'integration', 'appointment_cases.yaml')) as f:
        return yaml.safe_load(f)


def db_query(query, args=()):
    if not os.path.exists(DB_PATH):
        return []
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(query, args)
    rows = c.fetchall()
    conn.close()
    return rows


def count_appointments_by_client(client_request_id):
    rows = db_query('SELECT COUNT(*) FROM appointments WHERE client_request_id = ?', (client_request_id,))
    return rows[0][0] if rows else 0


def appointment_exists(client_request_id):
    return count_appointments_by_client(client_request_id) > 0


def get_appointment(client_request_id):
    rows = db_query('SELECT id, status, calendar_id FROM appointments WHERE client_request_id = ?', (client_request_id,))
    return rows[0] if rows else None


def main():
    # remove old DB
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    # global run start time for watchdog
    run_start = time.time()
    RUN_TIMEOUT = 240  # seconds; whole run timeout

    # Start mock calendar service
    calendar_cmd = [sys.executable, os.path.join(ROOT, 'mocks', 'mock_calendar_service.py')]
    calendar_proc = start_process(calendar_cmd)
    print('Started mock calendar with pid', calendar_proc.pid)

    # wait for mock readiness
    if not wait_for_port('http://127.0.0.1:9001/health'):
        print('Calendar mock health not ready; continuing')

    cases = read_yaml()['scenarios']
    results = []

    for case in cases:
        # Start appointment API fresh for each test case to isolate in-memory state
        api_cmd = [sys.executable, '-m', 'uvicorn', 'src.app:app', '--host', '127.0.0.1', '--port', '8000']
        api_proc = start_process(api_cmd)
        print('Started appointment API with pid', api_proc.pid)
        # wait for API readiness
        if not wait_for_port('http://127.0.0.1:8000/health'):
            print('API health not ready; continuing')
        # watchdog check
        if time.time() - run_start > RUN_TIMEOUT:
            print('Run timeout exceeded, terminating tests')
            results.append({'case': case['id'], 'passed': False, 'http': None, 'extra': 'timed out'})
            break
        print('Running case', case['id'])
        mode = case.get('mode', '')
        req = case['request']
        headers = {'Content-Type': 'application/json'}
        if mode:
            headers['X-Calendar-Mode'] = mode
        if case['id'] == 'idempotent_retry_no_double_booking':
            headers['X-Api-Adapter-Timeout'] = '5'
        # Ensure clean state per test
        try:
            rr = requests.post('http://127.0.0.1:8000/debug/reset', timeout=5)
            print('debug/reset', rr.status_code, rr.text)
        except Exception as ex:
            print('debug/reset failed', ex)
        try:
            resp = requests.post('http://127.0.0.1:8000/appointments/confirm', json=req, headers=headers, timeout=15)
            print('HTTP', resp.status_code, resp.text)
            expected_code = case['expect']['status_code']
            passed = resp.status_code == expected_code
            extra = ''
        except Exception as ex:
            print('HTTP request failed', str(ex))
            resp = None
            expected_code = case['expect']['status_code']
            passed = False
            extra = f'exception:{ex}'

        if case['id'] == 'idempotent_retry_no_double_booking':
            # try again with same client_request_id and assert no double booking
            try:
                resp2 = requests.post('http://127.0.0.1:8000/appointments/confirm', json=req, headers=headers, timeout=10)
                print('Retry HTTP', resp2.status_code, resp2.text)
                count = count_appointments_by_client(req['client_request_id'])
                passed = (count == 1)
                extra = f'count={count}'
            except Exception as ex:
                print('Retry request exception', str(ex))
                extra = f'retry_exception:{ex}'
        elif case['id'] == 'calendar_timeout_no_booking' or case['id'] == 'partial_success_triggers_compensation':
            exists = appointment_exists(req['client_request_id'])
            passed = passed and (exists == case['expect']['db_exists'])
        elif case['id'] == 'normal_success' or case['id'] == 'audit_and_reconciliation':
            exists = appointment_exists(req['client_request_id'])
            passed = passed and exists
        # audit checks
        if 'log_contains' in case['expect']:
            # read logs
            if os.path.exists(os.path.join(ROOT, 'logs', 'appointments.log')):
                with open(os.path.join(ROOT, 'logs', 'appointments.log')) as lf:
                    content = lf.read()
                    passed = passed and (case['expect']['log_contains'] in content)
                    if 'log_contains2' in case['expect']:
                        passed = passed and (case['expect']['log_contains2'] in content)
        http_status = resp.status_code if resp else None
        results.append({'case': case['id'], 'passed': passed, 'http': http_status, 'extra': extra})
        # Close API for this case to isolate in-memory state
        try:
            api_proc.terminate()
            api_proc.wait(timeout=5)
        except Exception:
            api_proc.kill()

    # shutdown mock
    try:
        calendar_proc.terminate()
        calendar_proc.wait(timeout=5)
    except Exception:
        calendar_proc.kill()

    # report
    total = len(results)
    passed_total = sum(1 for r in results if r['passed'])
    print('\nTest Results:')
    for r in results:
        print(r)
    print(f'Passed {passed_total}/{total} cases')
    sys.exit(0 if passed_total == total else 1)


if __name__ == '__main__':
    main()
