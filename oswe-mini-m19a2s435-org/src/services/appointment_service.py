from ..db import SessionLocal
from ..models import Appointment, Outbox, IdempotencyRecord, AppointmentStatus
from ..adapters.calendar_adapter import CalendarAdapter, CalendarError
from ..utils.logging import audit_log
from sqlalchemy.exc import IntegrityError
import json


class IdempotencyConflict(Exception):
    pass


class AppointmentService:
    def __init__(self, calendar_adapter: CalendarAdapter):
        self.calendar_adapter = calendar_adapter

    def confirm_appointment(self, client_request_id: str, user_id: str, slot: str, async_confirm: bool = False, mode: str = None):
        # Check idempotency
        db = SessionLocal()
        try:
            rec = db.query(IdempotencyRecord).filter_by(client_request_id=client_request_id).first()
            if rec:
                audit_log('INFO', 'Idempotent duplicate', None, client_request_id, {'status': rec.response_status})
                return {'status': rec.response_status, 'payload': rec.response_payload}

            # Begin transaction to create appointment
            appt = Appointment(client_request_id=client_request_id, user_id=user_id, slot=slot, status=AppointmentStatus.IN_PROGRESS)
            db.add(appt)
            db.flush()  # get appt.id
            audit_log('INFO', 'Appointment persisted (in-progress)', appt.id, client_request_id, {'slot': slot})

            if async_confirm:
                # create outbox message and return in-progress
                out = Outbox(appointment_id=appt.id, payload={'user_id':user_id,'slot':slot, 'client_request_id': client_request_id, 'mode': mode})
                db.add(out)
                db.commit()
                # idempotency record
                idrec = IdempotencyRecord(client_request_id=client_request_id, response_status='in_progress', response_payload={'appointment_id': appt.id, 'status': 'in_progress'})
                db.add(idrec)
                db.commit()
                audit_log('INFO', 'Returning in-progress after scheduling outbox', appt.id, client_request_id)
                return {'status':'in_progress','payload':{'appointment_id': appt.id, 'status':'in_progress'}}

            # For synchronous confirm: attempt to call calendar
            try:
                success, payload = self.calendar_adapter.create_event(appt.id, user_id, slot, mode=mode, client_request_id=client_request_id)
                if success:
                    appt.status = AppointmentStatus.SUCCESS
                    appt.calendar_event_id = payload.get('event_id')
                    idrec = IdempotencyRecord(client_request_id=client_request_id, response_status='success', response_payload={'appointment_id': appt.id, 'status': 'success', 'calendar_event_id': appt.calendar_event_id})
                    db.add(idrec)
                    db.commit()
                    audit_log('INFO', 'Appointment confirmed (success)', appt.id, client_request_id, {'calendar_event_id': appt.calendar_event_id})
                    return {'status':'success','payload':{'appointment_id': appt.id, 'status':'success', 'calendar_event_id': appt.calendar_event_id}}
                else:
                    raise CalendarError('Unknown calendar response')
            except CalendarError as e:
                db.rollback()
                # On failure, ensure deterministic failure; do not leave appointment reserved
                audit_log('ERROR', 'Calendar sync failed, rolling back to avoid booking', appt.id, client_request_id, {'error': str(e)})
                idrec = IdempotencyRecord(client_request_id=client_request_id, response_status='failed', response_payload={'message':'Calendar sync failed'})
                db.add(idrec)
                db.commit()
                return {'status':'failed', 'payload': {'message': 'Calendar sync failed'}}
        finally:
            db.close()

    def process_outbox_once(self):
        # Simple worker to process pending outbox messages
        db = SessionLocal()
        try:
            out = db.query(Outbox).filter_by(locked=0).order_by(Outbox.id).first()
            if not out:
                return None
            out.locked = 1
            db.commit()
            appt = db.get(Appointment, out.appointment_id)
            if not appt:
                db.delete(out)
                db.commit()
                return None
            try:
                # pick mode from outbox payload if provided
                mode = out.payload.get('mode') or None
                success, payload = self.calendar_adapter.create_event(appt.id, appt.user_id, appt.slot, mode=mode, client_request_id=appt.client_request_id)
                if success:
                    appt.status = AppointmentStatus.SUCCESS
                    appt.calendar_event_id = payload.get('event_id')
                    db.delete(out)
                    # update idempotency
                    idrec = db.query(IdempotencyRecord).filter_by(client_request_id=appt.client_request_id).first()
                    if idrec:
                        idrec.response_status = 'success'
                        idrec.response_payload = {'appointment_id': appt.id, 'status': 'success'}
                    else:
                        db.add(IdempotencyRecord(client_request_id=appt.client_request_id, response_status='success', response_payload={'appointment_id': appt.id, 'status': 'success'}))
                    db.commit()
                    audit_log('INFO', 'Outbox processed successfully', appt.id, appt.client_request_id)
                    return {'ok': True}
                else:
                    out.attempts += 1
                    if out.attempts >= out.max_attempts:
                        # Compensation
                        appt.status = AppointmentStatus.FAILED
                        db.delete(out)
                        idrec = db.query(IdempotencyRecord).filter_by(client_request_id=appt.client_request_id).first()
                        if idrec:
                            idrec.response_status = 'failed'
                            idrec.response_payload = {'message':'Calendar sync failed after retries'}
                        else:
                            db.add(IdempotencyRecord(client_request_id=appt.client_request_id, response_status='failed', response_payload={'message':'Calendar sync failed after retries'}))
                        db.commit()
                        audit_log('WARN', 'Outbox failed and compensated (appointment failed)', appt.id, appt.client_request_id)
                        return {'ok': False, 'compensated': True}
                    else:
                        # release lock for retry and persist the attempt counter
                        out.locked = 0
                        db.commit()
                        audit_log('INFO', 'Outbox attempt failed, will retry', appt.id, appt.client_request_id, {'attempts': out.attempts})
                        return {'ok': False}
            except CalendarError as e:
                out.attempts += 1
                if out.attempts >= out.max_attempts:
                    # Compensation due to repeated errors
                    appt.status = AppointmentStatus.FAILED
                    db.delete(out)
                    idrec = db.query(IdempotencyRecord).filter_by(client_request_id=appt.client_request_id).first()
                    if idrec:
                        idrec.response_status = 'failed'
                        idrec.response_payload = {'message':'Calendar sync failed after retries'}
                    else:
                        db.add(IdempotencyRecord(client_request_id=appt.client_request_id, response_status='failed', response_payload={'message':'Calendar sync failed after retries'}))
                    db.commit()
                    audit_log('WARN', 'Outbox error and compensated (appointment failed)', appt.id, appt.client_request_id, {'error': str(e), 'attempts': out.attempts})
                    return {'ok': False, 'compensated': True}
                else:
                    # release lock for next attempt
                    out.locked = 0
                    db.commit()
                    audit_log('ERROR', 'Calendar error while processing outbox', appt.id, appt.client_request_id, {'error': str(e), 'attempts': out.attempts})
                    return {'ok': False}
        finally:
            db.close()
