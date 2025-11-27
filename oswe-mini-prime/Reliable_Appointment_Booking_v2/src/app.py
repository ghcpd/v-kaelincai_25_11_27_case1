from flask import Flask, request, jsonify, send_from_directory
import uuid
import time
from src.models import init_db, AppointmentState
from src.idempotency import IdempotencyHandler
from src.state_machine import AppointmentStateMachine
from src.adapters import CalendarAdapter
from src.worker import OutboxWorker
from src.logging_utils import structured_log

SessionLocal = init_db()
app = Flask(__name__, static_folder='../frontend')

IDEMPOTENCY_HEADER = 'Idempotency-Key'

calendar_base = 'http://127.0.0.1:5001'  # mock calendar default
calendar_adapter = CalendarAdapter(calendar_base, timeout=2.0, max_attempts=2)

idemp = IdempotencyHandler(SessionLocal)
state_machine = AppointmentStateMachine(SessionLocal)
worker = OutboxWorker(SessionLocal, calendar_adapter)
worker.start()

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status':'ok'})


@app.route('/')
def index():
    return send_from_directory('../frontend', 'index.html')

@app.route('/api/appointments', methods=['POST'])
def create_appointment():
    data = request.get_json() or {}
    client_id = data.get('client_id')
    slot = data.get('slot')
    idempotency_key = request.headers.get(IDEMPOTENCY_HEADER)
    request_id = str(uuid.uuid4())

    structured_log('request_received', request_id=request_id, idempotency_key=idempotency_key, message='Create appointment request')

    if not client_id or not slot:
        return jsonify({'error':'client_id and slot required'}), 400

    if not idempotency_key:
        return jsonify({'error':'Idempotency-Key header required'}), 400

    # idempotency check
    existing, record = idemp.check_and_mark(idempotency_key, appointment_id=None)
    if existing:
        # return previous response (or in-progress)
        structured_log('idempotency_repeat', idempotency_key=idempotency_key, message='Returning stored response')
        if record.response is not None:
            status = 200 if record.response.get('status') == 'confirmed' else 202
            return jsonify(record.response), status
        else:
            # in-progress
            return jsonify({'appointment_id': record.appointment_id, 'status': 'in-progress'}), 202

    # create appointment entry (reservation) with IN_PROGRESS
    appointment_id = str(uuid.uuid4())
    appt = state_machine.create_appointment(appointment_id, client_id, slot, meta={'request_id': request_id})
    # update idempotency record with appointment id
    idemp.update_appointment(idempotency_key, appointment_id)
    # If client asked for async response, enqueue outbox and return 202 IN_PROGRESS
    if request.headers.get('Prefer') == 'respond-async':
        state_machine.enqueue_outbox(appointment_id, {'slot': slot, 'request_id': request_id, 'simulate': data.get('simulate')})
        response = {'appointment_id': appointment_id, 'status': 'in-progress'}
        idemp.update_response(idempotency_key, response)
        structured_log('create_async', appointment_id=appointment_id, request_id=request_id, idempotency_key=idempotency_key)
        return jsonify(response), 202

    # Synchronous attempt to book calendar
    try:
        simulate = data.get('simulate')
        resp = calendar_adapter.book(appointment_id, slot, request_id=request_id, simulate=simulate)
        # mark confirmed and update idempotency
        state_machine.mark_confirmed(appointment_id)
        response = {'appointment_id': appointment_id, 'status': 'confirmed', 'calendar': resp}
        idemp.update_response(idempotency_key, response)
        structured_log('create_success', appointment_id=appointment_id, request_id=request_id, idempotency_key=idempotency_key, state='CONFIRMED')
        return jsonify(response), 200
    except Exception as e:
        # compensating action: cancel local reservation
        state_machine.mark_cancelled(appointment_id, reason=str(e))
        response = {'appointment_id': appointment_id, 'status': 'failed', 'error': str(e)}
        idemp.update_response(idempotency_key, response)
        structured_log('create_failed', appointment_id=appointment_id, request_id=request_id, idempotency_key=idempotency_key, message=str(e))
        return jsonify(response), 500


@app.route('/api/appointments/<appointment_id>', methods=['GET'])
def get_appointment(appointment_id):
    sess = SessionLocal()
    from src.models import Appointment
    appt = sess.query(Appointment).filter(Appointment.appointment_id==appointment_id).first()
    if not appt:
        return jsonify({'error':'not_found'}), 404
    return jsonify({'appointment_id': appt.appointment_id, 'state': appt.state.value, 'slot': appt.slot})


@app.route('/api/appointments', methods=['GET'])
def list_appointments():
    slot = request.args.get('slot')
    sess = SessionLocal()
    from src.models import Appointment
    if slot:
        appts = sess.query(Appointment).filter(Appointment.slot==slot).all()
    else:
        appts = sess.query(Appointment).all()
    return jsonify([{'appointment_id': a.appointment_id, 'state': a.state.value, 'slot':a.slot} for a in appts])


@app.route('/api/idempotency/<key>', methods=['GET'])
def get_idempotency(key):
    sess = SessionLocal()
    from src.models import IdempotencyKey
    rec = sess.query(IdempotencyKey).filter(IdempotencyKey.key==key).first()
    if not rec:
        return jsonify({'error':'not_found'}), 404
    return jsonify({'key': rec.key, 'appointment_id': rec.appointment_id, 'response': rec.response})

if __name__ == '__main__':
    try:
        app.run(port=5000)
    finally:
        worker.stop()
