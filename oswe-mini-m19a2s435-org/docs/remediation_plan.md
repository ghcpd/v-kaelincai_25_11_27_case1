# Remediation Plan: Reliable_Appointment_Booking_v2

## Goals
- Guarantee success only after both DB slot reserved AND calendar confirmation are successful (synchronous) or return deterministic `in_progress` when calendar confirmation is pending.
- Implement idempotency keyed by client_request_id to prevent duplicate bookings.
- Add a transactional outbox pattern for async confirms.
- Add compensation to release slots after repeated calendar failures.
- Standardize structured logs with `request_id`, `appointment_id`, and redacted sensitive fields.

## Changes to Implement
- Implement idempotency table to store request_id and response.
- Add a CalendarAdapter with sensible timeouts and circuit-breaker settings.
- Maintain a state machine per appointment: INIT -> IN_PROGRESS -> SUCCESS/FAILED.
- Use an outbox worker that retries calendar sync with backoff and on final failure triggers compensation.

## Rollout/Rollback Strategy
1. Add idempotency and structured logs behind a feature flag; enable for a subset of requests and monitor.
2. Add sync confirm path with rollback on failure to ensure no reservation occurs if calendar fails.
3. Add async confirm + outbox worker to support long-running calendar calls.
4. Add compensation logic and increase retries.

## Monitoring & Alerting
- Count of in_progress appointments older than threshold
- Number of outbox retries and compensations
- Calendar adapter timeouts and exception rates

## Validation
- The integration suite validates five scenarios including timeouts, idempotency, compensation and audit logs.

