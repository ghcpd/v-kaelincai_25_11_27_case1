import asyncio
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from .db import init_db, create_appointment, add_outbox, get_appointment_by_client_id, set_appointment_status, delete_appointment, get_outbox_by_appointment, mark_outbox_done
from .idempotency import check_idempotency
from .calendar_adapter import create_booking, cancel_booking, reset_circuit_breaker
from .logger import setup_logger, log_structured

logger = setup_logger()

from fastapi.staticfiles import StaticFiles
app = FastAPI()
app.mount('/ui', StaticFiles(directory='c:\\workspace\\reliable_appointment_booking_v2\\frontend', html=True), name='frontend')

# init DB
init_db()

# worker stop event
stop_event = asyncio.Event()


class ConfirmRequest(BaseModel):
    client_request_id: str
    slot_id: str
    patient_name: Optional[str] = None


@app.post('/appointments/confirm')
async def confirm_appointment(req: ConfirmRequest, request: Request):
    # structured logging
    log_structured(logger, 'info', 'Received confirm request', appointment_id=None, client_request_id=req.client_request_id, event='request.start', extra={'slot_id': req.slot_id})

    # pass-through calendar mode header (for tests)
    mode = request.headers.get('X-Calendar-Mode')
    adapter_timeout_header = request.headers.get('X-Api-Adapter-Timeout')
    try:
        adapter_timeout = float(adapter_timeout_header) if adapter_timeout_header else None
    except Exception:
        adapter_timeout = None

    # idempotency check
    existing = check_idempotency(req.client_request_id)
    if existing:
        # return previous state
        log_structured(logger, 'info', 'Idempotent request detected', appointment_id=existing['id'], client_request_id=req.client_request_id, event='idempotency.hit')
        if existing['status'] == 'SUCCESS':
            return {'status': 'SUCCESS', 'appointment_id': existing['id'], 'calendar_id': existing.get('calendar_id')}
        elif existing['status'] == 'IN_PROGRESS':
            raise HTTPException(status_code=202, detail={'status': 'IN_PROGRESS', 'appointment_id': existing['id']})
        else:
            raise HTTPException(status_code=500, detail={'status': existing['status']})

    # create tentative appointment IN_PROGRESS
    appt_id = create_appointment(req.client_request_id, req.slot_id, metadata={'patient_name': req.patient_name}, status='IN_PROGRESS')
    effective_timeout = adapter_timeout if adapter_timeout is not None else 2.0
    add_outbox(appt_id, 'CREATE_CALENDAR', {'client_request_id': req.client_request_id, 'slot_id': req.slot_id, 'metadata': {'patient_name': req.patient_name}, 'mode': mode, 'adapter_timeout': effective_timeout})

    # Try to process synchronously once
    res = await create_booking(req.client_request_id, req.slot_id, {'patient_name': req.patient_name}, timeout=effective_timeout, mode=mode)

    if res.get('ok'):
        calendar_id = res.get('calendar_id')
        set_appointment_status(appt_id, 'SUCCESS', calendar_id=calendar_id)
        # mark outbox as done to avoid double-processing
        try:
            outboxes = get_outbox_by_appointment(appt_id)
            for o in outboxes:
                mark_outbox_done(o['id'])
        except Exception:
            pass
        log_structured(logger, 'info', 'Appointment created and calendar confirmed', appointment_id=appt_id, client_request_id=req.client_request_id, event='appointment.success')
        return {'status': 'SUCCESS', 'appointment_id': appt_id, 'calendar_id': calendar_id}
    else:
        # sync failure, attempt compensation (if calendar_id present), and ensure no slot reserved
        try:
            calendar_id = res.get('calendar_id')
            if calendar_id:
                # attempt cancel
                await cancel_booking(calendar_id)
        except Exception:
            pass
        # mark failed and delete appointment to avoid false positives
        set_appointment_status(appt_id, 'FAILURE')
        delete_appointment(appt_id)
        log_structured(logger, 'error', 'Calendar sync failed, appointment rolled back', appointment_id=appt_id, client_request_id=req.client_request_id, event='appointment.rollback', extra={'calendar_error': res.get('error')})
        raise HTTPException(status_code=500, detail={'status': 'FAILURE', 'error': res.get('error')})


@app.on_event('startup')
async def start_workers():
    from .outbox_worker import run_worker_loop

    log_structured(logger, 'info', 'Starting background workers', appointment_id=None, client_request_id=None, event='startup')

    async def _start():
        # start background loop for outbox processing
        await run_worker_loop(stop_event)

    asyncio.create_task(_start())


@app.get('/health')
async def health():
    return {'status': 'ok'}


@app.post('/debug/reset')
async def debug_reset():
    from .db import reset_db
    reset_db()
    return {'ok': True}


@app.on_event('shutdown')
async def stop_workers():
    log_structured(logger, 'info', 'Stopping background workers', appointment_id=None, client_request_id=None, event='shutdown')
    stop_event.set()
