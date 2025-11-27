import os
from typing import Optional

DB_PATH = os.environ.get("APPOINTMENT_DB_PATH", os.path.join(os.path.dirname(__file__), "..", "data", "appointments.db"))
LOG_PATH = os.environ.get("APPOINTMENT_LOG_PATH", os.path.join(os.path.dirname(__file__), "..", "logs", "app.log"))

CALENDAR_TIMEOUT_SECONDS = float(os.environ.get("CALENDAR_TIMEOUT_SECONDS", 1.5))
CALENDAR_MAX_ATTEMPTS = int(os.environ.get("CALENDAR_MAX_ATTEMPTS", 2))
CALENDAR_BACKOFF_BASE = float(os.environ.get("CALENDAR_BACKOFF_BASE", 0.5))
CALENDAR_CIRCUIT_THRESHOLD = int(os.environ.get("CALENDAR_CIRCUIT_THRESHOLD", 5))

# For structured log redaction
REDACT_FIELDS = {"patient_name", "patient_email", "patient_phone"}

# Optional: allow injection of mock calendar behavior
MOCK_CALENDAR_MODE: Optional[str] = os.environ.get("MOCK_CALENDAR_MODE")  # e.g., success, timeout, exception, partial
