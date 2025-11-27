import sqlite3
import threading
from contextlib import contextmanager
import json
import time

DB_PATH = 'c:\\workspace\\reliable_appointment_booking_v2\\appointments.db'

LOCK = threading.Lock()


def init_db():
    with LOCK:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_request_id TEXT UNIQUE,
            slot_id TEXT,
            status TEXT,
            calendar_id TEXT,
            metadata TEXT,
            created_at REAL,
            updated_at REAL
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            appointment_id INTEGER,
            action TEXT,
            status TEXT,
            payload TEXT,
            attempts INTEGER,
            last_error TEXT,
            created_at REAL,
            updated_at REAL
        )''')
        conn.commit()
        conn.close()


@contextmanager
def get_conn():
    with LOCK:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()


def create_appointment(client_request_id, slot_id, metadata=None, status='IN_PROGRESS'):
    now = time.time()
    payload = json.dumps(metadata or {})
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO appointments (client_request_id, slot_id, status, metadata, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (client_request_id, slot_id, status, payload, now, now),
        )
        conn.commit()
        return c.lastrowid


def get_appointment_by_client_id(client_request_id):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM appointments WHERE client_request_id = ?", (client_request_id,))
        row = c.fetchone()
        return dict(row) if row else None


def set_appointment_status(appointment_id, status, calendar_id=None):
    now = time.time()
    with get_conn() as conn:
        c = conn.cursor()
        if calendar_id:
            c.execute(
                "UPDATE appointments SET status = ?, calendar_id = ?, updated_at = ? WHERE id = ?",
                (status, calendar_id, now, appointment_id),
            )
        else:
            c.execute(
                "UPDATE appointments SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, appointment_id),
            )
        conn.commit()


def delete_appointment(appointment_id):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM appointments WHERE id = ?", (appointment_id,))
        conn.commit()


def add_outbox(appointment_id, action, payload):
    now = time.time()
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO outbox (appointment_id, action, status, payload, attempts, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (appointment_id, action, 'PENDING', json.dumps(payload), 0, now, now),
        )
        conn.commit()
        return c.lastrowid


def get_pending_outbox(limit=10):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM outbox WHERE status = 'PENDING' ORDER BY created_at LIMIT ?", (limit,))
        rows = c.fetchall()
        return [dict(r) for r in rows]


def get_outbox_by_appointment(appointment_id):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM outbox WHERE appointment_id = ?", (appointment_id,))
        rows = c.fetchall()
        return [dict(r) for r in rows]


def update_outbox_attempt(outbox_id, status, attempts=0, last_error=None):
    now = time.time()
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(
            "UPDATE outbox SET status = ?, attempts = ?, last_error = ?, updated_at = ? WHERE id = ?",
            (status, attempts, last_error, now, outbox_id),
        )
        conn.commit()


def mark_outbox_done(outbox_id):
    update_outbox_attempt(outbox_id, 'DONE')


def mark_outbox_failed(outbox_id, last_error, attempts):
    update_outbox_attempt(outbox_id, 'FAILED', attempts, last_error)


def reset_db():
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM outbox")
        c.execute("DELETE FROM appointments")
        conn.commit()
