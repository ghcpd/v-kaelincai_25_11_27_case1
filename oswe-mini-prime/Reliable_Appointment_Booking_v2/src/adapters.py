import requests
import time
from requests.exceptions import RequestException
from src.logging_utils import structured_log

class CalendarAdapter:
    def __init__(self, base_url, timeout=2.0, max_attempts=3):
        self.base_url = base_url
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.failure_count = 0
        self.circuit_open = False
        self.open_ttl = 5.0 # seconds
        self.opened_at = None

    def _open_circuit(self):
        self.circuit_open = True
        self.opened_at = time.time()
        structured_log('circuit_breaker_open', message='Circuit breaker opened for calendar')

    def _check_circuit(self):
        if self.circuit_open:
            if self.opened_at is not None and (time.time() - self.opened_at) > self.open_ttl:
                self.circuit_open = False
            else:
                return False
        return True

    def book(self, appointment_id, slot, request_id=None, simulate=None):
        if not self._check_circuit():
            structured_log('calendar_circuit_open', appointment_id=appointment_id, request_id=request_id, message='Circuit is open')
            raise RequestException('calendar circuit is open')
        attempts = 0
        while attempts < self.max_attempts:
            try:
                attempts += 1
                payload = {'appointment_id': appointment_id, 'slot': slot}
                if simulate:
                    payload['simulate'] = simulate
                resp = requests.post(self.base_url + '/book', timeout=self.timeout, json=payload)
                if resp.status_code == 200:
                    self.failure_count = 0
                    return resp.json()
                else:
                    # treat as failure
                    structured_log('calendar_book_failed', appointment_id=appointment_id, request_id=request_id, message=f'status {resp.status_code}')
                    self.failure_count += 1
            except RequestException as e:
                structured_log('calendar_exception', appointment_id=appointment_id, request_id=request_id, message=str(e))
                self.failure_count += 1
            if self.failure_count >= 5:
                self._open_circuit()
        raise RequestException('calendar retries exhausted')

    def cancel(self, appointment_id, request_id=None):
        try:
            resp = requests.post(self.base_url + '/cancel', timeout=self.timeout, json={'appointment_id': appointment_id})
            return resp.json()
        except RequestException as e:
            structured_log('calendar_cancel_exception', appointment_id=appointment_id, request_id=request_id, message=str(e))
            raise
