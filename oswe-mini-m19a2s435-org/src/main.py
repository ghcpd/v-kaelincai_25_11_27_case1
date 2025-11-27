from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from .services.appointment_service import AppointmentService
from .adapters.calendar_adapter import CalendarAdapter
from .db import init_db
from .schemas import ConfirmAppointmentRequest, ConfirmAppointmentResponse
from .utils.logging import audit_log
import threading
import time

app = FastAPI()
init_db()
calendar_adapter = CalendarAdapter()
service = AppointmentService(calendar_adapter)

# Background loop to process outbox
def outbox_worker():
    while True:
        try:
            res = service.process_outbox_once()
        except Exception as e:
            audit_log('ERROR', 'Outbox worker error', None, None, {'error': str(e)})
        time.sleep(0.2)

worker_thread = threading.Thread(target=outbox_worker, daemon=True)
worker_thread.start()


@app.post('/appointments/confirm')
async def confirm_appointment(req: ConfirmAppointmentRequest, request: Request):
    # Read header idempotency key if provided
    client_request_id = req.client_request_id
    audit_log('DEBUG', 'Confirm endpoint called', None, client_request_id, {'user_id': req.user_id, 'slot': req.slot, 'async_confirm': req.async_confirm})
    mode = getattr(req, 'mode', None)
    res = service.confirm_appointment(client_request_id, req.user_id, req.slot, async_confirm=req.async_confirm, mode=mode)
    if res['status'] == 'success':
        return JSONResponse(status_code=200, content=res['payload'])
    elif res['status'] == 'in_progress':
        # return 202
        return JSONResponse(status_code=202, content=res['payload'])
    else:
        # deterministic failure
        raise HTTPException(status_code=500, detail=res['payload'].get('message'))


@app.get('/appointments/{appointment_id}')
async def get_appointment(appointment_id: int):
    from .db import SessionLocal
    from .models import Appointment
    db = SessionLocal()
    try:
        appt = db.get(Appointment, appointment_id)
        if not appt:
            return JSONResponse(status_code=404, content={'message':'Not found'})
        return {'appointment_id': appt.id, 'status': appt.status.value, 'slot': appt.slot}
    finally:
        db.close()
