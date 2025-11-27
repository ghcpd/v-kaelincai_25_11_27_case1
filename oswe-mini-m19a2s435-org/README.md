# Reliable_Appointment_Booking_v2

This workspace contains a minimal FastAPI-based Appointment API resilient to external calendar failures with idempotency, outbox-based retries, compensation, and structured logging.

Run integration tests:
- Use python 3.11 (recommended) or Docker/GitHub Actions for consistent runs.
- Setup Python environment: `bash setup.sh` or for Windows use `powershell.exe -File setup.ps1` (not provided). If you have Python 3.11 installed, create venv and install requirements: `python -m venv .venv; . .venv/bin/activate; python -m pip install -r requirements.txt`.
- Run tests locally: `python -m pytest -q` or `bash scripts/run_appointment_suite.sh`.
- Alternatively: run in Docker (if available): `docker build -t appointment-suite-test . && docker run --rm appointment-suite-test`.
- CI: GitHub Actions `/.github/workflows/run_tests.yml` runs pytest on Python 3.11 and will validate the suite.

Structure:
- src/ backend
- mocks/ mock calendar service
- tests/ integration tests and runner
- docs/ analysis and remediation
- frontend/ index.html
