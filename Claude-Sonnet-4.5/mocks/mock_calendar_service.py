"""
Mock Calendar Service with Controllable Fault Injection

Simulates external calendar API behavior including:
- Normal success responses
- Configurable delays
- Timeout scenarios
- Rate limiting
- Malformed responses
- Service unavailability
"""

import time
import random
import json
from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime
import uuid


class CalendarBehavior(Enum):
    """Defines mock calendar service behavior modes"""
    SUCCESS = "success"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    SERVICE_UNAVAILABLE = "service_unavailable"
    MALFORMED_RESPONSE = "malformed_response"
    INTERMITTENT_FAILURE = "intermittent_failure"
    SLOW_RESPONSE = "slow_response"


class MockCalendarService:
    """
    Simulates external calendar API with configurable fault injection.
    
    Usage:
        # Normal operation
        service = MockCalendarService()
        event = service.create_event(appointment_data)
        
        # Inject timeout
        service = MockCalendarService(behavior=CalendarBehavior.TIMEOUT)
        service.create_event(appointment_data)  # Will delay 11 seconds
        
        # Inject rate limit
        service = MockCalendarService(behavior=CalendarBehavior.RATE_LIMITED)
        service.create_event(appointment_data)  # Raises rate limit error
    """
    
    def __init__(
        self,
        behavior: CalendarBehavior = CalendarBehavior.SUCCESS,
        delay_seconds: float = 0.1,
        failure_rate: float = 0.0,
        enable_logging: bool = True
    ):
        """
        Initialize mock calendar service.
        
        Args:
            behavior: The behavior mode to simulate
            delay_seconds: Base delay for responses (default 100ms)
            failure_rate: Probability of failure for INTERMITTENT_FAILURE mode (0.0-1.0)
            enable_logging: Whether to print debug logs
        """
        self.behavior = behavior
        self.delay_seconds = delay_seconds
        self.failure_rate = failure_rate
        self.enable_logging = enable_logging
        self.request_count = 0
        self.created_events: Dict[str, Dict[str, Any]] = {}
    
    def create_event(
        self,
        appointment_id: str,
        patient_id: str,
        doctor_id: str,
        appointment_time: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Create a calendar event (simulated).
        
        Args:
            appointment_id: Unique appointment identifier
            patient_id: Patient identifier
            doctor_id: Doctor identifier
            appointment_time: ISO 8601 timestamp
            
        Returns:
            Dict with event_id, status, and created_at
            
        Raises:
            CalendarTimeoutException: On timeout behavior
            CalendarRateLimitException: On rate limit behavior
            CalendarServiceException: On service unavailable
            CalendarMalformedResponseException: On malformed response
        """
        self.request_count += 1
        
        if self.enable_logging:
            print(f"[MockCalendar] Request #{self.request_count}: create_event for appointment={appointment_id}")
        
        # Apply behavior-based logic
        if self.behavior == CalendarBehavior.TIMEOUT:
            return self._simulate_timeout(appointment_id)
        
        elif self.behavior == CalendarBehavior.RATE_LIMITED:
            return self._simulate_rate_limit(appointment_id)
        
        elif self.behavior == CalendarBehavior.SERVICE_UNAVAILABLE:
            return self._simulate_service_unavailable(appointment_id)
        
        elif self.behavior == CalendarBehavior.MALFORMED_RESPONSE:
            return self._simulate_malformed_response(appointment_id)
        
        elif self.behavior == CalendarBehavior.INTERMITTENT_FAILURE:
            return self._simulate_intermittent_failure(appointment_id, patient_id, doctor_id, appointment_time)
        
        elif self.behavior == CalendarBehavior.SLOW_RESPONSE:
            return self._simulate_slow_response(appointment_id, patient_id, doctor_id, appointment_time)
        
        else:  # SUCCESS
            return self._simulate_success(appointment_id, patient_id, doctor_id, appointment_time)
    
    def _simulate_success(
        self,
        appointment_id: str,
        patient_id: str,
        doctor_id: str,
        appointment_time: str
    ) -> Dict[str, Any]:
        """Simulate successful calendar event creation"""
        time.sleep(self.delay_seconds)  # Realistic network delay
        
        event_id = f"cal-evt-{uuid.uuid4().hex[:8]}"
        event_data = {
            "event_id": event_id,
            "status": "confirmed",
            "appointment_id": appointment_id,
            "patient_id": patient_id,
            "doctor_id": doctor_id,
            "start_time": appointment_time,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "calendar_provider": "MockCalendarService"
        }
        
        self.created_events[event_id] = event_data
        
        if self.enable_logging:
            print(f"[MockCalendar] ✅ Success: Created event {event_id}")
        
        return event_data
    
    def _simulate_timeout(self, appointment_id: str) -> Dict[str, Any]:
        """Simulate timeout by delaying beyond typical timeout threshold"""
        if self.enable_logging:
            print(f"[MockCalendar] ⏰ Simulating timeout (11s delay)...")
        
        time.sleep(11)  # Exceeds typical 10s timeout
        
        # Code below won't be reached if client has timeout set
        raise CalendarTimeoutException(
            f"Calendar service timed out for appointment {appointment_id}"
        )
    
    def _simulate_rate_limit(self, appointment_id: str) -> Dict[str, Any]:
        """Simulate rate limit error (HTTP 429)"""
        time.sleep(self.delay_seconds)
        
        if self.enable_logging:
            print(f"[MockCalendar] 🚫 Rate limit exceeded")
        
        raise CalendarRateLimitException(
            message="Rate limit exceeded",
            retry_after=60,
            details={
                "error": "rate_limit_exceeded",
                "retry_after": 60,
                "limit": 100,
                "window": "60s",
                "appointment_id": appointment_id
            }
        )
    
    def _simulate_service_unavailable(self, appointment_id: str) -> Dict[str, Any]:
        """Simulate service unavailable error (HTTP 503)"""
        time.sleep(self.delay_seconds)
        
        if self.enable_logging:
            print(f"[MockCalendar] ❌ Service unavailable (503)")
        
        raise CalendarServiceException(
            message="Calendar service temporarily unavailable",
            status_code=503,
            details={
                "error": "service_unavailable",
                "message": "Upstream calendar provider is down",
                "appointment_id": appointment_id
            }
        )
    
    def _simulate_malformed_response(self, appointment_id: str) -> Dict[str, Any]:
        """Simulate malformed JSON response missing expected fields"""
        time.sleep(self.delay_seconds)
        
        if self.enable_logging:
            print(f"[MockCalendar] ⚠️  Returning malformed response")
        
        # Return response missing 'event_id' field
        malformed_data = {
            "status": "unknown",
            "message": "Something went wrong",
            # Missing: event_id (expected by client)
            "timestamp": datetime.utcnow().isoformat()
        }
        
        raise CalendarMalformedResponseException(
            message="Missing expected field: event_id",
            response_data=malformed_data
        )
    
    def _simulate_intermittent_failure(
        self,
        appointment_id: str,
        patient_id: str,
        doctor_id: str,
        appointment_time: str
    ) -> Dict[str, Any]:
        """Randomly fail based on failure_rate"""
        if random.random() < self.failure_rate:
            # Fail with random error
            error_types = [
                self._simulate_timeout,
                self._simulate_rate_limit,
                self._simulate_service_unavailable
            ]
            error_func = random.choice(error_types)
            return error_func(appointment_id)
        else:
            # Success
            return self._simulate_success(appointment_id, patient_id, doctor_id, appointment_time)
    
    def _simulate_slow_response(
        self,
        appointment_id: str,
        patient_id: str,
        doctor_id: str,
        appointment_time: str
    ) -> Dict[str, Any]:
        """Simulate slow but successful response (tests p95 latency)"""
        slow_delay = random.uniform(3.0, 5.0)  # 3-5 seconds
        
        if self.enable_logging:
            print(f"[MockCalendar] 🐌 Slow response: {slow_delay:.2f}s delay")
        
        time.sleep(slow_delay)
        return self._simulate_success(appointment_id, patient_id, doctor_id, appointment_time)
    
    def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a previously created event"""
        return self.created_events.get(event_id)
    
    def delete_event(self, event_id: str) -> bool:
        """Delete a calendar event (for compensation testing)"""
        if event_id in self.created_events:
            del self.created_events[event_id]
            
            if self.enable_logging:
                print(f"[MockCalendar] 🗑️  Deleted event {event_id}")
            
            return True
        return False
    
    def list_events(self) -> Dict[str, Dict[str, Any]]:
        """List all created events"""
        return self.created_events.copy()
    
    def reset(self):
        """Reset service state (for testing)"""
        self.request_count = 0
        self.created_events.clear()
        
        if self.enable_logging:
            print("[MockCalendar] 🔄 Service reset")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics"""
        return {
            "total_requests": self.request_count,
            "events_created": len(self.created_events),
            "behavior": self.behavior.value,
            "failure_rate": self.failure_rate
        }


# Custom Exceptions

class CalendarException(Exception):
    """Base exception for calendar service errors"""
    pass


class CalendarTimeoutException(CalendarException):
    """Raised when calendar service times out"""
    pass


class CalendarRateLimitException(CalendarException):
    """Raised when rate limit is exceeded"""
    def __init__(self, message: str, retry_after: int, details: Optional[Dict] = None):
        super().__init__(message)
        self.retry_after = retry_after
        self.details = details or {}


class CalendarServiceException(CalendarException):
    """Raised when calendar service is unavailable or returns error"""
    def __init__(self, message: str, status_code: int, details: Optional[Dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details or {}


class CalendarMalformedResponseException(CalendarException):
    """Raised when calendar returns malformed response"""
    def __init__(self, message: str, response_data: Optional[Dict] = None):
        super().__init__(message)
        self.response_data = response_data or {}


# Factory function for easy test setup

def create_calendar_service(scenario: str) -> MockCalendarService:
    """
    Factory function to create mock calendar service with predefined scenarios.
    
    Scenarios:
        - "success": Normal operation
        - "timeout": Always timeout
        - "rate_limited": Always rate limited
        - "service_unavailable": Always 503
        - "malformed": Always malformed response
        - "intermittent": 30% failure rate
        - "slow": Slow but successful (3-5s)
    """
    scenario_map = {
        "success": CalendarBehavior.SUCCESS,
        "timeout": CalendarBehavior.TIMEOUT,
        "rate_limited": CalendarBehavior.RATE_LIMITED,
        "service_unavailable": CalendarBehavior.SERVICE_UNAVAILABLE,
        "malformed": CalendarBehavior.MALFORMED_RESPONSE,
        "intermittent": CalendarBehavior.INTERMITTENT_FAILURE,
        "slow": CalendarBehavior.SLOW_RESPONSE
    }
    
    behavior = scenario_map.get(scenario, CalendarBehavior.SUCCESS)
    
    # Set failure rate for intermittent mode
    failure_rate = 0.3 if scenario == "intermittent" else 0.0
    
    return MockCalendarService(
        behavior=behavior,
        failure_rate=failure_rate,
        enable_logging=True
    )


# Example usage and testing
if __name__ == "__main__":
    print("=== Mock Calendar Service Test ===\n")
    
    # Test 1: Success
    print("Test 1: Success scenario")
    service = create_calendar_service("success")
    try:
        result = service.create_event(
            appointment_id="apt-001",
            patient_id="P123",
            doctor_id="D456",
            appointment_time="2025-11-28T14:00:00Z"
        )
        print(f"Result: {json.dumps(result, indent=2)}\n")
    except Exception as e:
        print(f"Error: {e}\n")
    
    # Test 2: Timeout
    print("Test 2: Timeout scenario")
    service = create_calendar_service("timeout")
    try:
        result = service.create_event(
            appointment_id="apt-002",
            patient_id="P124",
            doctor_id="D456",
            appointment_time="2025-11-28T15:00:00Z"
        )
        print(f"Result: {json.dumps(result, indent=2)}\n")
    except CalendarTimeoutException as e:
        print(f"Caught timeout: {e}\n")
    
    # Test 3: Rate limited
    print("Test 3: Rate limited scenario")
    service = create_calendar_service("rate_limited")
    try:
        result = service.create_event(
            appointment_id="apt-003",
            patient_id="P125",
            doctor_id="D456",
            appointment_time="2025-11-28T16:00:00Z"
        )
        print(f"Result: {json.dumps(result, indent=2)}\n")
    except CalendarRateLimitException as e:
        print(f"Caught rate limit: {e}, retry_after={e.retry_after}s\n")
    
    # Test 4: Service unavailable
    print("Test 4: Service unavailable scenario")
    service = create_calendar_service("service_unavailable")
    try:
        result = service.create_event(
            appointment_id="apt-004",
            patient_id="P126",
            doctor_id="D456",
            appointment_time="2025-11-28T17:00:00Z"
        )
        print(f"Result: {json.dumps(result, indent=2)}\n")
    except CalendarServiceException as e:
        print(f"Caught service error: {e}, status={e.status_code}\n")
    
    # Test 5: Malformed response
    print("Test 5: Malformed response scenario")
    service = create_calendar_service("malformed")
    try:
        result = service.create_event(
            appointment_id="apt-005",
            patient_id="P127",
            doctor_id="D456",
            appointment_time="2025-11-28T18:00:00Z"
        )
        print(f"Result: {json.dumps(result, indent=2)}\n")
    except CalendarMalformedResponseException as e:
        print(f"Caught malformed response: {e}\n")
    
    print("=== Tests Complete ===")
