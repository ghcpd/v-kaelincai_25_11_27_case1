import threading
import time
import json
from src.models import Outbox
from src.logging_utils import structured_log

class OutboxWorker(threading.Thread):
    def __init__(self, db_session, calendar_adapter, poll_interval=1.0, max_attempts=3, backoff=2.0):
        super().__init__(daemon=True)
        self.db_session = db_session
        self.calendar = calendar_adapter
        self.poll_interval = poll_interval
        self.max_attempts = max_attempts
        self.backoff = backoff
        self._stop = threading.Event()

    def run(self):
        structured_log('outbox_worker_start')
        while not self._stop.is_set():
            sess = self.db_session()
            items = sess.query(Outbox).filter(Outbox.status=='PENDING').all()
            for item in items:
                try:
                    appt_id = item.appointment_id
                    payload = item.payload
                    structured_log('outbox_processing', appointment_id=appt_id, extra={'payload': payload})
                    resp = self.calendar.book(appt_id, payload.get('slot'), request_id=payload.get('request_id'), simulate=payload.get('simulate'))
                    # mark confirmed
                    from src.models import Appointment, AppointmentState
                    appt = sess.query(Appointment).filter(Appointment.appointment_id==appt_id).first()
                    appt.state = AppointmentState.CONFIRMED
                    item.status = 'DONE'
                    sess.commit()
                    structured_log('outbox_done', appointment_id=appt_id)
                except Exception as e:
                    item.attempts += 1
                    item.last_error = str(e)
                    if item.attempts >= self.max_attempts:
                        item.status = 'FAILED'
                        # compensation: mark appointment cancelled
                        from src.state_machine import AppointmentStateMachine
                        sm = AppointmentStateMachine(self.db_session)
                        sm.mark_cancelled(item.appointment_id, reason=item.last_error)
                    sess.commit()
                    structured_log('outbox_error', appointment_id=item.appointment_id, message=str(e), extra={'attempts': item.attempts})
                    time.sleep(self.backoff)
            time.sleep(self.poll_interval)

    def stop(self):
        self._stop.set()
