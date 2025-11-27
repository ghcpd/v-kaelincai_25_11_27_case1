from flask import Flask, request, jsonify
import time

# Mock calendar service that supports simulate behavior in requests
app = Flask('mock_calendar')

@app.route('/book', methods=['POST'])
def book():
    data = request.get_json() or {}
    simulate = data.get('simulate')
    appointment_id = data.get('appointment_id')
    slot = data.get('slot')
    if simulate == 'timeout':
        time.sleep(5)  # longer than adapter timeout
    elif simulate == 'fail':
        return jsonify({'error':'calendar error'}), 500
    elif simulate == 'malformed':
        return "not-json", 200
    # default success
    return jsonify({'booking_id': appointment_id, 'slot': slot})

@app.route('/cancel', methods=['POST'])
def cancel():
    data = request.get_json() or {}
    appointment_id = data.get('appointment_id')
    return jsonify({'status':'cancelled', 'appointment_id': appointment_id})

if __name__ == '__main__':
    app.run(port=5001)
