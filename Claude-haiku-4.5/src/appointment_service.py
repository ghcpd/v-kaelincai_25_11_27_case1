"""
Appointment service with compensation and idempotency
Orchestrates the booking flow with error handling and recovery
"""
import time
from typing import Dict, Any, Optional, Tuple
from enum import Enum

from src.models import (
    Appointment, AppointmentStatus, ErrorCode, AppointmentStateMachine,
    IdempotencyStore, CalendarResponse
)
from src.audit_logger import AuditLogger, EventType
from src.calendar_adapter import CalendarAdapter
from src.database import AppointmentDatabase


class CompensationAction(Enum):
    """Compensation strategies"""
    DB_ROLLBACK = "DB_ROLLBACK"
    SLOT_RELEASE = "SLOT_RELEASE"
    NONE = "NONE"


class AppointmentService:
    """
    Service for appointment booking with:
    - Idempotency via request ID
    - State machine transitions
    - Compensation/rollback on failure
    - Structured audit logging
    """
    
    def __init__(
        self,
        database: AppointmentDatabase,
        calendar_adapter: CalendarAdapter,
        audit_logger: AuditLogger
    ):
        self.db = database
        self.calendar_adapter = calendar_adapter
        self.audit_logger = audit_logger
        self.idempotency_store = IdempotencyStore()

    def request_appointment(
        self,
        user_id: str,
        patient_name: str,
        appointment_date: str,
        appointment_time: str,
        request_id: str  # Client-provided idempotency key
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Request new appointment with idempotency
        
        Flow:
        1. Check idempotency (duplicate request)
        2. Create appointment (INIT state)
        3. Reserve slot in DB (IN_PROGRESS)
        4. Sync with calendar
        5. On success: mark SUCCESS
        6. On failure: compensate (rollback) and mark FAILURE
        
        Args:
            user_id: User ID
            patient_name: Patient name
            appointment_date: ISO date
            appointment_time: Time (HH:MM)
            request_id: Client request ID for idempotency
            
        Returns:
            (success: bool, response: Dict)
        """
        start_time = time.time()

        # Step 1: Check idempotency
        existing = self.db.get_by_request_id(request_id)
        if existing:
            self.audit_logger.log_idempotency_hit(request_id, existing)
            return True, self._format_response(existing, is_idempotency_hit=True)

        # Step 2: Create appointment
        appointment = Appointment.create(
            user_id=user_id,
            patient_name=patient_name,
            appointment_date=appointment_date,
            appointment_time=appointment_time,
            request_id=request_id
        )

        # Log creation
        self.audit_logger.log_event(
            EventType.APPOINTMENT_INIT,
            appointment,
            message="Appointment creation initiated"
        )

        # Step 3: Persist appointment (reserve locally)
        if not self.db.create(appointment):
            AppointmentStateMachine.transition(
                appointment,
                AppointmentStatus.FAILURE,
                ErrorCode.DB_ERROR,
                "Failed to create appointment in database"
            )
            self.audit_logger.log_event(
                EventType.DB_RESERVE_FAILED,
                appointment,
                error_code=ErrorCode.DB_ERROR,
                message="DB creation failed"
            )
            return False, self._format_response(appointment)

        # Update state to IN_PROGRESS
        AppointmentStateMachine.transition(
            appointment,
            AppointmentStatus.IN_PROGRESS
        )
        self.db.update(appointment)

        self.audit_logger.log_event(
            EventType.DB_RESERVE_START,
            appointment,
            message="Starting calendar synchronization"
        )

        # Step 4: Sync with calendar
        calendar_response = self.calendar_adapter.sync_appointment(
            appointment,
            appointment_date,
            appointment_time
        )

        elapsed_ms = (time.time() - start_time) * 1000

        # Log calendar sync attempt
        if calendar_response.is_success():
            event_type = EventType.CALENDAR_SYNC_SUCCESS
            error_code = ErrorCode.SUCCESS
        elif calendar_response.is_timeout():
            event_type = EventType.CALENDAR_SYNC_TIMEOUT
            error_code = ErrorCode.CALENDAR_TIMEOUT
        else:
            event_type = EventType.CALENDAR_SYNC_ERROR
            error_code = ErrorCode.CALENDAR_INVALID_RESPONSE

        calendar_response_snapshot = {
            "http_status": calendar_response.http_status,
            "response_time_ms": calendar_response.response_time_ms,
            "error_type": calendar_response.error_type
        }

        db_state_snapshot = {
            "appointment_exists": self.db.get_by_id(appointment.appointment_id) is not None,
            "slot_reserved": False,
            "reservation_count": 0
        }

        self.audit_logger.log_event(
            event_type,
            appointment,
            duration_ms=calendar_response.response_time_ms,
            error_code=error_code if event_type != EventType.CALENDAR_SYNC_SUCCESS else None,
            calendar_response=calendar_response_snapshot,
            db_state=db_state_snapshot
        )

        # Step 5: Handle calendar response
        if calendar_response.is_success():
            # Success: reserve slot and mark SUCCESS
            appointment.calendar_slot_id = calendar_response.calendar_slot_id
            self.db.reserve_slot(appointment.appointment_id, calendar_response.calendar_slot_id)

            AppointmentStateMachine.transition(
                appointment,
                AppointmentStatus.SUCCESS
            )
            appointment.last_error_code = ErrorCode.SUCCESS
            self.db.update(appointment)

            self.audit_logger.log_event(
                EventType.FINAL_SUCCESS,
                appointment,
                duration_ms=elapsed_ms,
                error_code=ErrorCode.SUCCESS,
                message="Appointment successfully booked and synchronized"
            )

            return True, self._format_response(appointment)

        else:
            # Step 6: Failure - trigger compensation
            return self._handle_calendar_failure(
                appointment,
                calendar_response,
                error_code,
                elapsed_ms
            )

    def _handle_calendar_failure(
        self,
        appointment: Appointment,
        calendar_response: CalendarResponse,
        error_code: ErrorCode,
        elapsed_ms: float
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Handle calendar sync failure with compensation
        
        Applies compensation strategy based on appointment state:
        - If DB record exists but calendar sync failed: rollback DB
        - Transition to FAILURE state
        """
        # Determine compensation action
        compensation_action = CompensationAction.DB_ROLLBACK

        # Log compensation trigger
        self.audit_logger.log_event(
            EventType.COMPENSATION_TRIGGERED,
            appointment,
            message=f"Triggering {compensation_action.value} due to calendar sync failure",
            error_code=error_code,
            compensation_action=compensation_action.value
        )

        # Execute compensation: delete appointment from DB
        if self.db.delete(appointment.appointment_id):
            AppointmentStateMachine.transition(
                appointment,
                AppointmentStatus.FAILURE,
                error_code=error_code
            )

            self.audit_logger.log_event(
                EventType.COMPENSATION_SUCCESS,
                appointment,
                message="DB rollback completed successfully",
                compensation_action=compensation_action.value,
                db_state={
                    "appointment_exists": False,
                    "slot_reserved": False,
                    "reservation_count": 0
                }
            )
        else:
            # Compensation failed - mark as partial
            AppointmentStateMachine.transition(
                appointment,
                AppointmentStatus.PARTIAL,
                error_code=error_code
            )

            self.audit_logger.log_event(
                EventType.COMPENSATION_FAILED,
                appointment,
                message="DB rollback failed - appointment may be in inconsistent state",
                error_code=error_code,
                compensation_action=compensation_action.value
            )

        self.audit_logger.log_event(
            EventType.FINAL_FAILURE,
            appointment,
            duration_ms=elapsed_ms,
            error_code=error_code,
            message=f"Appointment booking failed: {calendar_response.error_type}"
        )

        return False, self._format_response(appointment)

    def get_appointment(self, appointment_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve appointment details"""
        appointment = self.db.get_by_id(appointment_id)
        if appointment:
            return self._format_response(appointment)
        return None

    def _format_response(
        self,
        appointment: Appointment,
        is_idempotency_hit: bool = False
    ) -> Dict[str, Any]:
        """Format appointment as API response"""
        response = {
            "appointment_id": appointment.appointment_id,
            "request_id": appointment.request_id,
            "status": appointment.status.value,
            "patient_name": appointment.patient_name,
            "appointment_date": appointment.appointment_date,
            "appointment_time": appointment.appointment_time,
            "calendar_slot_id": appointment.calendar_slot_id,
            "retry_count": appointment.retry_count,
            "error_code": appointment.last_error_code.value if appointment.last_error_code else None,
            "error_message": appointment.last_error_msg,
            "is_idempotency_hit": is_idempotency_hit,
            "created_at": appointment.created_at.isoformat(),
            "updated_at": appointment.updated_at.isoformat()
        }
        return response

    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics"""
        return {
            "database": self.db.get_stats(),
            "calendar_adapter": self.calendar_adapter.get_status(),
            "idempotency_store": {
                "cached_requests": len(self.idempotency_store._store)
            }
        }
