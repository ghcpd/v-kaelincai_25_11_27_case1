import os
import time
import json
from fastapi.testclient import TestClient
import pytest

# ensure correct workspace root in sys.path
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.main import app, service
from src.db import init_db, engine, Base, SessionLocal
from src.services.appointment_service import CalendarError
from src.models import Appointment, IdempotencyRecord, Outbox
from src.utils.logging import audit_log


@pytest.fixture(autouse=True)
def setup_and_teardown():
    # reset DB tables
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    # reset logs
    logpath = 'logs/audit.log'
    try:
        if os.path.exists(logpath):
            os.remove(logpath)
    except Exception:
        pass
    yield
    # cleanup
    Base.metadata.drop_all(bind=engine)


client = TestClient(app)


def test_normal_success():
    # Arrange: patch calendar to succeed
    service.calendar_adapter.create_event = lambda appointment_id, user_id, slot, mode=None, client_request_id=None: (True, {'event_id': f'evt-{appointment_id}'})
    payload = {'client_request_id':'req-normal-1','user_id':'user-1','slot':'2025-12-01T10:00:00','async_confirm': False}

    # Act
    r = client.post('/appointments/confirm', json=payload)

    # Assert
    assert r.status_code == 200
    j = r.json()
    assert j['status'] == 'success' or 'appointment_id' in j
    # DB check
    db = SessionLocal()
    appt = db.query(Appointment).filter_by(client_request_id='req-normal-1').first()
    assert appt is not None and appt.status.value == 'success'
    db.close()


def test_calendar_timeout_no_booking():
    # Arrange: patch calendar to raise
    def _raise(*a, **k):
        raise CalendarError('Simulated timeout')
    service.calendar_adapter.create_event = _raise

    payload = {'client_request_id':'req-timeout-1','user_id':'user-2','slot':'2025-12-01T11:00:00','async_confirm': False}

    # Act
    r = client.post('/appointments/confirm', json=payload)

    # Assert
    assert r.status_code == 500
    # DB should not have appointment
    db = SessionLocal()
    appt = db.query(Appointment).filter_by(client_request_id='req-timeout-1').first()
    assert appt is None
    db.close()


def test_idempotent_retry_no_double_book():
    # Arrange: calendar returns success
    service.calendar_adapter.create_event = lambda appointment_id, user_id, slot, mode=None, client_request_id=None: (True, {'event_id': f'evt-{appointment_id}'})
    payload = {'client_request_id':'req-idemp-1','user_id':'user-3','slot':'2025-12-01T12:00:00','async_confirm': False}

    # Act: Call twice
    r1 = client.post('/appointments/confirm', json=payload)
    r2 = client.post('/appointments/confirm', json=payload)

    # Assert
    assert r1.status_code == 200
    assert r2.status_code == 200
    # DB only one appointment
    db = SessionLocal()
    appts = db.query(Appointment).filter_by(client_request_id='req-idemp-1').all()
    assert len(appts) == 1
    db.close()


def test_partial_success_triggers_compensation():
    # Arrange: For async_confirm; Calendar fails
    def _raise(*a, **k):
        raise CalendarError('Simulated failure')
    service.calendar_adapter.create_event = _raise
    payload = {'client_request_id':'req-async-1','user_id':'user-4','slot':'2025-12-01T13:00:00','async_confirm': True}

    # Act
    r = client.post('/appointments/confirm', json=payload)
    assert r.status_code == 202

    # Process outbox worker attempts multiple times to trigger compensation
    # Outbox max attempts small in model (2), so call process_outbox_once repeatedly
    for _ in range(3):
        service.process_outbox_once()
        time.sleep(0.1)

    # Assert appointment has been failed (compensated)
    db = SessionLocal()
    appt = db.query(Appointment).filter_by(client_request_id='req-async-1').first()
    assert appt is not None
    assert appt.status.value == 'failed'
    db.close()


def test_audit_verification():
    # Arrange: calendar success
    service.calendar_adapter.create_event = lambda appointment_id, user_id, slot, mode=None, client_request_id=None: (True, {'event_id': f'evt-{appointment_id}'})
    payload = {'client_request_id':'req-audit-1','user_id':'user-5','slot':'2025-12-01T14:00:00','async_confirm': False}

    # Act
    r = client.post('/appointments/confirm', json=payload)
    assert r.status_code == 200

    # Assert logs contain request id at least 3 times
    with open('logs/audit.log', 'r') as fh:
        logs = fh.read()
    assert logs.count('req-audit-1') >= 3
