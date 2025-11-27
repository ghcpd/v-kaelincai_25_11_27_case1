from fastapi import FastAPI, Request
from pydantic import BaseModel
import uuid
import time
import uvicorn
from typing import Optional

app = FastAPI()

# in-memory store
BOOKINGS = {}


class BookRequest(BaseModel):
    request_id: str
    slot_id: str
    metadata: Optional[dict] = None


@app.post('/book')
async def book(req: BookRequest, request: Request):
    # Use header X-Calendar-Mode or query param 'mode'
    mode = request.headers.get('X-Calendar-Mode') or request.query_params.get('mode')
    if mode == 'timeout':
        # simulate long delay
        time.sleep(5)
    if mode == 'error':
        return {'error': 'internal error'}, 500
    if mode == 'malformed':
        # return invalid data
        return "this is not json"

    # Idempotent booking by request_id
    if req.request_id in BOOKINGS:
        return {'calendar_id': BOOKINGS[req.request_id]}
    calendar_id = str(uuid.uuid4())
    BOOKINGS[req.request_id] = calendar_id
    return {'calendar_id': calendar_id}


class CancelRequest(BaseModel):
    calendar_id: str


@app.post('/cancel')
async def cancel(req: CancelRequest):
    # find booking and remove
    for k, v in list(BOOKINGS.items()):
        if v == req.calendar_id:
            del BOOKINGS[k]
            return {'ok': True}
    return {'ok': False}


@app.get('/health')
async def health():
    return {'status': 'ok'}


if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=9001)
