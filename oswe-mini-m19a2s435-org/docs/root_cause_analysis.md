# Root Cause Analysis

## Summary

When users confirm appointments, we create a local appointment and then call an external calendar service to create a calendar entry. Failures occur when the third-party calendar times out or returns malformed responses. The current implementation does not properly handle exceptions or provide idempotency, leading to: crashes (HTTP 500), partially-applied state (appointment persisted without calendar entry), and potential double-booking on retries.

## Call Flow

1. Client -> /appointments/confirm -> Controller
2. Controller writes appointment to DB (sometimes) and forwards to calendar sync
3. CalendarAdapter.post -> third-party returns timeout or 500 or malformed data
4. Exceptions bubble up -> no clean rollback or compensation -> controller returns 500

## Observations & Evidence

- Stack traces show HTTP call blocking beyond configured client timeouts.
- Logs show uncaught exceptions from calendar adapter.
- DB often contains appointments in IN_PROGRESS status without calendar_event_id. Some persisted appointments remain despite API returning error, leading to the UI showing failure but the slot being reserved in the DB.

## Crash Points

- Uncaught HTTP errors from calendar client
- Missing idempotency checks at controller level
- No transactional outbox: local appointment persisted even when calendar fails
- No compensation (SAGA) after repeated outbox failures

## State Snapshot Example

- Request ID: req-timeout-1
- DB: appointment exists with status IN_PROGRESS (or absent depending on rollback)
- Calendar: no event created; request timed out
- Log excerpt (structured):
  - {"request_id":"req-timeout-1","message":"Calendar request failed","level":"ERROR", "appointment_id": 123}
  - {"request_id":"req-timeout-1","message":"Rolling back to avoid booking","level":"ERROR"}

