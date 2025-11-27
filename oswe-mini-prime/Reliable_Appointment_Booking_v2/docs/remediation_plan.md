# Remediation Plan: Reliable_Appointment_Booking_v2

Goals
-----
- Guarantee idempotent appointment creation keyed by a client-provided idempotency key.
- Ensure success is only returned when local slot reservation and calendar confirmation succeed.
- Introduce compensation to revert local reservations when calendar sync fails.
- Add retry/backoff for transient calendar errors; observe circuit breaker behavior.
- Emit structured logs and an audit trail with appointment/request IDs.

Design Changes
--------------
- Idempotency: store Idempotency keys with response and appointment reference. Reuse stored responses for duplicate keys.
- State machine: appointment states: INIT -> IN_PROGRESS -> CONFIRMED or CANCELLED (FAILED).
- Calendar Integration: implement adapter with timeouts, retry and a simple circuit breaker.
- Transactional Outbox/Worker: create outbox for background retries; worker processes the outbox to reattempt calendar sync if desired.
- Compensation: on calendar failure, cancel reservation and mark CANCELLED.
- Observe and log: structured JSON logs for all transitions.

Rollout Plan
------------
1. Add idempotency and state machine logic to API.
2. Add calendar adapter, outbox worker and retry policies.
3. Deploy under feature flag; switch traffic gradually.
4. Monitor structured logs, metrics for retries, idempotency hits, and compensation events.
5. Once validated, remove feature flag and deprecate old endpoints.

Rollback Plan
-------------
- Revert to prior commit and notify operations teams to reconcile any half-completed entries via ad-hoc tools.
- Use audit logs to reconcile final state.

Testing
-------
- Run integration suite to confirm the following scenarios pass: success, timeout->500->no booking, idempotent retry, partial success with compensation, audit verification.

