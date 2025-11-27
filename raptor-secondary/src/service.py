from starlette import status
from typing import Optional

from .db import AppointmentRepository
from .models import AppointmentState, ErrorCode
from .errors import AppException
from .calendar_adapter import CalendarAdapter
from .logging_utils import get_logger, log_duration

logger = get_logger(__name__)


class AppointmentService:
    def __init__(self, repo: Optional[AppointmentRepository] = None, calendar: Optional[CalendarAdapter] = None):
        self.repo = repo or AppointmentRepository()
        self.calendar = calendar or CalendarAdapter()

    def confirm(self, request_id: str, slot_id: str, patient_name: Optional[str] = None):
        # Idempotency handling
        existing = self.repo.get_by_request_id(request_id)
        if existing:
            logger.info("idempotent_request", extra={"request_id": request_id, "appointment_id": existing.id, "state": existing.state.value, "slot_id": existing.slot_id})
            return self._build_response(existing)

        # Slot availability check
        active_for_slot = self.repo.get_active_by_slot(slot_id)
        if active_for_slot:
            raise AppException("Slot already booked", code=ErrorCode.SLOT_ALREADY_BOOKED, http_status=status.HTTP_409_CONFLICT)

        # Create appointment in-progress
        appointment = self.repo.create(request_id=request_id, slot_id=slot_id, patient_name=patient_name)
        logger.info("appointment_created", extra={"request_id": request_id, "appointment_id": appointment.id, "state": appointment.state.value, "slot_id": slot_id})

        # Call calendar sync with retries and compensation
        with log_duration(logger, "calendar_sync", request_id, appointment.id, slot_id):
            success, error_code, detail = self.calendar.sync(appointment)

        if success:
            updated = self.repo.update_state(appointment.id, AppointmentState.CONFIRMED, calendar_synced=True)
            logger.info("appointment_confirmed", extra={"request_id": request_id, "appointment_id": appointment.id, "slot_id": slot_id, "state": updated.state.value})
            return self._build_response(updated)

        # Failure path -> compensation
        logger.warning("calendar_failed", extra={"request_id": request_id, "appointment_id": appointment.id, "slot_id": slot_id, "error_code": error_code.value if error_code else None, "error_detail": detail})
        comp_state = self.compensate(appointment, error_code, detail)
        raise AppException(comp_state.last_error_message or "Calendar sync failed", code=comp_state.last_error_code or ErrorCode.UNKNOWN, http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def compensate(self, appointment, error_code: Optional[ErrorCode], detail: str):
        # Mark compensating
        self.repo.update_state(appointment.id, AppointmentState.COMPENSATING, calendar_synced=False, last_error_code=error_code, last_error_message=detail)
        logger.info("compensation_started", extra={"request_id": appointment.request_id, "appointment_id": appointment.id, "slot_id": appointment.slot_id})
        # For this simulation, compensation is just releasing the slot by marking failure
        updated = self.repo.update_state(appointment.id, AppointmentState.FAILED, calendar_synced=False, last_error_code=error_code, last_error_message=detail)
        logger.info("compensation_completed", extra={"request_id": appointment.request_id, "appointment_id": appointment.id, "slot_id": appointment.slot_id, "state": updated.state.value})
        return updated

    def _build_response(self, app):
        if app.state == AppointmentState.CONFIRMED:
            return {
                "status": "success",
                "appointment_id": app.id,
                "request_id": app.request_id,
                "slot_id": app.slot_id,
                "state": app.state.value,
            }
        elif app.state in (AppointmentState.IN_PROGRESS, AppointmentState.COMPENSATING):
            return {
                "status": "in-progress",
                "appointment_id": app.id,
                "request_id": app.request_id,
                "slot_id": app.slot_id,
                "state": app.state.value,
            }
        elif app.state == AppointmentState.FAILED:
            return {
                "status": "failure",
                "appointment_id": app.id,
                "request_id": app.request_id,
                "slot_id": app.slot_id,
                "state": app.state.value,
                "error": {
                    "code": app.last_error_code.value if app.last_error_code else None,
                    "message": app.last_error_message,
                },
            }
        else:
            return {
                "status": "unknown",
                "appointment_id": app.id,
                "request_id": app.request_id,
                "slot_id": app.slot_id,
                "state": app.state.value,
            }
