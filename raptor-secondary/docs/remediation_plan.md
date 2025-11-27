# Remediation Plan – Reliable_Appointment_Booking_v2

## Architecture Changes
- **Idempotency layer:**
  - DB unique constraint on `request_id`; reuse existing row on retries.
  - API returns consistent status based on stored state (CONFIRMED/IN_PROGRESS/FAILED).
- **State machine:** `INIT → IN_PROGRESS → (CONFIRMED | COMPENSATING → FAILED)`.
- **Calendar adapter:**
  - Retry with exponential backoff (`max_attempts=2`, configurable).
  - Simple circuit breaker to short-circuit repeated failures.
  - Standardized error codes (`CALENDAR_TIMEOUT`, `CALENDAR_EXCEPTION`, `CALENDAR_MALFORMED`, `CIRCUIT_OPEN`).
- **Compensation:**
  - On calendar failure, mark `COMPENSATING` then `FAILED`; release slot (no active reservation states).
- **Structured logging/audit:**
  - JSON logs with `request_id`, `appointment_id`, `slot_id`, `state`, `error_code`, `latency_ms`.
  - Redact sensitive fields (patient_*).
- **Mock calendar service:**
  - Deterministic outcomes (success/timeout/partial/malformed) for integration tests.

## Task Breakdown
1. **Backend (done)**
   - Starlette API, SQLite repo, state transitions, idempotency, retries/backoff, circuit breaker, compensation.
2. **Mock & tests (done)**
   - `mocks/mock_calendar_service.py`, integration YAML, `tests/run_suite.py`, runner scripts.
3. **Frontend (done)**
   - Simple HTML/JS for booking; shows init/in-progress/success/failure.
4. **Observability (done)**
   - `logs/audit_schema.json`, structured logging, sample screenshots.
5. **Docs (done)**
   - RCA, remediation plan, scenario definitions.

## Rollout
- **Phased enablement:**
  - Deploy idempotency + structured logging first (no behavior change).
  - Enable retry/backoff and circuit breaker.
  - Activate compensation logic after verifying audit trail.
- **Monitoring:**
  - Alert on elevated `CALENDAR_TIMEOUT`/`CIRCUIT_OPEN` rates.
  - Track idempotent retry counts and slot contention.

## Rollback
- Feature flags for retry/circuit breaker/compensation.
- Revert to previous API behavior while retaining logging for diagnosis.

## Single-Command Tests
- `bash scripts/run_appointment_suite.sh` (or `python tests/run_suite.py` on Windows) executes 5 integration scenarios and reports metrics.
