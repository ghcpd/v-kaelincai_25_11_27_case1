import httpx
import time
import asyncio
from .logger import setup_logger, log_structured
logger = setup_logger()

CALENDAR_BASE = 'http://127.0.0.1:9001'

# Simple circuit breaker
CB_FAILURES = 0
CB_THRESHOLD = 5
CB_RESET_TIMEOUT = 60
CB_TRIPPED_AT = None


def reset_circuit_breaker():
    global CB_FAILURES, CB_TRIPPED_AT
    CB_FAILURES = 0
    CB_TRIPPED_AT = None


async def create_booking(client_request_id, slot_id, metadata=None, timeout=2.0, retries=1, mode=None):
    global CB_FAILURES, CB_TRIPPED_AT
    if CB_TRIPPED_AT and time.time() - CB_TRIPPED_AT < CB_RESET_TIMEOUT:
        log_structured(logger, 'warning', 'Circuit breaker open', extra={'CB_FAILURES': CB_FAILURES, 'CB_TRIPPED_AT': CB_TRIPPED_AT})
        return {'ok': False, 'error': 'CircuitBreakerOpen'}
    log_structured(logger, 'debug', 'create_booking attempt start', extra={'client_request_id': client_request_id, 'slot_id': slot_id, 'mode': mode, 'CB_FAILURES': CB_FAILURES, 'CB_TRIPPED_AT': CB_TRIPPED_AT})
    attempt = 0
    while attempt <= retries:
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                headers = {}
                if mode:
                    headers['X-Calendar-Mode'] = mode
                resp = await client.post(f"{CALENDAR_BASE}/book", json={
                    'request_id': client_request_id,
                    'slot_id': slot_id,
                    'metadata': metadata or {}
                }, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    CB_FAILURES = 0
                    return {'ok': True, 'calendar_id': data.get('calendar_id')}
                else:
                    # treat as error
                    CB_FAILURES += 1
                    if CB_FAILURES >= CB_THRESHOLD:
                        CB_TRIPPED_AT = time.time()
                    return {'ok': False, 'error': f'CalendarError:{resp.status_code}', 'details': resp.text}
        except Exception as ex:
            CB_FAILURES += 1
            if CB_FAILURES >= CB_THRESHOLD:
                CB_TRIPPED_AT = time.time()
            attempt += 1
            # exponential backoff
            await asyncio.sleep(0.2 * (2 ** attempt))
            if attempt > retries:
                return {'ok': False, 'error': 'Timeout/NetworkError', 'details': str(ex)}


async def cancel_booking(calendar_id, timeout=5.0):
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{CALENDAR_BASE}/cancel", json={'calendar_id': calendar_id})
            if resp.status_code == 200:
                return {'ok': True}
            return {'ok': False, 'error': 'CancelFailed', 'details': resp.text}
    except Exception as ex:
        return {'ok': False, 'error': 'CancelException', 'details': str(ex)}
