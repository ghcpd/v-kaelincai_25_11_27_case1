# Root Cause Analysis: Appointment Booking HTTP 500 Defects

## Executive Summary

The Appointment Booking API intermittently returns HTTP 500 errors when confirming appointments due to:

1. **Uncaught exceptions** from external calendar service timeouts/failures
2. **Missing idempotency** - duplicate requests create multiple bookings for same slot
3. **No compensation logic** - failed calendar sync leaves DB in inconsistent state (local booking exists but calendar not synced)
4. **Lack of state management** - no clear distinction between partial success vs failure
5. **Non-standardized errors** - exceptions bubble up without classification

## Issue Flow Diagram

```
Client Request
    ↓
[INIT] Create Appointment locally
    ↓
    ├─→ Success: [IN_PROGRESS]
    │       ↓
    │   Call Calendar Service
    │       ↓
    │       ├─→ Success (200): [SUCCESS] ✓
    │       │
    │       ├─→ Timeout (>5s): ✗ UNCAUGHT EXCEPTION
    │       │   HTTP 500 returned
    │       │   DB record PERSISTS (inconsistent state)
    │       │   Slot may be reserved
    │       │
    │       ├─→ Invalid Response (400-599): ✗ UNCAUGHT EXCEPTION
    │       │   HTTP 500 returned
    │       │   DB record PERSISTS (inconsistent state)
    │       │
    │       └─→ Timeout + Retry: Retry logic missing
    │           Multiple attempts without backoff
    │           Circuit breaker not implemented
    │
    └─→ DB Conflict: [FAILURE]
        Idempotency not enforced
```

## Root Cause Evidence

### 1. Uncaught Calendar Service Exceptions

**Problem:**
- External calendar service may timeout or return malformed responses
- No timeout enforcement at service level
- Exceptions propagate directly to caller

**Evidence:**
```python
# OLD CODE (hypothetical):
calendar_response = requests.get(calendar_url, timeout=None)  # No timeout!
data = calendar_response.json()  # Can fail if response malformed
return data['slot_id']  # KeyError if field missing
```

**Impact:**
- HTTP 500 returned to client
- Appointment persists in DB even though calendar sync failed
- Client sees "failure" but slot may actually be reserved (race condition)

### 2. Missing Idempotency

**Problem:**
- No request ID tracking
- Same request submitted twice creates two appointments
- Both appointments may reserve same calendar slot

**Evidence:**
```
Request 1: POST /appointments (request_id=abc123)
  → Creates appointment_id=apt_001, reserves slot_1

Request 2: POST /appointments (request_id=abc123)  # Same ID, retry by client
  → Creates appointment_id=apt_002, reserves slot_1
  
Result: Double-booking! Both apt_001 and apt_002 for slot_1
```

**Impact:**
- Calendar slot over-booked
- Inconsistent counts and reservation conflicts
- Difficult to reconcile which booking is "real"

### 3. No Compensation on Failure

**Problem:**
- When calendar sync fails, no rollback executed
- Appointment remains in DB even though sync failed
- State is PARTIAL (booked locally but not in calendar)

**Evidence:**
```
Step 1: Appointment created in DB (INIT → IN_PROGRESS)
Step 2: Calendar sync called
Step 3: Calendar returns 503 (timeout/error)
Step 4: No compensation executed
Result: Appointment stays in DB
  - Status: ?
  - Calendar status: unknown
  - Client sees 500 error but appointment may exist
  - Retry attempt may succeed or fail unpredictably
```

**Impact:**
- Inconsistent local/remote state
- Manual reconciliation required
- Customer confusion: "Did my appointment book or not?"

### 4. Missing State Management

**Problem:**
- No clear appointment status transitions
- No distinction between:
  - INIT (just created)
  - IN_PROGRESS (local booking done, syncing with calendar)
  - SUCCESS (both DB and calendar synced)
  - PARTIAL (DB done but calendar not)
  - FAILURE (rolled back)

**Impact:**
- State unclear after failure
- Difficult to determine if compensation needed
- Audit trail unclear

### 5. Non-Standardized Errors

**Problem:**
- Raw exceptions returned
- No error classification
- Difficult to determine if error is retryable

**Example:**
```
HTTP 500
{
  "error": "Connection reset by peer"
}
vs.
HTTP 500
{
  "error": "timed out"
}
vs.
HTTP 500
{
  "error": "Invalid JSON response"
}
```

**Impact:**
- Difficult for client to implement smart retry logic
- All 500s treated same (all retried or all abandoned)
- Non-deterministic behavior

## Call Flow Analysis

### Current (Broken) Flow

