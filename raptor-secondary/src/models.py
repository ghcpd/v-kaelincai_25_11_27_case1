from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime


class AppointmentState(str, Enum):
    INIT = "INIT"
    IN_PROGRESS = "IN_PROGRESS"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    COMPENSATING = "COMPENSATING"
    COMPENSATED = "COMPENSATED"


class ErrorCode(str, Enum):
    CALENDAR_TIMEOUT = "CALENDAR_TIMEOUT"
    CALENDAR_EXCEPTION = "CALENDAR_EXCEPTION"
    CALENDAR_MALFORMED = "CALENDAR_MALFORMED"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"
    SLOT_ALREADY_BOOKED = "SLOT_ALREADY_BOOKED"
    UNKNOWN = "UNKNOWN"


@dataclass
class Appointment:
    id: str
    request_id: str
    slot_id: str
    patient_name: Optional[str] = None
    state: AppointmentState = AppointmentState.INIT
    calendar_synced: bool = False
    retry_count: int = 0
    last_error_code: Optional[ErrorCode] = None
    last_error_message: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "request_id": self.request_id,
            "slot_id": self.slot_id,
            "patient_name": self.patient_name,
            "state": self.state.value,
            "calendar_synced": self.calendar_synced,
            "retry_count": self.retry_count,
            "last_error_code": self.last_error_code.value if self.last_error_code else None,
            "last_error_message": self.last_error_message,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
