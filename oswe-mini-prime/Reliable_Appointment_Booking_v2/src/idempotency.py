from src.models import IdempotencyKey
from src.logging_utils import structured_log
from sqlalchemy.exc import IntegrityError

class IdempotencyHandler:
    def __init__(self, db_session):
        self.db_session = db_session

    def check_and_mark(self, key, appointment_id=None, response=None):
        """If key exists, return existing response and appointment_id. If not create a record.
        Returns: (existing, record)
        """
        sess = self.db_session()
        record = sess.query(IdempotencyKey).filter(IdempotencyKey.key == key).first()
        if record is not None:
            structured_log('idempotency_hit', idempotency_key=key, appointment_id=record.appointment_id)
            return True, record
        # create
        record = IdempotencyKey(key=key, appointment_id=appointment_id, response=response)
        sess.add(record)
        try:
            sess.commit()
        except IntegrityError:
            sess.rollback()
            record = sess.query(IdempotencyKey).filter(IdempotencyKey.key == key).first()
            if record is not None:
                structured_log('idempotency_concurrent_hit', idempotency_key=key, appointment_id=record.appointment_id)
                return True, record
        structured_log('idempotency_marked', idempotency_key=key, appointment_id=appointment_id)
        return False, record

    def update_response(self, key, response):
        sess = self.db_session()
        record = sess.query(IdempotencyKey).filter(IdempotencyKey.key==key).first()
        if record:
            record.response = response
            sess.commit()
    def update_appointment(self, key, appointment_id):
        sess = self.db_session()
        record = sess.query(IdempotencyKey).filter(IdempotencyKey.key==key).first()
        if record:
            record.appointment_id = appointment_id
            sess.commit()
