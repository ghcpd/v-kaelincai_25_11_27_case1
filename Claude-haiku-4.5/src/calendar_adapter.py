"""
Calendar adapter with timeout, retry, and circuit breaker
Bridges appointment service with external calendar
"""
import time
from typing import Dict, Any, Optional
from src.models import CalendarResponse, ErrorCode, Appointment
from src.resilience import RetryPolicy, CircuitBreaker, RetryStrategy
from mocks.mock_calendar_service import MockCalendarService


class CalendarAdapter:
    """Adapter for calendar service with resilience patterns"""
    
    def __init__(
        self,
        calendar_service: MockCalendarService,
        timeout_sec: float = 5.0,
        max_retries: int = 2
    ):
        self.calendar_service = calendar_service
        self.timeout_sec = timeout_sec
        self.max_retries = max_retries
        
        # Retry policy with exponential backoff
        self.retry_policy = RetryPolicy(
            max_retries=max_retries,
            initial_delay_ms=100,
            max_delay_ms=1000,
            strategy=RetryStrategy.EXPONENTIAL,
            jitter=True
        )
        
        # Circuit breaker for calendar service
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout_sec=30,
            name="calendar_service"
        )

    def sync_appointment(
        self,
        appointment: Appointment,
        appointment_date: str,
        appointment_time: str,
        patient_email: str = "patient@redacted.local"
    ) -> CalendarResponse:
        """
        Sync appointment with calendar service
        
        Implements timeout, retry with backoff, and circuit breaker.
        
        Args:
            appointment: Appointment entity
            appointment_date: ISO date
            appointment_time: Time (HH:MM)
            patient_email: Patient email (redacted)
            
        Returns:
            CalendarResponse with status and result
        """
        
        def _call_calendar():
            """Inner function for retry logic"""
            start_time = time.time()
            
            # Call calendar service (simulated)
            response_dict = self.calendar_service.sync_appointment(
                appointment_date=appointment_date,
                appointment_time=appointment_time,
                patient_name=appointment.patient_name,
                patient_email=patient_email,
                request_id=appointment.request_id
            )
            
            elapsed_ms = (time.time() - start_time) * 1000
            
            # Check timeout
            if elapsed_ms > self.timeout_sec * 1000:
                raise TimeoutError(f"Calendar sync exceeded {self.timeout_sec}s timeout")
            
            # Check HTTP status
            if response_dict.get("http_status") == 0:
                raise TimeoutError("Calendar service timeout")
            
            if response_dict.get("http_status") >= 400:
                raise RuntimeError(f"Calendar returned {response_dict.get('http_status')}: "
                                 f"{response_dict.get('error', 'Unknown error')}")
            
            return response_dict
        
        try:
            # Attempt through circuit breaker with retry
            response_dict = self.circuit_breaker.call(
                self.retry_policy.retry,
                args=(_call_calendar,)
            )
            
            return CalendarResponse(
                http_status=response_dict.get("http_status", 0),
                response_time_ms=response_dict.get("response_time_ms", 0),
                body=str(response_dict),
                calendar_slot_id=response_dict.get("calendar_slot_id")
            )
        
        except TimeoutError as e:
            return CalendarResponse(
                http_status=0,
                response_time_ms=self.timeout_sec * 1000,
                error_type="timeout",
                body=str(e)
            )
        
        except RuntimeError as e:
            return CalendarResponse(
                http_status=500,
                response_time_ms=0,
                error_type="invalid_response",
                body=str(e)
            )
        
        except Exception as e:
            return CalendarResponse(
                http_status=500,
                response_time_ms=0,
                error_type="internal_error",
                body=str(e)
            )

    def get_status(self) -> Dict[str, Any]:
        """Get adapter and circuit breaker status"""
        return {
            "timeout_sec": self.timeout_sec,
            "max_retries": self.max_retries,
            "circuit_breaker": self.circuit_breaker.status()
        }
