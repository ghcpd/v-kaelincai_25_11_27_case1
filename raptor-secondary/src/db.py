import os
import sqlite3
import threading
import uuid
from datetime import datetime
from typing import Optional

from .models import Appointment, AppointmentState, ErrorCode
from . import config

_DB_LOCK = threading.Lock()


class AppointmentRepository:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or config.DB_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with _DB_LOCK:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS appointments (
                        id TEXT PRIMARY KEY,
                        request_id TEXT UNIQUE NOT NULL,
                        slot_id TEXT NOT NULL,
                        patient_name TEXT,
                        state TEXT NOT NULL,
                        calendar_synced INTEGER NOT NULL DEFAULT 0,
                        retry_count INTEGER NOT NULL DEFAULT 0,
                        last_error_code TEXT,
                        last_error_message TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_slot_state ON appointments(slot_id, state);")
                conn.commit()
            finally:
                conn.close()

    def _row_to_appointment(self, row: sqlite3.Row) -> Appointment:
        return Appointment(
            id=row["id"],
            request_id=row["request_id"],
            slot_id=row["slot_id"],
            patient_name=row["patient_name"],
            state=AppointmentState(row["state"]),
            calendar_synced=bool(row["calendar_synced"]),
            retry_count=row["retry_count"],
            last_error_code=ErrorCode(row["last_error_code"]) if row["last_error_code"] else None,
            last_error_message=row["last_error_message"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def get_by_request_id(self, request_id: str) -> Optional[Appointment]:
        conn = self._connect()
        try:
            cur = conn.execute("SELECT * FROM appointments WHERE request_id = ?", (request_id,))
            row = cur.fetchone()
            return self._row_to_appointment(row) if row else None
        finally:
            conn.close()

    def get_active_by_slot(self, slot_id: str) -> Optional[Appointment]:
        conn = self._connect()
        try:
            cur = conn.execute(
                "SELECT * FROM appointments WHERE slot_id = ? AND state IN (?, ?, ?)",
                (slot_id, AppointmentState.IN_PROGRESS.value, AppointmentState.CONFIRMED.value, AppointmentState.COMPENSATING.value),
            )
            row = cur.fetchone()
            return self._row_to_appointment(row) if row else None
        finally:
            conn.close()

    def create(self, request_id: str, slot_id: str, patient_name: Optional[str] = None) -> Appointment:
        with _DB_LOCK:
            conn = self._connect()
            try:
                now = datetime.utcnow().isoformat()
                appointment_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO appointments (id, request_id, slot_id, patient_name, state, calendar_synced, retry_count, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        appointment_id,
                        request_id,
                        slot_id,
                        patient_name,
                        AppointmentState.IN_PROGRESS.value,
                        0,
                        0,
                        now,
                        now,
                    ),
                )
                conn.commit()
                appointment = self.get_by_request_id(request_id)
                assert appointment is not None
                return appointment
            finally:
                conn.close()

    def update_state(self, appointment_id: str, new_state: AppointmentState, calendar_synced: Optional[bool] = None, last_error_code: Optional[ErrorCode] = None, last_error_message: Optional[str] = None, retry_count: Optional[int] = None) -> Appointment:
        with _DB_LOCK:
            conn = self._connect()
            try:
                now = datetime.utcnow().isoformat()
                conn.execute(
                    """
                    UPDATE appointments
                    SET state = ?,
                        calendar_synced = COALESCE(?, calendar_synced),
                        last_error_code = ?,
                        last_error_message = ?,
                        retry_count = COALESCE(?, retry_count),
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        new_state.value,
                        int(calendar_synced) if calendar_synced is not None else None,
                        last_error_code.value if last_error_code else None,
                        last_error_message,
                        retry_count,
                        now,
                        appointment_id,
                    ),
                )
                conn.commit()
                cur = conn.execute("SELECT * FROM appointments WHERE id = ?", (appointment_id,))
                row = cur.fetchone()
                return self._row_to_appointment(row)
            finally:
                conn.close()

    def increment_retry(self, appointment_id: str) -> Appointment:
        with _DB_LOCK:
            conn = self._connect()
            try:
                conn.execute(
                    "UPDATE appointments SET retry_count = retry_count + 1, updated_at = ? WHERE id = ?",
                    (datetime.utcnow().isoformat(), appointment_id),
                )
                conn.commit()
                cur = conn.execute("SELECT * FROM appointments WHERE id = ?", (appointment_id,))
                row = cur.fetchone()
                return self._row_to_appointment(row)
            finally:
                conn.close()

    def clear_all(self):
        with _DB_LOCK:
            conn = self._connect()
            try:
                conn.execute("DELETE FROM appointments")
                conn.commit()
            finally:
                conn.close()
