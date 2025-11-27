# Root Cause Analysis: Appointment Confirm HTTP 500s

Summary:
- Intermittent HTTP 500s occurred during appointment confirmations primarily due to uncaught exceptions and external calendar sync timeouts. When the calendar service timed out or returned malformed responses, exceptions bubbled up and the user-facing API returned 500s while database state sometimes persisted (leading to inconsistent state and possible double bookings).

Call flow:
1. Client -> API /appointments/confirm
2. API validates and creates appointment record (status IN_PROGRESS)
3. API calls calendar sync adapter
4. Calendar adapter times out or returns invalid data -> exception
5a. Exception not handled correctly -> API crashes and returns 500
5b. In some cases calendar call succeeded but DB update later failed -> reservation existed but user saw error

Crash points identified:
- calendar_adapter.create_booking: timeouts and unhandled exceptions bubbled up to calling controller
- commit ordering: appointment persisted before calendar was confirmed; without compensation, DB and calendar diverge
- lack of idempotency: duplicate client_request_id could create multiple appointments when retries occurred

Evidence (logs & stack snippets):
- Logs: structured entries showing request ID, appointment ID, and trace of adapter errors
- Stack snippets: simulated in logs showing httpx timeout or JSON decode errors from the calendar service

State snapshots:
- Request ID: req_timeout_1
- Calendar response: Timeout
- DB state: No appointment (deleted on rollback)

Conclusion:
- Root cause: Lack of transactional control and compensation logic around the external calendar sync plus no idempotency handling for client-requested retries. Timeouts in calendar sync cause unhandled exceptions.