```
POST /appointments
  ├─ Create appointment (no idempotency check)
  ├─ Save to DB (no state tracking)
  ├─ Call calendar_service.sync()
  │  └─ requests.get(url, timeout=None)  ← Can hang indefinitely!
  ├─ If timeout/error → Exception not caught
  │  └─ 500 returned, DB record left as-is
  ├─ If success → Return 200
  └─ No compensation logic
```

### New (Fixed) Flow

```
POST /appointments
  ├─ Check idempotency (request_id)
  │  └─ If duplicate → Return cached response ✓
  ├─ Create appointment (status=INIT)
  ├─ Save to DB
  ├─ Transition to IN_PROGRESS
  ├─ Call calendar_adapter.sync_appointment()
  │  ├─ Enforce 5s timeout
  │  ├─ Implement retry with exponential backoff
  │  ├─ Circuit breaker for cascading failures
  │  └─ Catch all exceptions → CalendarResponse with error_code
  ├─ If calendar success
  │  ├─ Reserve slot
  │  ├─ Transition to SUCCESS
  │  └─ Return 201 ✓
  ├─ If calendar failure
  │  ├─ Log compensation trigger
  │  ├─ Delete appointment from DB
  │  ├─ Transition to FAILURE
  │  └─ Return 500 (but DB is clean)
  └─ Emit structured audit logs for all steps
```

## Database State Snapshots

### Scenario: Calendar Timeout

```
BEFORE calendar sync:
  appointments: {apt_001: {status: IN_PROGRESS, slot: null}}
  slot_reservations: {}

AFTER calendar timeout (OLD CODE):
  appointments: {apt_001: {status: ???, slot: null}}  ← Inconsistent!
  slot_reservations: {}

AFTER calendar timeout (NEW CODE):
  appointments: {}  ← Cleaned up via compensation
  slot_reservations: {}
```

### Scenario: Idempotent Retry

```
Request 1: request_id=req_abc123
AFTER:
  appointments: {apt_001: {status: SUCCESS, slot: slot_1}}
  request_ids: {req_abc123: apt_001}
  slot_reservations: {slot_1: [apt_001]}

Request 2: request_id=req_abc123 (duplicate)
AFTER:
  appointments: {apt_001: ...}  ← Unchanged!
  request_ids: {req_abc123: apt_001}
  slot_reservations: {slot_1: [apt_001]}
  → Return cached response for Request 1
```

## Error Classification Hierarchy

| Error Code | HTTP Status | Cause | Retryable? | Action |
|-----------|------------|-------|-----------|--------|
| CALENDAR_TIMEOUT | 0/500 | Calendar service timeout | Yes (exponential backoff) | Rollback DB, return 500 |
| CALENDAR_INVALID_RESPONSE | 500 | Malformed calendar response | Yes (limited) | Rollback DB, return 500 |
| DB_CONFLICT | 400 | Duplicate request/slot conflict | No | Return 400, cached response |
| DB_ERROR | 500 | Database operation failed | Yes (exponential backoff) | Return 500 |
| DUPLICATE_REQUEST | 201 | Idempotency hit | No (cached) | Return cached response |
| INTERNAL_ERROR | 500 | Unexpected error | No (circuit breaker) | Rollback DB, return 500 |
| SUCCESS | 201 | Appointment created and synced | N/A | Return appointment details |

## Impact Assessment

| Issue | Current Impact | Post-Fix Impact |
|-------|---|---|
| False negatives (user sees 500, slot actually booked) | HIGH - common in timeout scenarios | ELIMINATED - compensation ensures clean rollback |
| False positives (user sees success, slot not booked) | LOW - less common | ELIMINATED - only success if both DB and calendar succeed |
| Double-booking | MEDIUM - possible with retries | ELIMINATED - idempotency enforced |
| Manual reconciliation required | HIGH - state unclear | ELIMINATED - audit trail provides visibility |
| Non-deterministic behavior | HIGH - retry logic undefined | ELIMINATED - standardized errors and backoff |

## Metrics to Track Post-Fix

1. **Success Rate**: Percentage of bookings that complete with both DB and calendar in sync
2. **Idempotency Hit Rate**: Percentage of requests that hit idempotency store
3. **Compensation Rate**: Percentage of failures that trigger rollback
4. **Retry Count**: Distribution of retries attempted
5. **Calendar Timeout Rate**: Percentage of calendar calls that timeout
6. **Double-Booking Incidents**: Should be 0

## Testing Strategy

See `tests/integration/appointment_cases.yaml` for 5 comprehensive test scenarios:

1. **Normal Success**: Happy path verification
2. **Calendar Timeout → 500 with No Booking**: Verify compensation
3. **Idempotent Retry**: Verify no double-booking
4. **Partial Success → Compensation**: Verify state cleanup
5. **Audit Reconciliation**: Verify logging and traceability
