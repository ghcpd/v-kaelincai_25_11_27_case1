"""
Mock calendar service for testing
Simulates external calendar service with controllable delays and errors
"""
import time
import random
from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime, timedelta


class MockCalendarErrorMode(Enum):
    """Error modes for mock calendar"""
    SUCCESS = "success"
    TIMEOUT = "timeout"
    INVALID_RESPONSE = "invalid_response"
    SERVER_ERROR = "server_error"
    RANDOM = "random"


class MockCalendarService:
    """Simulated calendar service with controllable behavior"""
    
    def __init__(self, default_delay_ms: float = 100.0):
        self.default_delay_ms = default_delay_ms
        self.error_mode = MockCalendarErrorMode.SUCCESS
        self.timeout_threshold_ms = 3000
        self.call_count = 0
        self.call_history: list[Dict[str, Any]] = []

    def set_error_mode(self, mode: MockCalendarErrorMode, timeout_ms: float = 3000) -> None:
        """Configure error behavior for next calls"""
        self.error_mode = mode
        self.timeout_threshold_ms = timeout_ms

    def sync_appointment(
        self,
        appointment_date: str,
        appointment_time: str,
        patient_name: str,
        patient_email: str,
        request_id: str
    ) -> Dict[str, Any]:
        """
        Sync appointment with calendar
        
        Simulates HTTP call to external calendar service.
        Returns response dict with status, timing, and optional error.
        
        Args:
            appointment_date: ISO date string
            appointment_time: Time string (HH:MM)
            patient_name: Patient name
            patient_email: Patient email (redacted)
            request_id: Client request ID for correlation
            
        Returns:
            Dict with 'status', 'calendar_slot_id', 'response_time_ms', optional 'error'
        """
        self.call_count += 1
        start_time = time.time()

        # Determine response behavior
        error_mode = self.error_mode
        if error_mode == MockCalendarErrorMode.RANDOM:
            error_mode = random.choice([
                MockCalendarErrorMode.SUCCESS,
                MockCalendarErrorMode.TIMEOUT,
                MockCalendarErrorMode.INVALID_RESPONSE,
                MockCalendarErrorMode.SERVER_ERROR
            ])

        # Simulate delay
        base_delay = self.default_delay_ms
        if error_mode == MockCalendarErrorMode.TIMEOUT:
            delay = self.timeout_threshold_ms + random.uniform(500, 2000)
        else:
            delay = base_delay + random.uniform(-base_delay * 0.1, base_delay * 0.3)

        time.sleep(delay / 1000.0)
        elapsed_ms = (time.time() - start_time) * 1000

        # Build response
        response = {
            "request_id": request_id,
            "appointment_date": appointment_date,
            "appointment_time": appointment_time,
            "response_time_ms": elapsed_ms,
            "http_status": 200,
            "calendar_slot_id": None,
            "error": None
        }

        # Apply error behavior
        if error_mode == MockCalendarErrorMode.SUCCESS:
            response["http_status"] = 200
            response["calendar_slot_id"] = f"cal_slot_{self.call_count}_{int(time.time() * 1000)}"
            response["message"] = "Appointment synchronized successfully"

        elif error_mode == MockCalendarErrorMode.TIMEOUT:
            response["http_status"] = 0  # Timeout
            response["error"] = "Connection timeout"
            response["error_type"] = "timeout"

        elif error_mode == MockCalendarErrorMode.INVALID_RESPONSE:
            response["http_status"] = 500
            response["error"] = "Invalid calendar response format"
            response["error_type"] = "invalid_response"

        elif error_mode == MockCalendarErrorMode.SERVER_ERROR:
            response["http_status"] = 503
            response["error"] = "Calendar service unavailable"
            response["error_type"] = "server_error"

        # Log call
        self.call_history.append({
            "timestamp": datetime.utcnow().isoformat(),
            "request_id": request_id,
            "error_mode": error_mode.value,
            "response": response
        })

        return response

    def get_stats(self) -> Dict[str, Any]:
        """Get mock service statistics"""
        return {
            "total_calls": self.call_count,
            "call_history_size": len(self.call_history),
            "current_error_mode": self.error_mode.value,
            "default_delay_ms": self.default_delay_ms
        }

    def reset(self) -> None:
        """Reset mock service state"""
        self.call_count = 0
        self.call_history.clear()
        self.error_mode = MockCalendarErrorMode.SUCCESS


# Global singleton instance
_calendar_service: Optional[MockCalendarService] = None


def get_calendar_service() -> MockCalendarService:
    """Get or create mock calendar service singleton"""
    global _calendar_service
    if _calendar_service is None:
        _calendar_service = MockCalendarService()
    return _calendar_service


def reset_calendar_service() -> None:
    """Reset the mock calendar service for testing"""
    global _calendar_service
    if _calendar_service is not None:
        _calendar_service.reset()
