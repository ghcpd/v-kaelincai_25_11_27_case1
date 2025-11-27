"""
Calendar Adapter with Retry Logic and Circuit Breaker

Handles communication with external calendar service with resilience patterns.
"""

import time
from typing import Dict, Any, Optional
from datetime import datetime
import sys
import os

# Add mocks directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from mocks.mock_calendar_service import (
    MockCalendarService,
    CalendarTimeoutException,
    CalendarRateLimitException,
    CalendarServiceException,
    CalendarMalformedResponseException
)


class CircuitBreakerState:
    """Simple circuit breaker implementation"""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitBreaker:
    """
    Circuit breaker to prevent cascading failures.
    
    States:
        - CLOSED: Normal operation
        - OPEN: Too many failures, reject requests immediately
        - HALF_OPEN: Allow one test request to check recovery
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        timeout_seconds: int = 30,
        name: str = "calendar_service"
    ):
        """
        Initialize circuit breaker.
        
        Args:
            failure_threshold: Number of consecutive failures before opening
            timeout_seconds: Time to wait before attempting recovery (HALF_OPEN)
            name: Circuit breaker name for logging
        """
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.name = name
        
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.enable_logging = True
    
    def call(self, func, *args, **kwargs):
        """
        Execute function with circuit breaker protection.
        
        Args:
            func: Function to execute
            *args, **kwargs: Function arguments
            
        Returns:
            Function result
            
        Raises:
            CircuitBreakerOpenError: If circuit is open
            Original exception: If function fails
        """
        if self.state == CircuitBreakerState.OPEN:
            # Check if timeout has passed
            if self._should_attempt_reset():
                self._transition_to_half_open()
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit breaker '{self.name}' is OPEN. "
                    f"Retry after {self._time_until_retry():.1f}s"
                )
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise
    
    def _on_success(self):
        """Handle successful call"""
        if self.state == CircuitBreakerState.HALF_OPEN:
            self._transition_to_closed()
        self.failure_count = 0
    
    def _on_failure(self):
        """Handle failed call"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.state == CircuitBreakerState.HALF_OPEN:
            # Failed during recovery test, go back to OPEN
            self._transition_to_open()
        elif self.failure_count >= self.failure_threshold:
            self._transition_to_open()
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset"""
        if self.last_failure_time is None:
            return False
        return time.time() - self.last_failure_time >= self.timeout_seconds
    
    def _time_until_retry(self) -> float:
        """Calculate time remaining until retry attempt"""
        if self.last_failure_time is None:
            return 0
        elapsed = time.time() - self.last_failure_time
        return max(0, self.timeout_seconds - elapsed)
    
    def _transition_to_open(self):
        """Transition to OPEN state"""
        if self.state != CircuitBreakerState.OPEN:
            self.state = CircuitBreakerState.OPEN
            if self.enable_logging:
                print(f"[CircuitBreaker:{self.name}] ⚠️  OPENED (failures={self.failure_count})")
    
    def _transition_to_half_open(self):
        """Transition to HALF_OPEN state"""
        self.state = CircuitBreakerState.HALF_OPEN
        if self.enable_logging:
            print(f"[CircuitBreaker:{self.name}] 🔄 HALF_OPEN (testing recovery)")
    
    def _transition_to_closed(self):
        """Transition to CLOSED state"""
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        if self.enable_logging:
            print(f"[CircuitBreaker:{self.name}] ✅ CLOSED (recovered)")
    
    def get_state(self) -> str:
        """Get current circuit breaker state"""
        return self.state
    
    def reset(self):
        """Manually reset circuit breaker (for testing)"""
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
        if self.enable_logging:
            print(f"[CircuitBreaker:{self.name}] 🔄 Manually reset")


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open"""
    pass


