import json
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.requests import Request
from starlette.routing import Route
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

from .service import AppointmentService
from .errors import AppException
from .logging_utils import get_logger

logger = get_logger("api")
service = AppointmentService()


async def confirm(request: Request):
    try:
        data = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"detail": "Invalid JSON"}, status_code=400)

    request_id = data.get("request_id")
    slot_id = data.get("slot_id")
    patient_name = data.get("patient_name")
    if not request_id or not slot_id:
        return JSONResponse({"detail": "request_id and slot_id are required"}, status_code=400)

    try:
        resp = service.confirm(request_id=request_id, slot_id=slot_id, patient_name=patient_name)
        return JSONResponse(resp, status_code=200)
    except AppException as e:
        logger.error("appointment_failed", extra={"request_id": request_id, "slot_id": slot_id, "error_code": e.code.value if e.code else None, "error": e.message})
        return JSONResponse({"detail": {"code": e.code.value if e.code else None, "message": e.message}}, status_code=e.http_status)
    except Exception as e:
        logger.exception("unexpected_failure", extra={"request_id": request_id, "slot_id": slot_id})
        return JSONResponse({"detail": str(e)}, status_code=500)


async def health(request: Request):
    return JSONResponse({"status": "ok"})


routes = [
    Route("/appointments/confirm", confirm, methods=["POST"]),
    Route("/healthz", health, methods=["GET"]),
]

middleware = [Middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])]

app = Starlette(debug=False, routes=routes, middleware=middleware)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
