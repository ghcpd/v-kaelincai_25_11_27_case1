import json
import os
import datetime

# Simple JSON structured logger
REDACT_FIELDS = ['user_ssn', 'password', 'credit_card']


def redact(obj):
    if isinstance(obj, dict):
        new = {}
        for k, v in obj.items():
            if k in REDACT_FIELDS:
                new[k] = 'REDACTED'
            else:
                new[k] = redact(v)
        return new
    elif isinstance(obj, list):
        return [redact(i) for i in obj]
    else:
        return obj


def audit_log(level: str, msg: str, appointment_id=None, request_id=None, extra=None):
    entry = {
        "timestamp": datetime.datetime.utcnow().isoformat() + 'Z',
        "level": level,
        "message": msg,
        "appointment_id": appointment_id,
        "request_id": request_id,
        "extra": redact(extra) if extra else None,
        "service": "AppointmentAPI",
    }
    line = json.dumps(entry)
    print(line)
    # Also append to file for test harness to check
    try:
        with open('logs/audit.log', 'a') as fh:
            fh.write(line + '\n')
    except Exception:
        pass