class CalendarAdapter:
    """
    Adapter for external calendar service with retry and circuit breaker.
    
    Features:
        - Exponential backoff retry (1s, 2s, 4s)
        - Circuit breaker (fail after 5 consecutive errors)
        - Timeout handling
        - Exception normalization
    """
    
    def __init__(
        self,
        calendar_service: MockCalendarService,
        max_retries: int = 3,
        timeout_seconds: float = 10.0,
        enable_circuit_breaker: bool = True
    ):
        """
        Initialize calendar adapter.
        
        Args:
            calendar_service: Underlying calendar service (real or mock)
            max_retries: Maximum retry attempts
            timeout_seconds: Timeout per request
            enable_circuit_breaker: Enable circuit breaker protection
        """
        self.calendar_service = calendar_service
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds
        self.enable_circuit_breaker = enable_circuit_breaker
        
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            timeout_seconds=30,
            name="calendar_service"
        )
        
        self.enable_logging = True
    
    def create_event(
        self,
        appointment_id: str,
        patient_id: str,
        doctor_id: str,
        appointment_time: str
    ) -> Dict[str, Any]:
        """
        Create calendar event with retry and circuit breaker.
        
        Args:
            appointment_id: Unique appointment ID
            patient_id: Patient identifier
            doctor_id: Doctor identifier
            appointment_time: ISO 8601 timestamp
            
        Returns:
            Calendar event data with event_id
            
        Raises:
            CalendarTimeoutException: On timeout
            CalendarRateLimitException: On rate limit
            CalendarServiceException: On service unavailable
            CircuitBreakerOpenError: If circuit breaker is open
        """
        if self.enable_circuit_breaker:
            return self.circuit_breaker.call(
                self._create_event_with_retry,
                appointment_id,
                patient_id,
                doctor_id,
                appointment_time
            )
        else:
            return self._create_event_with_retry(
                appointment_id,
                patient_id,
                doctor_id,
                appointment_time
            )
    
    def _create_event_with_retry(
        self,
        appointment_id: str,
        patient_id: str,
        doctor_id: str,
        appointment_time: str
    ) -> Dict[str, Any]:
        """Internal method with retry logic"""
        last_exception = None
        
        for attempt in range(self.max_retries):
            try:
                if self.enable_logging and attempt > 0:
                    print(f"[CalendarAdapter] 🔄 Retry attempt {attempt + 1}/{self.max_retries}")
                
                # Call calendar service with timeout wrapper
                result = self._call_with_timeout(
                    appointment_id,
                    patient_id,
                    doctor_id,
                    appointment_time
                )
                
                if self.enable_logging:
                    print(f"[CalendarAdapter] ✅ Success on attempt {attempt + 1}")
                
                return result
            
            except CalendarTimeoutException as e:
                last_exception = e
                if self.enable_logging:
                    print(f"[CalendarAdapter] ⏰ Timeout on attempt {attempt + 1}")
                
                # Don't retry on timeout (might succeed but we'll never know)
                # Let caller handle async retry
                raise
            
            except CalendarRateLimitException as e:
                last_exception = e
                if self.enable_logging:
                    print(f"[CalendarAdapter] 🚫 Rate limited, waiting {e.retry_after}s")
                
                # Wait for retry_after period (only if not last attempt)
                if attempt < self.max_retries - 1:
                    time.sleep(min(e.retry_after, 5))  # Cap at 5s for testing
                else:
                    raise
            
            except (CalendarServiceException, CalendarMalformedResponseException) as e:
                last_exception = e
                if self.enable_logging:
                    print(f"[CalendarAdapter] ❌ Error: {type(e).__name__}")
                
                # Exponential backoff: 1s, 2s, 4s
                if attempt < self.max_retries - 1:
                    backoff = 2 ** attempt  # 1, 2, 4
                    if self.enable_logging:
                        print(f"[CalendarAdapter] ⏳ Backing off {backoff}s")
                    time.sleep(backoff)
                else:
                    raise
        
        # All retries exhausted
        if last_exception:
            raise last_exception
    
    def _call_with_timeout(
        self,
        appointment_id: str,
        patient_id: str,
        doctor_id: str,
        appointment_time: str
    ) -> Dict[str, Any]:
        """
        Call calendar service with timeout.
        
        Note: In production, use asyncio with timeout or threading.
        For this demo, we rely on the mock service's built-in delay.
        """
        import signal
        
        class TimeoutError(Exception):
            pass
        
        def timeout_handler(signum, frame):
            raise TimeoutError("Calendar service call timed out")
        
        # Set timeout alarm (Unix-like systems only)
        # For Windows, this won't work - rely on mock service behavior
        try:
            if hasattr(signal, 'SIGALRM'):
                signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(int(self.timeout_seconds))
        except Exception:
            pass  # Skip timeout on Windows
        
        try:
            result = self.calendar_service.create_event(
                appointment_id=appointment_id,
                patient_id=patient_id,
                doctor_id=doctor_id,
                appointment_time=appointment_time
            )
            return result
        except TimeoutError:
            raise CalendarTimeoutException(
                f"Calendar service timed out after {self.timeout_seconds}s"
            )
        finally:
            # Cancel alarm
            try:
                if hasattr(signal, 'SIGALRM'):
                    signal.alarm(0)
            except Exception:
                pass
    
    def delete_event(self, event_id: str) -> bool:
        """
        Delete calendar event (for compensation).
        
        Args:
            event_id: Calendar event ID
            
        Returns:
            True if deleted, False otherwise
        """
        try:
            if self.enable_circuit_breaker:
                return self.circuit_breaker.call(
                    self.calendar_service.delete_event,
                    event_id
                )
            else:
                return self.calendar_service.delete_event(event_id)
        except Exception as e:
            if self.enable_logging:
                print(f"[CalendarAdapter] ❌ Failed to delete event {event_id}: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get adapter statistics"""
        return {
            "max_retries": self.max_retries,
            "timeout_seconds": self.timeout_seconds,
            "circuit_breaker_enabled": self.enable_circuit_breaker,
            "circuit_breaker_state": self.circuit_breaker.get_state() if self.enable_circuit_breaker else None,
            "calendar_service_stats": self.calendar_service.get_stats()
        }
