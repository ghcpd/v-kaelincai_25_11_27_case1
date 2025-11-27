import httpx
from typing import Tuple, Optional
from ..utils.logging import audit_log


class CalendarError(Exception):
    pass


class CalendarAdapter:
    def __init__(self, service_url=None, timeout_seconds=2):
        self.service_url = service_url or 'http://127.0.0.1:8001'
        self.timeout_seconds = timeout_seconds

    def create_event(self, appointment_id: int, user_id: str, slot: str, mode: Optional[str] = None, client_request_id: Optional[str] = None) -> Tuple[bool, dict]:
        url = f"{self.service_url}/events"
        if mode:
            url = url + f"?mode={mode}"
        payload = {
            'appointment_id': appointment_id,
            'user_id': user_id,
            'slot': slot,
            'client_request_id': client_request_id
        }
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                resp = client.post(url, json=payload)
                if resp.status_code == 200:
                    audit_log('INFO', 'Calendar event created', appointment_id, payload.get('client_request_id'), {'response': resp.json()})
                    return True, resp.json()
                else:
                    audit_log('WARN', 'Calendar returned error', appointment_id, payload.get('client_request_id'), {'status': resp.status_code, 'body': resp.text})
                    raise CalendarError(f"Calendar error: {resp.status_code}")
        except httpx.RequestError as e:
            audit_log('ERROR', 'Calendar request failed', appointment_id, payload.get('client_request_id'), {'error': str(e)})
            raise CalendarError("Calendar request failed")
