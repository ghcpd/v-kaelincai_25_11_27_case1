from flask import Flask, request, jsonify
import time
import argparse

app = Flask(__name__)

# Configurable mode using query params or runtime args
# /events?mode=success -> quick success
# mode=timeout -> sleep for longer than client timeout => client times out
# mode=bad -> return 500
# mode=malformed -> return 200 with bad payload


@app.route('/events', methods=['POST'])
def create_event():
    mode = request.args.get('mode', 'success')
    payload = request.json
    if mode == 'success':
        # return with event id
        return jsonify({'event_id': f"evt-{payload.get('appointment_id')}", 'status':'ok'})
    elif mode == 'timeout':
        time.sleep(10)
        return jsonify({'event_id': f"evt-{payload.get('appointment_id')}", 'status':'ok'})
    elif mode == 'bad':
        return ('Internal Error', 500)
    elif mode == 'malformed':
        return ('I am not JSON', 200)
    else:
        return jsonify({'event_id': f"evt-{payload.get('appointment_id')}", 'status':'ok'})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', default=8001, type=int)
    args = parser.parse_args()
    app.run(port=args.port)
