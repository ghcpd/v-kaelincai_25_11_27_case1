# Reliable_Appointment_Booking_v2

This project demonstrates a resilient appointment booking API with idempotency, outbox compensation, and structured logging for calendar sync timeouts and errors.

Quickstart:
1. Setup: `bash scripts/setup.sh` (or `pip install -r requirements.txt`)
2. Run tests: `bash run_tests.sh` (or `python tests/run_suite.py`)

Components:
- `src/`: FastAPI app and modules
- `mocks/`: mock calendar service
- `frontend/`: simple UI
- `tests/`: integration YAML and runner
- `logs/`: audit schema and logs
- `docs/`: analysis and remediation plan

Contact: Backend & QA lead. Documented and testable via provided scripts.
