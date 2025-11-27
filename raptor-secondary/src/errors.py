from typing import Optional
from starlette import status
from .models import ErrorCode


class AppException(Exception):
    def __init__(self, message: str, code: ErrorCode = ErrorCode.UNKNOWN, http_status: int = status.HTTP_500_INTERNAL_SERVER_ERROR):
        super().__init__(message)
        self.message = message
        self.code = code
        self.http_status = http_status

    def to_dict(self):
        return {"code": self.code.value if self.code else None, "message": self.message}
