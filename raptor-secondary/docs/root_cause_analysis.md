# Reliable_Appointment_Booking_v2 – Root Cause Analysis

## Overview
- **Service:** Outpatient Appointment System
- **Issue:** Intermittent HTTP 500 on `Confirm Appointment` due to external calendar sync timeouts/exceptions. No idempotency or compensation; retries cause double booking.
- **Impact:** Users see failures while slots are reserved; repeated submits double-book; debugging slowed by unstructured logs.

## Appointment Lifecycle & Crash Points
```
init (request received)
  ↓ create DB row (IN_PROGRESS) + slot lock [CRASH: uncaught DB errors]
  ↓ calendar_sync (HTTP/gRPC)
     ├─ success → state=CONFIRMED → return 200
     ├─ timeout/exception/malformed → state=COMPENSATING → FAILED → return 500
     └─ circuit_open → return 503 (in-progress/try later)

Crash points observed:
- Uncaught calendar timeout/exception bubbles to API (500)
- Missing idempotency: same request_id not deduped → duplicate row + slot collision
- Missing compensation: on calendar failure, slot remained reserved → false negatives
- Logs unstructured; no correlation by request_id/appointment_id
```

## Evidence
### Structured log excerpts
```json
{"timestamp":"2025-11-27T05:29:02.449658Z","level":"WARNING","logger":"src.service","message":"calendar_failed","request_id":"req-docs-partial","appointment_id":"b27b0329-9410-46e0-a644-5e205dddb78d","slot_id":"slot-docs","error_code":"CALENDAR_EXCEPTION","error_detail":"partial"}
{"timestamp":"2025-11-27T05:29:02.475295Z","level":"INFO","logger":"src.service","message":"compensation_completed","request_id":"req-docs-partial","appointment_id":"b27b0329-9410-46e0-a644-5e205dddb78d","slot_id":"slot-docs","state":"FAILED"}
```

### State snapshot (post-partial failure)
```json
{
  "id": "b27b0329-9410-46e0-a644-5e205dddb78d",
  "request_id": "req-docs-partial",
  "slot_id": "slot-docs",
  "state": "FAILED",
  "calendar_synced": false,
  "retry_count": 0,
  "last_error_code": "CALENDAR_EXCEPTION",
  "last_error_message": "partial",
  "created_at": "2025-11-27T05:29:01.940888",
  "updated_at": "2025-11-27T05:29:02.468926"
}
```

### Failure scenarios (integration suite)
| Scenario | Symptom | Root Cause | Fix (v2) |
| --- | --- | --- | --- |
| Calendar timeout | 500 + slot reserved | No compensation; uncaught timeout | Retry+backoff, compensate, return 500 with `CALENDAR_TIMEOUT`; slot freed |
| Idempotent retry | Double booking | No request_id uniqueness | DB unique index on `request_id`; idempotent responses |
| Partial calendar | Inconsistent state | No saga compensation | Mark `COMPENSATING`→`FAILED`; release slot |
| Audit gaps | Slow triage | Unstructured logs | JSON logs with `request_id`/`appointment_id`, error codes |

## Conclusion
- Failures stem from missing idempotency and compensation around calendar sync, plus unstructured error handling.
- Reliable v2 adds: request_id idempotency, retries with backoff, simple circuit breaker, compensation, and structured auditing.
