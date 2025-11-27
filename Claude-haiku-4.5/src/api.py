"""
Flask API for Appointment Booking
Provides REST endpoints for appointment management
"""
from flask import Flask, request, jsonify
from typing import Tuple, Dict, Any
import uuid
import json

from src.models import Appointment
from src.appointment_service import AppointmentService
from src.calendar_adapter import CalendarAdapter
from src.database import get_database, reset_database
from src.audit_logger import AuditLogger
from mocks.mock_calendar_service import get_calendar_service, reset_calendar_service


def create_app(test_mode: bool = False) -> Flask:
    """Create and configure Flask app"""
    app = Flask(__name__)

    # Initialize services
    db = get_database()
    calendar_service = get_calendar_service()
    calendar_adapter = CalendarAdapter(calendar_service, timeout_sec=5.0, max_retries=2)
    audit_logger = AuditLogger()
    appointment_service = AppointmentService(db, calendar_adapter, audit_logger)

    @app.route("/api/health", methods=["GET"])
    def health():
        """Health check endpoint"""
        return jsonify({"status": "ok", "service": "appointment-booking-v2"}), 200

    @app.route("/api/appointments", methods=["POST"])
    def create_appointment():
        """
        Create appointment (with idempotency via request_id)
        
        Request body:
        {
            "user_id": "user123",
            "patient_name": "John Doe",
            "appointment_date": "2025-12-15",
            "appointment_time": "14:30",
            "request_id": "req_unique_id"  # Client-provided idempotency key
        }
        
        Response: 200/201 on success with appointment details
                  400/500 on failure with error details
        """
        try:
            data = request.get_json()
            
            # Validate required fields
            required = ["user_id", "patient_name", "appointment_date", "appointment_time", "request_id"]
            missing = [f for f in required if f not in data]
            if missing:
                return jsonify({"error": f"Missing fields: {missing}"}), 400

            # Request appointment
            success, response = appointment_service.request_appointment(
                user_id=data["user_id"],
                patient_name=data["patient_name"],
                appointment_date=data["appointment_date"],
                appointment_time=data["appointment_time"],
                request_id=data["request_id"]
            )

            status_code = 201 if success else 500
            return jsonify(response), status_code

        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/appointments/<appointment_id>", methods=["GET"])
    def get_appointment(appointment_id: str):
        """Get appointment details"""
        appointment = appointment_service.get_appointment(appointment_id)
        if appointment:
            return jsonify(appointment), 200
        return jsonify({"error": "Appointment not found"}), 404

    @app.route("/api/stats", methods=["GET"])
    def get_stats():
        """Get system statistics"""
        stats = appointment_service.get_stats()
        return jsonify(stats), 200

    @app.route("/api/admin/reset", methods=["POST"])
    def admin_reset():
        """
        Admin endpoint to reset all state (for testing)
        WARNING: Deletes all appointments and resets mock service
        """
        reset_database()
        reset_calendar_service()
        return jsonify({"message": "All state reset"}), 200

    @app.route("/api/admin/mock-config", methods=["POST"])
    def admin_mock_config():
        """
        Admin endpoint to configure mock calendar behavior
        
        Request body:
        {
            "error_mode": "timeout|success|invalid_response|server_error",
            "timeout_ms": 3000
        }
        """
        try:
            data = request.get_json()
            error_mode_str = data.get("error_mode", "success").upper()
            timeout_ms = data.get("timeout_ms", 3000)

            from mocks.mock_calendar_service import MockCalendarErrorMode
            error_mode = MockCalendarErrorMode[error_mode_str]
            calendar_service.set_error_mode(error_mode, timeout_ms)

            return jsonify({
                "message": "Mock calendar configured",
                "error_mode": error_mode.value,
                "timeout_ms": timeout_ms
            }), 200

        except Exception as e:
            return jsonify({"error": str(e)}), 400

    if test_mode:
        app.config["TESTING"] = True

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=5000)
