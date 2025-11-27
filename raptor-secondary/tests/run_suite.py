import os
import sys
import json
import yaml
from typing import List, Dict

TESTS_DIR = os.path.abspath(os.path.dirname(__file__))
ROOT = os.path.abspath(os.path.join(TESTS_DIR, ".."))
sys.path.insert(0, ROOT)  # add workspace root

from starlette.testclient import TestClient

from src.app import app, service
from src.db import AppointmentRepository
from src.models import AppointmentState
from mocks.mock_calendar_service import MockCalendarService
from src import config

LOG_FILE = os.path.abspath(os.path.join(ROOT, "logs", "app.log"))


def load_cases() -> List[Dict]:
    path = os.path.join(TESTS_DIR, "integration", "appointment_cases.yaml")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def clear_env(repo: AppointmentRepository, mock: MockCalendarService):
    repo.clear_all()
    mock.clear()
    # Clear logs
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "w", encoding="utf-8"):
        pass


def read_logs() -> List[Dict]:
    entries = []
    if not os.path.exists(LOG_FILE):
        return entries
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def slot_available(repo: AppointmentRepository, slot_id: str) -> bool:
    return repo.get_active_by_slot(slot_id) is None


def run_case(client: TestClient, repo: AppointmentRepository, mock: MockCalendarService, case: Dict, metrics: Dict):
    name = case["name"]
    expected = case.get("expected", {})

    # Setup behavior
    behavior = case.get("behavior", {})
    outcome = behavior.get("outcome", "success")
    key = behavior.get("request_id") or behavior.get("slot_id")
    if key:
        mock.set_behavior(key, outcome)

    # Execute request
    req_body = case["request"]
    resp = client.post("/appointments/confirm", json=req_body)

    # Idempotent scenario: call twice
    if expected.get("idempotent"):
        resp2 = client.post("/appointments/confirm", json=req_body)
        assert resp2.status_code == resp.status_code, f"Idempotent mismatch: {resp.status_code} vs {resp2.status_code}"
        body1 = resp.json()
        body2 = resp2.json()
        assert body1.get("appointment_id") == body2.get("appointment_id"), "Idempotent retry returned different appointment_id"
        metrics["idempotent_assertions"] += 1

    # Assertions
    assert resp.status_code == expected.get("status_code"), f"{name}: expected status_code {expected.get('status_code')}, got {resp.status_code}: {resp.text}"
    body = resp.json()

    if "status" in expected:
        assert body.get("status") == expected.get("status"), f"{name}: expected status {expected.get('status')}, got {body.get('status')}"
    if "state" in expected:
        assert body.get("state") == expected.get("state"), f"{name}: expected state {expected.get('state')}, got {body.get('state')}"
    if "error_code" in expected:
        # When raised via HTTPException detail is {code,message}
        detail = body.get("detail") or body.get("error") or {}
        code = detail.get("code") if isinstance(detail, dict) else None
        assert code == expected.get("error_code"), f"{name}: expected error_code {expected.get('error_code')}, got {code}"
    if expected.get("slot_available"):
        assert slot_available(repo, req_body["slot_id"]), f"{name}: slot {req_body['slot_id']} not available after failure"

    if expected.get("compensation_logged"):
        logs = read_logs()
        events = {e.get("event") or e.get("message") for e in logs}
        assert "compensation_completed" in events, f"{name}: compensation_completed not logged"

    if "logs_present" in expected:
        logs = read_logs()
        events = {e.get("event") or e.get("message") for e in logs}
        for ev in expected["logs_present"]:
            assert ev in events, f"{name}: log event {ev} missing"

    # Metrics
    if resp.status_code == 200:
        metrics["success"] += 1
    else:
        metrics["failure"] += 1

    # Accumulate retry counts
    rows = repo._connect().execute("SELECT retry_count FROM appointments").fetchall()
    retry_total = sum(r["retry_count"] for r in rows)
    metrics["total_retries"] += retry_total

    return True


def main():
    repo = service.repo
    mock = service.calendar.service
    client = TestClient(app)

    cases = load_cases()
    metrics = {"success": 0, "failure": 0, "total_retries": 0, "idempotent_assertions": 0}

    for case in cases:
        clear_env(repo, mock)
        try:
            run_case(client, repo, mock, case, metrics)
            print(f"[PASS] {case['name']}")
        except AssertionError as e:
            print(f"[FAIL] {case['name']}: {e}")
            return 1

    print("\nSummary:")
    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
