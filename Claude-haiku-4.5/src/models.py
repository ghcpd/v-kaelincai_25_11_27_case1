"""
Domain models for Appointment Booking System v2
Includes idempotency, state management, and compensation logic
"""
import uuid
import hashlib
from enum import Enum
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict
import json


class AppointmentStatus(Enum):
    """Appointment lifecycle states"""
    INIT = "INIT"
    IN_PROGRESS = "IN_PROGRESS"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    PARTIAL = "PARTIAL"  # Booked locally but calendar sync pending
    COMPENSATING = "COMPENSATING"


class ErrorCode(Enum):
    """Standardized error classifications"""
    CALENDAR_TIMEOUT = "CALENDAR_TIMEOUT"
    CALENDAR_INVALID_RESPONSE = "CALENDAR_INVALID_RESPONSE"
    DB_CONFLICT = "DB_CONFLICT"
    DB_ERROR = "DB_ERROR"
    DUPLICATE_REQUEST = "DUPLICATE_REQUEST"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SUCCESS = "SUCCESS"


@dataclass
class CalendarResponse:
    """Structured calendar sync response"""
    http_status: int
    response_time_ms: float
    body: Optional[str] = None
    error_type: Optional[str] = None
    calendar_slot_id: Optional[str] = None

    def is_success(self) -> bool:
        return 200 <= self.http_status < 300

    def is_timeout(self) -> bool:
        return self.http_status == 0 or self.error_type == "timeout"

    def is_invalid(self) -> bool:
        return self.http_status >= 400 or self.error_type == "invalid_response"


@dataclass
class DBState:
    """Snapshot of DB state for audit"""
    appointment_exists: bool
    slot_reserved: bool
    reservation_count: int


@dataclass
class Appointment:
    """Core appointment entity with idempotency and state tracking"""
    appointment_id: str
    request_id: str  # Client-provided idempotency key
    user_id: str
    patient_name: str
    appointment_date: str  # ISO format
    appointment_time: str
    calendar_slot_id: Optional[str]
    status: AppointmentStatus = AppointmentStatus.INIT
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    retry_count: int = 0
    last_error_code: Optional[ErrorCode] = None
    last_error_msg: Optional[str] = None
    compensation_action: Optional[str] = None  # DB_ROLLBACK, SLOT_RELEASE, NONE
    calendar_response_snapshot: Optional[Dict[str, Any]] = None
    db_state_snapshot: Optional[Dict[str, Any]] = None

    @staticmethod
    def create(user_id: str, patient_name: str, appointment_date: str,
               appointment_time: str, request_id: str) -> "Appointment":
        """Factory method to create new appointment"""
        return Appointment(
            appointment_id=f"apt_{uuid.uuid4().hex[:20]}",
            request_id=request_id,
            user_id=user_id,
            patient_name=patient_name,
            appointment_date=appointment_date,
            appointment_time=appointment_time,
            calendar_slot_id=None
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, handling Enum serialization"""
        data = asdict(self)
        data["status"] = self.status.value
        data["last_error_code"] = self.last_error_code.value if self.last_error_code else None
        data["created_at"] = self.created_at.isoformat()
        data["updated_at"] = self.updated_at.isoformat()
        return data


class AppointmentStateMachine:
    """State machine for appointment lifecycle with validation"""
    
    # Valid transitions: from_state -> [to_states]
    VALID_TRANSITIONS = {
        AppointmentStatus.INIT: [AppointmentStatus.IN_PROGRESS, AppointmentStatus.FAILURE],
        AppointmentStatus.IN_PROGRESS: [
            AppointmentStatus.SUCCESS,
            AppointmentStatus.FAILURE,
            AppointmentStatus.PARTIAL,
            AppointmentStatus.COMPENSATING
        ],
        AppointmentStatus.PARTIAL: [AppointmentStatus.SUCCESS, AppointmentStatus.FAILURE],
        AppointmentStatus.COMPENSATING: [AppointmentStatus.FAILURE, AppointmentStatus.SUCCESS],
        AppointmentStatus.SUCCESS: [],  # Terminal
        AppointmentStatus.FAILURE: [],  # Terminal
    }

    @staticmethod
    def can_transition(current: AppointmentStatus, target: AppointmentStatus) -> bool:
        """Check if transition is valid"""
        return target in AppointmentStateMachine.VALID_TRANSITIONS.get(current, [])

    @staticmethod
    def transition(appointment: Appointment, new_status: AppointmentStatus,
                   error_code: Optional[ErrorCode] = None,
                   error_msg: Optional[str] = None) -> bool:
        """Transition appointment to new status with validation"""
        if not AppointmentStateMachine.can_transition(appointment.status, new_status):
            return False
        
        appointment.status = new_status
        appointment.updated_at = datetime.utcnow()
        if error_code:
            appointment.last_error_code = error_code
        if error_msg:
            appointment.last_error_msg = error_msg
        
        return True


class IdempotencyStore:
    """In-memory idempotency store (production would use distributed cache/DB)"""
    
    def __init__(self):
        self._store: Dict[str, Dict[str, Any]] = {}

    def get(self, request_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve previous response for request_id"""
        return self._store.get(request_id)

    def set(self, request_id: str, response: Dict[str, Any]) -> None:
        """Store response for request_id"""
        self._store[request_id] = {
            "timestamp": datetime.utcnow().isoformat(),
            "response": response
        }

    def exists(self, request_id: str) -> bool:
        """Check if request_id has been processed"""
        return request_id in self._store


def hash_user_id(user_id: str, prefix_length: int = 8) -> str:
    """Redact user_id to hash prefix for audit logging"""
    return f"usr_{hashlib.sha256(user_id.encode()).hexdigest()[:prefix_length]}..."
