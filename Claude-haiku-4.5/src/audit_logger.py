"""
Structured logging module for appointment booking
Emits audit events with appointment/request IDs and redacted sensitive data
"""
import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, Optional
from enum import Enum

from src.models import ErrorCode, Appointment, hash_user_id


class EventType(Enum):
    """Audit event types"""
    APPOINTMENT_INIT = "APPOINTMENT_INIT"
    IDEMPOTENCY_CHECK = "IDEMPOTENCY_CHECK"
    DB_RESERVE_START = "DB_RESERVE_START"
    DB_RESERVE_SUCCESS = "DB_RESERVE_SUCCESS"
    DB_RESERVE_FAILED = "DB_RESERVE_FAILED"
    CALENDAR_SYNC_START = "CALENDAR_SYNC_START"
    CALENDAR_SYNC_SUCCESS = "CALENDAR_SYNC_SUCCESS"
    CALENDAR_SYNC_TIMEOUT = "CALENDAR_SYNC_TIMEOUT"
    CALENDAR_SYNC_ERROR = "CALENDAR_SYNC_ERROR"
    COMPENSATION_TRIGGERED = "COMPENSATION_TRIGGERED"
    COMPENSATION_SUCCESS = "COMPENSATION_SUCCESS"
    COMPENSATION_FAILED = "COMPENSATION_FAILED"
    FINAL_SUCCESS = "FINAL_SUCCESS"
    FINAL_FAILURE = "FINAL_FAILURE"
    RETRY_ATTEMPT = "RETRY_ATTEMPT"


class AuditLogger:
    """Structured audit logger for appointment lifecycle"""

    def __init__(self, log_file: str = "logs/appointment_audit.log"):
        self.log_file = log_file
        self.logger = logging.getLogger("appointment_audit")
        
        # File handler with JSON formatting
        handler = logging.FileHandler(log_file)
        handler.setFormatter(logging.Formatter('%(message)s'))
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)

    def log_event(
        self,
        event_type: EventType,
        appointment: Appointment,
        message: str = "",
        duration_ms: Optional[float] = None,
        error_code: Optional[ErrorCode] = None,
        db_state: Optional[Dict[str, Any]] = None,
        calendar_response: Optional[Dict[str, Any]] = None,
        compensation_action: Optional[str] = None
    ) -> None:
        """
        Log a structured audit event
        
        Args:
            event_type: Type of event
            appointment: Appointment entity
            message: Contextual message
            duration_ms: Operation duration
            error_code: Error classification
            db_state: Snapshot of DB state
            calendar_response: Snapshot of calendar response
            compensation_action: Compensation strategy applied
        """
        event = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event_type": event_type.value,
            "appointment_id": appointment.appointment_id,
            "request_id": appointment.request_id,
            "status": appointment.status.value,
            "user_id": hash_user_id(appointment.user_id),
            "message": message,
        }

        if duration_ms is not None:
            event["duration_ms"] = round(duration_ms, 2)

        if appointment.retry_count > 0:
            event["retry_count"] = appointment.retry_count

        if error_code:
            event["error_code"] = error_code.value
        else:
            event["error_code"] = "SUCCESS"

        if appointment.calendar_slot_id:
            event["calendar_slot_id"] = appointment.calendar_slot_id

        if db_state:
            event["db_state"] = db_state

        if calendar_response:
            event["calendar_response"] = calendar_response

        if compensation_action:
            event["compensation_action"] = compensation_action

        # Write as JSON line
        self.logger.info(json.dumps(event))

    def log_idempotency_hit(self, request_id: str, appointment: Appointment) -> None:
        """Log when duplicate request is detected"""
        event = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event_type": EventType.IDEMPOTENCY_CHECK.value,
            "appointment_id": appointment.appointment_id,
            "request_id": request_id,
            "status": appointment.status.value,
            "user_id": hash_user_id(appointment.user_id),
            "message": "Duplicate request detected - returning cached response",
            "error_code": "DUPLICATE_REQUEST"
        }
        self.logger.info(json.dumps(event))

    def print_summary(self) -> None:
        """Print audit log summary to console"""
        try:
            with open(self.log_file, 'r') as f:
                lines = f.readlines()
                print(f"\n[AUDIT LOG] Total events: {len(lines)}")
                print("\nRecent events:")
                for line in lines[-10:]:
                    event = json.loads(line)
                    print(f"  {event['timestamp']} | {event['event_type']:25s} | "
                          f"{event['appointment_id']} | {event['status']}")
        except FileNotFoundError:
            print("[AUDIT LOG] No audit log found")
