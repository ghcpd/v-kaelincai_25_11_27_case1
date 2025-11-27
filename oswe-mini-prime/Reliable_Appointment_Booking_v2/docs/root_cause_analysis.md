# Root Cause Analysis: Appointment Confirmations 500s

Summary
-------
Intermittent HTTP 500 errors during the appointment confirmation path were caused by uncaught exceptions and timed-out responses from an external calendar sync service. The system previously wrote to the local DB and immediately attempted calendar sync; when calendar sync failed or timed out, the error bubbled up to the client and the local DB state wasn't consistently rolled back or compensated, producing double bookings and inconsistent client responses.

Call Flow & Crash Points
------------------------
- Client => POST /api/appointments
- Controller writes reservation to DB (state=IN_PROGRESS)
- Controller attempts calendar_booking via HTTP POST to external calendar
  - Crash points: HTTP timeout (RequestException), 5xx response, malformed JSON
- Without idempotency, repeated requests can create multiple rows with same slot
- No transactional outbox: calendar request and DB write are not coordinated for durability
- No circuit breaker: repeated failures cause cascading errors

Evidence
--------
- Logs (structured) show `appointment_created` followed by `calendar_exception` and `appointment_failed` without `appointment_confirmed`.
- DB state snapshot shows reservation with state=IN_PROGRESS or FAILED in cases where client saw 500.
- Replayed requests with same idempotency key resulted in repeated DB entries prior to the fix.

Example log snippet (structured):

{"timestamp":"...Z","event":"appointment_created","appointment_id":"uuid","state":"IN_PROGRESS","message":"..."}
{"timestamp":"...Z","event":"calendar_exception","appointment_id":"uuid","request_id":"...","message":"Read timed out"}
{"timestamp":"...Z","event":"appointment_cancelled","appointment_id":"uuid","state":"CANCELLED","message":"Read timed out"}

Recommendations
---------------
(Consolidated into remediation plan)

