"""
Appointment Controller

HTTP API layer for appointment booking.
"""

import sys
import os
from typing import Dict, Any

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.appointment.saga import AppointmentSaga
from src.appointment.idempotency import generate_request_id


class AppointmentController:
    """
    HTTP controller for appointment booking API.
    
    Endpoints:
        POST /api/v2/appointments/confirm - Create new appointment
        GET /api/v2/appointments/<id>/status - Get appointment status
    """
    
    def __init__(self, saga: AppointmentSaga):
        """
        Initialize controller.
        
        Args:
            saga: Appointment saga orchestrator
        """
        self.saga = saga
    
    def create_appointment(
        self,
        request_data: Dict[str, Any],
        request_id: str = None
    ) -> tuple[Dict[str, Any], int]:
        """
        Create new appointment.
        
        Args:
            request_data: Request body with patient_id, doctor_id, appointment_time
            request_id: Optional X-Request-ID header (generated if not provided)
            
        Returns:
            Tuple of (response_dict, http_status_code)
        """
        # Generate request ID if not provided
        if not request_id:
            request_id = generate_request_id()
        
        # Validate required fields
        required_fields = ["patient_id", "doctor_id", "appointment_time"]
        missing_fields = [f for f in required_fields if f not in request_data]
        
        if missing_fields:
            field_list = ", ".join(missing_fields)
            return {
                "status": "failed",
                "error_code": "MISSING_REQUIRED_FIELDS",
                "error_message": f"Missing required fields: {field_list}",
                "request_id": request_id
            }, 400
        
        # Execute saga
        response = self.saga.execute(
            request_id=request_id,
            patient_id=request_data["patient_id"],
            doctor_id=request_data["doctor_id"],
            appointment_time=request_data["appointment_time"],
            **{k: v for k, v in request_data.items() if k not in required_fields}
        )
        
        # Determine HTTP status code
        status_code = self._get_status_code(response)
        
        return response, status_code
    
    def get_appointment_status(
        self,
        appointment_id: str
    ) -> tuple[Dict[str, Any], int]:
        """
        Get appointment status.
        
        Args:
            appointment_id: Appointment ID
            
        Returns:
            Tuple of (response_dict, http_status_code)
        """
        appointment = self.saga.db.get_appointment(appointment_id)
        
        if not appointment:
            return {
                "status": "failed",
                "error_code": "NOT_FOUND",
                "error_message": f"Appointment {appointment_id} not found"
            }, 404
        
        return {
            "appointment_id": appointment.appointment_id,
            "status": appointment.status,
            "patient_id": appointment.patient_id,
            "doctor_id": appointment.doctor_id,
            "appointment_time": appointment.appointment_time,
            "calendar_event_id": appointment.calendar_event_id,
            "created_at": appointment.created_at,
            "updated_at": appointment.updated_at
        }, 200
    
    def _get_status_code(self, response: Dict[str, Any]) -> int:
        """
        Determine HTTP status code from response.
        
        Args:
            response: Response dictionary
            
        Returns:
            HTTP status code
        """
        status = response.get("status")
        
        if status == "confirmed":
            # Check if idempotent
            if response.get("idempotent"):
                return 200  # OK (cached response)
            return 200  # OK (newly created)
        
        elif status == "in_progress":
            return 202  # Accepted (async processing)
        
        elif status == "failed":
            error_code = response.get("error_code")
            
            if error_code == "INVALID_REQUEST_ID":
                return 400  # Bad Request
            elif error_code == "RATE_LIMITED":
                return 429  # Too Many Requests
            elif error_code in ["SERVICE_UNAVAILABLE", "CALENDAR_SERVICE_ERROR"]:
                return 503  # Service Unavailable
            elif error_code == "DB_WRITE_FAILED":
                return 500  # Internal Server Error
            else:
                return 422  # Unprocessable Entity
        
        return 500  # Internal Server Error (unknown status)
