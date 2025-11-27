# Remediation Plan: Reliable_Appointment_Booking_v2

## Overview

This document outlines the architecture changes, implementation tasks, and rollout strategy to fix appointment booking HTTP 500 defects.

## Architecture Changes

### 1. State Machine with Clear Transitions

**Before:**
- No clear status tracking
- Ambiguous state after failures

**After:**
```python
class AppointmentStatus(Enum):
    INIT = "INIT"
    IN_PROGRESS = "IN_PROGRESS"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    PARTIAL = "PARTIAL"
    COMPENSATING = "COMPENSATING"

# Valid transitions enforced:
INIT → [IN_PROGRESS, FAILURE]
IN_PROGRESS → [SUCCESS, FAILURE, PARTIAL, COMPENSATING]
PARTIAL → [SUCCESS, FAILURE]
COMPENSATING → [FAILURE, SUCCESS]
SUCCESS/FAILURE → []  # Terminal states
```

**Benefit:** Clear state machine prevents invalid transitions, aids troubleshooting.

---

### 2. Idempotency via Request ID

**Before:**
- No tracking of client requests
- Duplicate submissions create multiple bookings

**After:**
```python
class IdempotencyStore:
    def get(request_id: str) → Optional[CachedResponse]
    def set(request_id: str, response: Dict)
    def exists(request_id: str) → bool

# Flow:
1. Check: existing = db.get_by_request_id(request_id)
2. If exists: return cached response + is_idempotency_hit=true
3. Else: create appointment, store response
```

**Implementation:**
- In-memory store for development (can upgrade to Redis/DynamoDB)
- Production: distributed cache (Redis) or database table

**Benefit:** Prevents double-booking from retries, deterministic behavior.

---

### 3. Timeout & Retry with Exponential Backoff

**Before:**
- No timeout enforcement
- No retry logic (client retries unpredictably)
- Cascading failures

**After:**
```python
class RetryPolicy:
    def __init__(
        max_retries: int = 3,
        initial_delay_ms: int = 100,
        max_delay_ms: int = 5000,
        strategy: RetryStrategy = EXPONENTIAL,
        jitter: bool = True
    )

# Backoff: 100ms → 200ms → 400ms → 800ms (capped at 5s)
# Jitter: ±25% randomization to prevent thundering herd
```

**Benefit:** Resilient to transient failures, server load aware.

---

### 4. Circuit Breaker Pattern

**Before:**
- Cascading failures to calendar service
- No recovery detection

**After:**
```python
class CircuitBreaker:
    CLOSED → OPEN (after 5 failures)
    OPEN → HALF_OPEN (after 30s recovery timeout)
    HALF_OPEN → CLOSED (on success) or OPEN (on failure)

# Effect:
- CLOSED: Normal operation
- OPEN: Fail fast, don't call service
- HALF_OPEN: Test if service recovered
```

**Benefit:** Prevents cascading failures, faster failure detection.

---

### 5. Compensation / Saga Pattern

**Before:**
- No rollback on calendar sync failure
- Inconsistent state (booked locally but not synced)

**After:**
```python
# Compensation triggers on calendar failure:
1. Log compensation trigger
2. Delete appointment from DB
3. Release slot reservation
4. Transition to FAILURE
5. Return 500 to client (but DB is clean)

# On retry:
- DB is clean, can retry from scratch (idempotency ensured)
- No orphaned records
```

**Benefit:** Ensures consistency, enables safe retries.

---

### 6. Structured Audit Logging

**Before:**
- Raw exceptions logged (if at all)
- No audit trail for reconciliation

**After:**
```json
{
  "timestamp": "2025-11-27T10:30:00Z",
  "event_type": "CALENDAR_SYNC_TIMEOUT",
  "appointment_id": "apt_550e8400e29b41d4a716",
  "request_id": "req_6ba7b810550e8400e29b41d4a716",
  "status": "IN_PROGRESS",
  "user_id": "usr_abcd...",
  "error_code": "CALENDAR_TIMEOUT",
  "duration_ms": 5000,
  "calendar_response": {
    "http_status": 0,
    "response_time_ms": 5000,
    "error_type": "timeout"
  },
  "db_state": {
    "appointment_exists": true,
    "slot_reserved": false,
    "reservation_count": 0
  }
}
```

**Benefits:**
- Complete audit trail for reconciliation
- Structured for log aggregation tools (ELK, Datadog)
- Sensitive data redacted (user IDs hashed)

---

## Implementation Task Breakdown

### Phase 1: Core Domain Models (2 days)

| Task | Description | Owner | Status |
|------|-------------|-------|--------|
| models.py | Appointment, Status, Error enums, State machine | Backend | ✓ |
| resilience.py | Retry, Circuit breaker, Backoff strategies | Backend | ✓ |
| audit_logger.py | Structured logging, Event types | Backend | ✓ |

### Phase 2: Service Layer (3 days)

| Task | Description | Owner | Status |
|------|-------------|-------|--------|
| calendar_adapter.py | Timeout, retry, circuit breaker | Backend | ✓ |
| appointment_service.py | Idempotency, compensation, state transitions | Backend | ✓ |
| database.py | In-memory DB with slot tracking | Backend | ✓ |

### Phase 3: API Layer (2 days)

| Task | Description | Owner | Status |
|------|-------------|-------|--------|
| api.py | Flask endpoints, request validation | Backend | ✓ |
| Mock calendar service | Controllable errors/timeouts | QA | ✓ |

### Phase 4: Testing (3 days)

