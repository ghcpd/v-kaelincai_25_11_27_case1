"""
Appointment Booking Saga Orchestrator

Coordinates the appointment booking workflow with state management,
retry logic, and compensation handling.
"""

import sys
import os
import uuid
import time
from typing import Dict, Any, Optional

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.appointment.state_machine import (
    AppointmentState,
    AppointmentStateMachine,
    InvalidStateTransitionError
)
from src.appointment.idempotency import IdempotencyManager, validate_request_id
from src.appointment.database import InMemoryDatabase
from src.appointment.audit_logger import AuditLogger
from src.adapters.calendar_adapter import (
    CalendarAdapter,
    CircuitBreakerOpenError
)
from mocks.mock_calendar_service import (
    CalendarTimeoutException,
    CalendarRateLimitException,
    CalendarServiceException,
    CalendarMalformedResponseException
)


class AppointmentSaga:
    """
    Saga orchestrator for appointment booking.
    
    Implements the following workflow:
        1. Validate request and check idempotency
        2. Create appointment record (DB)
        3. Sync with calendar service (external API)
        4. Confirm or compensate based on result
    
    Features:
        - State machine tracking
        - Idempotency protection
        - Retry logic via calendar adapter
        - Compensation on failure
        - Structured audit logging
    """
    
    def __init__(
        self,
        database: InMemoryDatabase,
        calendar_adapter: CalendarAdapter,
        idempotency_manager: IdempotencyManager,
        audit_logger: AuditLogger
    ):
        """
        Initialize saga orchestrator.
        
        Args:
            database: Database for appointment storage
            calendar_adapter: Calendar service adapter
            idempotency_manager: Idempotency cache manager
            audit_logger: Structured audit logger
        """
        self.db = database
        self.calendar = calendar_adapter
        self.idempotency = idempotency_manager
        self.logger = audit_logger
    
    def execute(
        self,
        request_id: str,
        patient_id: str,
        doctor_id: str,
        appointment_time: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Execute appointment booking saga.
        
        Args:
            request_id: Unique request ID (for idempotency)
            patient_id: Patient identifier
            doctor_id: Doctor identifier
            appointment_time: ISO 8601 timestamp
            **kwargs: Additional appointment data
            
        Returns:
            Response dict with status, appointment_id, and details
        """
        start_time = time.time()
        
        # Log incoming request
        self.logger.log_request_received(
            request_id=request_id,
            appointment_data={
                "patient_id": patient_id,
                "doctor_id": doctor_id,
                "appointment_time": appointment_time,
                **kwargs
            }
        )
        
        # Step 0: Validate request ID
        if not validate_request_id(request_id):
            return self._error_response(
                request_id=request_id,
                error_code="INVALID_REQUEST_ID",
                error_message="Request ID must be 8-128 characters"
            )
        
        # Step 1: Check idempotency (duplicate request?)
        cached_response = self.idempotency.get_cached_response(request_id)
        if cached_response:
            # Return cached response
            appointment_id = cached_response.get("appointment_id")
            self.logger.log_idempotency_hit(request_id, appointment_id)
            
            cached_response["idempotent"] = True
            return cached_response
        
        # Step 2: Execute saga workflow
        try:
            response = self._execute_workflow(
                request_id,
                patient_id,
                doctor_id,
                appointment_time,
                kwargs
            )
            
            # Cache successful or terminal failure responses
            if response["status"] in ["confirmed", "failed"]:
                self.idempotency.store_response(request_id, response)
            
            # Log total duration
            duration_ms = int((time.time() - start_time) * 1000)
            self.logger.log(
                level="INFO",
                action="saga_complete",
                request_id=request_id,
                appointment_id=response.get("appointment_id"),
                duration_ms=duration_ms,
                metadata={"status": response["status"]}
            )
            
            return response
        
        except Exception as e:
            # Unhandled exception (should not happen)
            duration_ms = int((time.time() - start_time) * 1000)
            self.logger.log(
                level="ERROR",
                action="saga_error",
                request_id=request_id,
                error=str(e),
                duration_ms=duration_ms
            )
            
            return self._error_response(
                request_id=request_id,
                error_code="INTERNAL_ERROR",
                error_message=f"Unexpected error: {str(e)}"
            )
    
    def _execute_workflow(
        self,
        request_id: str,
        patient_id: str,
        doctor_id: str,
        appointment_time: str,
        metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute the saga workflow steps"""
        
        appointment_id = f"apt-{uuid.uuid4().hex[:8]}"
        state_machine = AppointmentStateMachine()
        
        # Step 1: Initialize state
        self._transition_state(
            state_machine,
            appointment_id,
            request_id,
            AppointmentState.INITIATED
        )
        
        # Step 2: Create appointment record in DB
        try:
            self._transition_state(
                state_machine,
                appointment_id,
                request_id,
                AppointmentState.IN_PROGRESS
            )
            
            self.db.create_appointment(
                appointment_id=appointment_id,
                request_id=request_id,
                patient_id=patient_id,
                doctor_id=doctor_id,
                appointment_time=appointment_time,
                status=AppointmentState.IN_PROGRESS.value,
                metadata=metadata
            )
        
        except Exception as e:
            # DB write failed - immediate failure
            self._transition_state(
                state_machine,
                appointment_id,
                request_id,
                AppointmentState.FAILED,
                metadata={"error": str(e)}
            )
            
            return self._error_response(
                request_id=request_id,
                error_code="DB_WRITE_FAILED",
                error_message=f"Failed to create appointment: {str(e)}"
            )
        
        # Step 3: Sync with calendar service
        calendar_event_id = None
        try:
            self._transition_state(
                state_machine,
                appointment_id,
                request_id,
                AppointmentState.CALENDAR_SYNCING
            )
            
            sync_start = time.time()
            self.logger.log_calendar_sync_start(request_id, appointment_id)
            
            calendar_result = self.calendar.create_event(
                appointment_id=appointment_id,
                patient_id=patient_id,
                doctor_id=doctor_id,
                appointment_time=appointment_time
            )
            
            sync_duration = int((time.time() - sync_start) * 1000)
            calendar_event_id = calendar_result.get("event_id")
            
            self.logger.log_calendar_sync_success(
                request_id,
                appointment_id,
                calendar_event_id,
                sync_duration
            )
        
        except CalendarTimeoutException as e:
            # Timeout - transition to PENDING_RETRY
            sync_duration = int((time.time() - sync_start) * 1000)
            self.logger.log_calendar_sync_failure(
                request_id,
                appointment_id,
                "timeout",
                sync_duration
            )
            
            self._transition_state(
                state_machine,
                appointment_id,
                request_id,
                AppointmentState.PENDING_RETRY,
                metadata={"error": "timeout", "retry_scheduled": True}
            )
            
            self.db.update_appointment_status(
                appointment_id,
                AppointmentState.PENDING_RETRY.value
            )
            
            # Return 202 Accepted (async processing)
            return {
                "status": "in_progress",
                "appointment_id": appointment_id,
                "request_id": request_id,
                "message": "Calendar sync timed out. Appointment queued for retry.",
                "poll_url": f"/api/v2/appointments/{appointment_id}/status"
            }
        
        except CircuitBreakerOpenError as e:
            # Circuit breaker open - fail fast
            sync_duration = int((time.time() - sync_start) * 1000)
            self.logger.log_circuit_breaker_open(request_id, "calendar_service")
            self.logger.log_calendar_sync_failure(
                request_id,
                appointment_id,
                "circuit_breaker_open",
                sync_duration
            )
            
            # Compensate (delete appointment)
            self._compensate(state_machine, appointment_id, request_id, "Circuit breaker open")
            
            return self._error_response(
                request_id=request_id,
                appointment_id=appointment_id,
                error_code="SERVICE_UNAVAILABLE",
                error_message="Calendar service is temporarily unavailable. Please try again later.",
                retry_after=30
            )
        
        except (CalendarRateLimitException, CalendarServiceException, CalendarMalformedResponseException) as e:
            # Calendar service error - compensate
            sync_duration = int((time.time() - sync_start) * 1000)
            error_type = type(e).__name__
            
            self.logger.log_calendar_sync_failure(
                request_id,
                appointment_id,
                error_type,
                sync_duration
            )
            
            # Compensate (delete appointment)
            self._compensate(state_machine, appointment_id, request_id, error_type)
            
            # Determine error code and retry_after
            if isinstance(e, CalendarRateLimitException):
                error_code = "RATE_LIMITED"
                retry_after = getattr(e, 'retry_after', 60)
            else:
                error_code = "CALENDAR_SERVICE_ERROR"
                retry_after = None
            
            return self._error_response(
                request_id=request_id,
                appointment_id=appointment_id,
                error_code=error_code,
                error_message=str(e),
                retry_after=retry_after
            )
        
        # Step 4: Confirm booking (both DB and calendar succeeded)
        self._transition_state(
            state_machine,
            appointment_id,
            request_id,
            AppointmentState.CONFIRMED,
            metadata={"calendar_event_id": calendar_event_id}
        )
        
        self.db.update_appointment_status(
            appointment_id,
            AppointmentState.CONFIRMED.value,
            calendar_event_id=calendar_event_id
        )
        
        return {
            "status": "confirmed",
            "appointment_id": appointment_id,
            "request_id": request_id,
            "calendar_event_id": calendar_event_id,
            "appointment_time": appointment_time,
            "message": "Appointment confirmed successfully"
        }
    
    def _compensate(
        self,
        state_machine: AppointmentStateMachine,
        appointment_id: str,
        request_id: str,
        reason: str
    ):
        """
        Execute compensation (rollback) logic.
        
        Args:
            state_machine: State machine instance
            appointment_id: Appointment ID
            request_id: Request ID
            reason: Reason for compensation
        """
        self.logger.log_compensation_start(request_id, appointment_id, reason)
        
        # Transition to compensating state
        self._transition_state(
            state_machine,
            appointment_id,
            request_id,
            AppointmentState.COMPENSATING,
            metadata={"reason": reason}
        )
        
        actions_taken = []
        
        # Delete appointment from DB
        if self.db.delete_appointment(appointment_id):
            actions_taken.append("deleted_appointment_record")
        
        # Note: If calendar event was created, delete it
        # (In our flow, we compensate before calendar success, so this won't happen)
        
        # Transition to failed state
        self._transition_state(
            state_machine,
            appointment_id,
            request_id,
            AppointmentState.FAILED,
            metadata={"compensation_reason": reason}
        )
        
        self.logger.log_compensation_complete(request_id, appointment_id, actions_taken)
    
    def _transition_state(
        self,
        state_machine: AppointmentStateMachine,
        appointment_id: str,
        request_id: str,
        to_state: AppointmentState,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Transition state and log to audit.
        
        Args:
            state_machine: State machine instance
            appointment_id: Appointment ID
            request_id: Request ID
            to_state: Target state
            metadata: Optional metadata
        """
        from_state = state_machine.get_current_state()
        
        transition = state_machine.transition(
            appointment_id=appointment_id,
            request_id=request_id,
            to_state=to_state,
            metadata=metadata
        )
        
        # Log to database
        self.db.record_state_transition(
            appointment_id=appointment_id,
            request_id=request_id,
            from_state=from_state.value if from_state else None,
            to_state=to_state.value,
            metadata=metadata
        )
        
        # Log to audit logger
        self.logger.log_state_transition(
            request_id=request_id,
            appointment_id=appointment_id,
            from_state=from_state.value if from_state else None,
            to_state=to_state.value,
            metadata=metadata
        )
    
    def _error_response(
        self,
        request_id: str,
        error_code: str,
        error_message: str,
        appointment_id: Optional[str] = None,
        retry_after: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Create error response.
        
        Args:
            request_id: Request ID
            error_code: Error code
            error_message: Error message
            appointment_id: Optional appointment ID
            retry_after: Optional retry delay in seconds
            
        Returns:
            Error response dict
        """
        response = {
            "status": "failed",
            "request_id": request_id,
            "error_code": error_code,
            "error_message": error_message
        }
        
        if appointment_id:
            response["appointment_id"] = appointment_id
        
        if retry_after:
            response["retry_after"] = retry_after
        
        return response
