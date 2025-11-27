from pydantic import BaseModel, Field
from typing import Optional


class ConfirmAppointmentRequest(BaseModel):
    client_request_id: str = Field(..., description="Idempotency key)")
    user_id: str
    slot: str
    async_confirm: Optional[bool] = False
    mode: Optional[str] = None


class ConfirmAppointmentResponse(BaseModel):
    appointment_id: int
    status: str
    message: Optional[str]
