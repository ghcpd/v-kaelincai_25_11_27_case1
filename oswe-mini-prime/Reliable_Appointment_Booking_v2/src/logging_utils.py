import json
import logging
from datetime import datetime

logger = logging.getLogger('appointments')
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)
# file handler for audit logs
fh = logging.FileHandler('logs/appointments.jsonl')
fh.setLevel(logging.DEBUG)
fh.setFormatter(formatter)
logger.addHandler(fh)

def structured_log(event, appointment_id=None, request_id=None, idempotency_key=None, state=None, level='INFO', message=None, extra=None):
    payload = {
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'level': level,
        'event': event,
        'appointment_id': appointment_id,
        'request_id': request_id,
        'idempotency_key': idempotency_key,
        'state': state,
        'message': message,
    }
    if extra:
        payload.update(extra)
    # redact not needed fields - placeholder for PII
    payload = {k:v for k,v in payload.items() if v is not None}
    logger.info(json.dumps(payload))
