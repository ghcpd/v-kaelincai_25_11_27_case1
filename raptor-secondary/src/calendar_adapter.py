import time
from typing import Tuple, Optional
from tenacity import retry, stop_after_attempt, wait_exponential, RetryError

from . import config
from .models import Appointment, ErrorCode
from .errors import AppException
from .logging_utils import get_logger

logger = get_logger(__name__)


class CalendarTimeoutError(Exception):
    pass


class CalendarMalformedError(Exception):
    pass


class CalendarPartialError(Exception):
    """Represents a partial success that needs compensation."""
    pass


class CircuitOpenError(Exception):
    pass


class SimpleCircuitBreaker:
    def __init__(self, threshold: int):
        self.threshold = threshold
        self.failures = 0
        self.open_until = None
        self.cooldown_seconds = 5

    def record_success(self):
        self.failures = 0
        self.open_until = None

    def record_failure(self):
        self.failures += 1
        if self.failures >= self.threshold:
            self.open_until = time.time() + self.cooldown_seconds

    def check(self):
        if self.open_until and time.time() < self.open_until:
            raise CircuitOpenError("Calendar circuit is open")
        if self.open_until and time.time() >= self.open_until:
            # reset after cooldown
            self.failures = 0
            self.open_until = None


_circuit = SimpleCircuitBreaker(config.CALENDAR_CIRCUIT_THRESHOLD)


class CalendarAdapter:
    def __init__(self, mock_service=None):
        # lazily import to avoid circulars
        if mock_service is None:
            from mocks.mock_calendar_service import MockCalendarService
            self.service = MockCalendarService()
        else:
            self.service = mock_service

    def _call_calendar(self, appointment: Appointment) -> Tuple[bool, str]:
        # We allow the mock to simulate behavior based on request_id or slot_id
        outcome = self.service.sync(slot_id=appointment.slot_id, request_id=appointment.request_id)
        # outcome: tuple (status: str, detail: str)
        status, detail = outcome
        if status == "success":
            return True, detail
        elif status == "timeout":
            raise CalendarTimeoutError(detail)
        elif status == "malformed":
            raise CalendarMalformedError(detail)
        elif status == "partial":
            raise CalendarPartialError(detail)
        else:
            raise Exception(detail)

    @retry(stop=stop_after_attempt(config.CALENDAR_MAX_ATTEMPTS), wait=wait_exponential(multiplier=config.CALENDAR_BACKOFF_BASE))
    def _retryable_call(self, appointment: Appointment) -> Tuple[bool, str]:
        _circuit.check()
        success, detail = self._call_calendar(appointment)
        return success, detail

    def sync(self, appointment: Appointment) -> Tuple[bool, Optional[ErrorCode], str]:
        try:
            success, detail = self._retryable_call(appointment)
            _circuit.record_success()
            return True, None, detail
        except RetryError as e:
            last_exc = e.last_attempt.exception()
            if isinstance(last_exc, CalendarTimeoutError):
                _circuit.record_failure()
                return False, ErrorCode.CALENDAR_TIMEOUT, str(last_exc)
            if isinstance(last_exc, CalendarMalformedError):
                _circuit.record_failure()
                return False, ErrorCode.CALENDAR_MALFORMED, str(last_exc)
            if isinstance(last_exc, CalendarPartialError):
                _circuit.record_failure()
                return False, ErrorCode.CALENDAR_EXCEPTION, str(last_exc)
            _circuit.record_failure()
            return False, ErrorCode.UNKNOWN, str(last_exc)
        except CircuitOpenError as e:
            return False, ErrorCode.CIRCUIT_OPEN, str(e)
        except CalendarPartialError as e:
            _circuit.record_failure()
            return False, ErrorCode.CALENDAR_EXCEPTION, str(e)
        except CalendarTimeoutError as e:
            _circuit.record_failure()
            return False, ErrorCode.CALENDAR_TIMEOUT, str(e)
        except CalendarMalformedError as e:
            _circuit.record_failure()
            return False, ErrorCode.CALENDAR_MALFORMED, str(e)
        except Exception as e:
            _circuit.record_failure()
            return False, ErrorCode.UNKNOWN, str(e)