| Task | Description | Owner | Status |
|------|-------------|-------|--------|
| 5 integration test scenarios | Test suite with assertions | QA | ✓ |
| run_suite.py | Test runner and reporting | QA | ✓ |
| appointment_cases.yaml | Test case definitions | QA | ✓ |

### Phase 5: Frontend & Documentation (2 days)

| Task | Description | Owner | Status |
|------|-------------|-------|--------|
| frontend/index.html | Interactive booking UI | Frontend | ✓ |
| docs/ | Architecture, root cause, remediation | Tech Lead | ✓ |
| README.md | Setup and usage guide | Tech Lead | ✓ |

**Total: 12 days (2 weeks)**

---

## Configuration Parameters

### Calendar Adapter

```python
CalendarAdapter(
    timeout_sec=5.0,           # Timeout for calendar service
    max_retries=2,              # Retry attempts
    retry_strategy=EXPONENTIAL, # Backoff strategy
    initial_delay_ms=100,       # Initial backoff
    jitter=True                 # Add randomization
)
```

### Circuit Breaker

```python
CircuitBreaker(
    failure_threshold=5,        # Failures before opening
    recovery_timeout_sec=30,    # Time before half-open
    name="calendar_service"
)
```

### Deployment

```yaml
Environment Variables:
  CALENDAR_TIMEOUT_SEC: 5.0
  MAX_RETRIES: 2
  CIRCUIT_BREAKER_THRESHOLD: 5
  AUDIT_LOG_FILE: /var/log/appointments/audit.log
  IDEMPOTENCY_STORE: redis  # or in_memory for dev
  REDIS_URL: redis://localhost:6379  # if using redis
```

---

## Rollout & Rollback Strategy

### Pre-Rollout (2 days)

1. **Staging Environment Testing**
   - Run full integration test suite
   - Load testing: 1000 concurrent bookings
   - Calendar service failure injection
   - Verify audit logs in production format

2. **Canary Deployment** (5% of traffic)
   - Monitor error rates, latency, compensation triggers
   - Compare with current version (shadow traffic)
   - Verify idempotency effectiveness

### Rollout (1 day)

```
Week 1: Canary (5% traffic) → Monitor 2 hours
Week 2: Progressive rollout
  Day 1: 10% traffic
  Day 2: 25% traffic
  Day 3: 50% traffic
  Day 4: 100% traffic
```

### Rollback Plan (30 mins)

If issues detected:

```bash
# Immediate rollback to previous version
kubectl rollout undo deployment/appointment-api

# Reset affected appointments
scripts/reset_appointment_state.sh --date="2025-11-27" --status="PARTIAL"

# Audit events remain for investigation
# No data loss
```

---

## Success Criteria

| Metric | Current | Target | Measurement |
|--------|---------|--------|-------------|
| HTTP 500 rate | ~5% | <0.5% | CloudWatch |
| Double-booking incidents | ~10/month | 0 | Manual count |
| Calendar timeout recovery | None | 100% | Test suite |
| Idempotency hit rate | 0% | >10% | Audit logs |
| Audit trail completeness | None | 100% | ELK aggregation |
| False negatives | High | 0 | User feedback |

---

## Monitoring & Alerting

### Metrics to Track

```
appointment_booking.requests_total (counter)
  - status: success, failure, partial, timeout
  - idempotency_hit: yes, no

appointment_booking.calendar_sync_duration_ms (histogram)
  - status: timeout, success, error

appointment_booking.compensation_actions_total (counter)
  - action: db_rollback, slot_release

calendar_adapter.circuit_breaker_state (gauge)
  - state: closed, open, half_open

appointment_booking.audit_log_events_total (counter)
  - event_type: init, sync_success, sync_failure, compensation, etc.
```

### Alerting Rules

```
# Alert if 500 rate > 2%
error_rate > 0.02 → Page on-call

# Alert if circuit breaker OPEN > 5 mins
circuit_breaker_state == OPEN for 5m → Page on-call

# Alert if audit logs not received for 5 mins
rate(audit_events[5m]) == 0 → Warning

# Alert if compensation rate > 10%
compensation_rate > 0.1 → Investigation needed
```

---

## Documentation

### For Developers

- `src/models.py` - Domain model documentation
- `src/appointment_service.py` - Service logic and flow
- `src/calendar_adapter.py` - Resilience patterns
- `docs/remediation_plan.md` - This file

### For Operators

- `docs/operation_guide.md` - Deployment, monitoring, troubleshooting
- Alert runbooks for each metric
- Compensation recovery procedures

### For QA/Support

- `tests/run_suite.py` - Integration test harness
- `TESTING_GUIDE.md` - How to run/extend tests
- `logs/audit_schema.json` - Audit log reference

---

## Future Improvements

1. **Distributed Idempotency Store**
   - Replace in-memory with Redis/DynamoDB for multi-server setup
   - TTL: 24-48 hours (tunable)

2. **Enhanced Compensation**
   - Sagas for multi-step workflows (room booking → resource scheduling)
   - Automatic reconciliation job (nightly)

3. **Analytics**
   - Dashboard showing success rate, retry distribution, error trends
   - ML-based anomaly detection for cascade failures

4. **API Versioning**
   - v1: Current (deprecated)
   - v2: New resilient version
   - v3: Future streaming/async API

---

## Questions & Escalation

| Question | Owner | Timeline |
|----------|-------|----------|
| Should we use external cache for idempotency? | Platform | Architecture review |
| Retention period for audit logs? | Security | Compliance review |
| SLA for appointment booking? | Product | Business review |
