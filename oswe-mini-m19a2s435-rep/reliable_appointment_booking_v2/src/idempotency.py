from .db import get_appointment_by_client_id


def check_idempotency(client_request_id):
    appt = get_appointment_by_client_id(client_request_id)
    if not appt:
        return None
    # returning existing state
    return appt
