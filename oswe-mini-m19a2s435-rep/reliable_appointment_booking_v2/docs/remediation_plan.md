# Remediation Plan: Reliable_Appointment_Booking_v2

Objectives:
- Ensure success is returned only after DB slot reserved and calendar sync confirmed.
- Return deterministic failure or IN_PROGRESS on errors, and avoid double booking.
- Provide idempotency keyed by client_request_id.
- Implement compensation and outbox for eventual consistency.

High-level changes:
- Add idempotency layer to dedupe requests by client_request_id.
- Introduce an outbox table and background worker to process calendar sync actions with retries/backoff.
- Add synchronous attempt during API call for quick successes; if sync fails, roll back DB or mark IN_PROGRESS.
- Add compensation logic: if calendar booking exists but DB state inconsistent, cancel calendar entry.
- Circuit breaker around calendar adapter.
- Structured JSON logging with request and appointment IDs, redacting PII.

Rollout plan (phased):
1. Deploy new API with outbox and idempotency toggled on as feature flag. Monitor audit logs and success rate.
2. Enable circuit breaker thresholds and retry policies.
3. Monitor error budget; if regressions detected, toggle feature off and rollback.
4. Acceptance: all five integration tests pass and log metrics meet expectations.

Rollback strategy:
- If new system introduces regressions, revert feature flag or restore previous service version.

Tasks:
- Implement DB schema and outbox worker (done).
- Implement calendar adapter with retries and CB (done).
- Implement idempotency layer and test harness (done).
- Add structured logging to all flows (done).
- Run integration tests and iterate.
