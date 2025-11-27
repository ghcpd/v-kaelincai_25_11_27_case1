import asyncio
import json
import time
from .db import get_pending_outbox, update_outbox_attempt, mark_outbox_done, mark_outbox_failed, set_appointment_status
from .calendar_adapter import create_booking, cancel_booking
from .logger import setup_logger, log_structured

logger = setup_logger()


async def process_outbox_once():
    entries = get_pending_outbox(20)
    for e in entries:
        outbox_id = e['id']
        appointment_id = e['appointment_id']
        action = e['action']
        payload = json.loads(e['payload'])
        attempts = e['attempts']
        try:
            log_structured(logger, 'info', f'Processing outbox {outbox_id}', appointment_id=appointment_id, client_request_id=payload.get('client_request_id'), event='outbox.process')
            if action == 'CREATE_CALENDAR':
                timeout_val = payload.get('adapter_timeout')
                if timeout_val:
                    res = await create_booking(payload.get('client_request_id'), payload.get('slot_id'), payload.get('metadata'), timeout=timeout_val, mode=payload.get('mode'))
                else:
                    res = await create_booking(payload.get('client_request_id'), payload.get('slot_id'), payload.get('metadata'), mode=payload.get('mode'))
                if res.get('ok'):
                    calendar_id = res.get('calendar_id')
                    set_appointment_status(appointment_id, 'SUCCESS', calendar_id=calendar_id)
                    mark_outbox_done(outbox_id)
                else:
                    # failed; if no calendar id created, remove appointment (compensation)
                    if res.get('error') == 'CircuitBreakerOpen':
                        # leave pending
                        update_outbox_attempt(outbox_id, 'PENDING', attempts+1, 'CircuitBreakerOpen')
                    else:
                        # After exhausting retries elsewhere, mark failed and set appt to FAILURE
                        mark_outbox_failed(outbox_id, str(res.get('error')), attempts+1)
                        set_appointment_status(appointment_id, 'FAILURE')
            elif action == 'CANCEL_CALENDAR':
                calendar_id = payload.get('calendar_id')
                res = await cancel_booking(calendar_id)
                if res.get('ok'):
                    set_appointment_status(appointment_id, 'CANCELLED')
                    mark_outbox_done(outbox_id)
                else:
                    mark_outbox_failed(outbox_id, res.get('error'), attempts+1)
        except Exception as ex:
            log_structured(logger, 'error', 'Exception processing outbox', appointment_id=appointment_id, client_request_id=payload.get('client_request_id'), event='outbox.exception', extra={'error': str(ex)})
            mark_outbox_failed(outbox_id, str(ex), attempts+1)


async def run_worker_loop(stop_event):
    while not stop_event.is_set():
        await process_outbox_once()
        await asyncio.sleep(0.5)
