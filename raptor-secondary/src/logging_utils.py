from typing import Any, Dict, Optional
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict

from . import config


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_record: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Attach extra fields
        for key, value in record.__dict__.items():
            if key.startswith("_"):
                continue
            if key in ("args", "asctime", "created", "exc_info", "exc_text", "filename", "funcName", "levelname", "levelno", "lineno", "module", "msecs", "msecs", "message", "msg", "name", "pathname", "process", "processName", "relativeCreated", "stack_info", "thread", "threadName"):
                continue
            if key in config.REDACT_FIELDS and value:
                log_record[key] = "[REDACTED]"
            elif value is not None:
                log_record[key] = value
        if record.exc_info:
            log_record["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(log_record)


def setup_logging():
    os.makedirs(os.path.dirname(config.LOG_PATH), exist_ok=True)
    handler = logging.FileHandler(config.LOG_PATH)
    handler.setFormatter(JsonFormatter())

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers = []
    root.addHandler(handler)
    root.addHandler(console)


def get_logger(name: str = "appointment") -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)


def log_duration(logger: logging.Logger, event: str, request_id: str, appointment_id: Optional[str] = None, slot_id: Optional[str] = None):
    """
    Context manager to log duration of operations.
    """
    class _Timer:
        def __enter__(self):
            self.start = time.perf_counter()
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            duration_ms = (time.perf_counter() - self.start) * 1000
            logger.info(
                f"{event}",
                extra={
                    "event": event,
                    "request_id": request_id,
                    "appointment_id": appointment_id,
                    "slot_id": slot_id,
                    "latency_ms": round(duration_ms, 2),
                },
            )
    return _Timer()
