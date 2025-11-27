import logging
import json

from pythonjsonlogger import jsonlogger


def setup_logger(name: str = 'appointments'):
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    logHandler = logging.StreamHandler()
    import os
    os.makedirs('c:\\\\workspace\\\\reliable_appointment_booking_v2\\\\logs', exist_ok=True)
    fileHandler = logging.FileHandler('c:\\\\workspace\\\\reliable_appointment_booking_v2\\\\logs\\\\appointments.log')
    formatter = jsonlogger.JsonFormatter(
        '%(asctime)s %(levelname)s %(name)s %(message)s %(appointment_id)s %(client_request_id)s %(event)s'
    )
    fileHandler.setFormatter(formatter)
    logger.addHandler(fileHandler)
    formatter = jsonlogger.JsonFormatter(
        '%(asctime)s %(levelname)s %(name)s %(message)s %(appointment_id)s %(client_request_id)s %(event)s'
    )
    logHandler.setFormatter(formatter)
    logger.addHandler(logHandler)
    return logger


# Helper for structured log entries

def log_structured(logger, level, message, appointment_id=None, client_request_id=None, event=None, extra=None):
    payload = {
        'message': message,
        'appointment_id': appointment_id,
        'client_request_id': client_request_id,
        'event': event,
    }
    if extra:
        payload.update(extra)
    # redact sensitive data
    if 'patient_name' in payload:
        payload['patient_name'] = '[REDACTED]'
    if level == 'info':
        logger.info(payload)
    elif level == 'error':
        logger.error(payload)
    elif level == 'warning':
        logger.warning(payload)
    else:
        logger.debug(payload)
