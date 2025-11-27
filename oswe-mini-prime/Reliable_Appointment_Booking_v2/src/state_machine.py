from src.models import Appointment, AppointmentState, Outbox
from src.logging_utils import structured_log
from sqlalchemy.exc import IntegrityError

class AppointmentStateMachine:
    def __init__(self, db_session):
        self.db_session = db_session

    def create_appointment(self, appointment_id, client_id, slot, meta=None):
        sess = self.db_session()
        appt = Appointment(appointment_id=appointment_id, client_id=client_id, slot=slot, state=AppointmentState.IN_PROGRESS, meta=meta or {})
        sess.add(appt)
        try:
            sess.commit()
            structured_log('appointment_created', appointment_id=appointment_id, state=appt.state.value)
            return appt
        except IntegrityError:
            sess.rollback()
            existing = sess.query(Appointment).filter(Appointment.appointment_id==appointment_id).first()
            structured_log('appointment_already_exists',(appointment_id, existing.state.value))
            return existing

    def mark_confirmed(self, appointment_id):
        sess = self.db_session()
        appt = sess.query(Appointment).filter(Appointment.appointment_id==appointment_id).first()
        if appt:
            appt.state = AppointmentState.CONFIRMED
            sess.commit()
            structured_log('appointment_confirmed', appointment_id=appointment_id, state=appt.state.value)

    def mark_failed(self, appointment_id, reason=None):
        sess = self.db_session()
        appt = sess.query(Appointment).filter(Appointment.appointment_id==appointment_id).first()
        if appt:
            appt.state = AppointmentState.FAILED
            sess.commit()
            structured_log('appointment_failed', appointment_id=appointment_id, state=appt.state.value, message=reason)

    def mark_cancelled(self, appointment_id, reason=None):
        sess = self.db_session()
        appt = sess.query(Appointment).filter(Appointment.appointment_id==appointment_id).first()
        if appt:
            appt.state = AppointmentState.CANCELLED
            sess.commit()
            structured_log('appointment_cancelled', appointment_id=appointment_id, state=appt.state.value, message=reason)

    def enqueue_outbox(self, appointment_id, payload):
        sess = self.db_session()
        o = Outbox(appointment_id=appointment_id, payload=payload, status='PENDING')
        sess.add(o)
        sess.commit()
        structured_log('outbox_enqueued', appointment_id=appointment_id)
        return o
