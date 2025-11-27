# Integration Test Plan

Scenarios (from `tests/integration/appointment_cases.yaml`):

1) normal_success
   - simulate: none
   - expected: 200, appointment state CONFIRMED

2) calendar_timeout
   - simulate: timeout
   - expected: 500, appointment state CANCELLED

3) idempotency_retry
   - simulate: none
   - retries: 2 (same Idempotency-Key sent twice), expected: returns same appointment_id for both attempts; final state CONFIRMED

4) partial_success_compensation
   - simulate: fail (calendar returns 500), expected: 500, appointment state CANCELLED

5) audit_verification
   - simulate: none
   - verify logs contain events for appointment creation, calendar booking attempt, and confirmation

6) async_in_progress
   - prefer_async: true
   - simulate: none
   - client requests 202; background worker processes outbox and eventually appointment becomes CONFIRMED

Validation and Observability
---------------------------
- Each test records the raw HTTP response, and checks the appointment state by calling GET /api/appointments/{appointment_id}.
- For idempotency, we check the idempotency endpoint to ensure same response.
- Logs are written in JSONL in `logs/appointments.jsonl` for audit verification.
- The worker's attempts and compensation events are visible via logs and appointment states.
