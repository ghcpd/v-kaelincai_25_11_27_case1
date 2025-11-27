# Appointment Booking System v2 - Setup & Usage Guide

## Quick Start

### 1. Environment Setup

```bash
# Clone or extract the project
cd workSpace

# Run setup script (creates venv, installs dependencies)
bash setup.sh

# Activate virtual environment
source venv/bin/activate
```

### 2. Run Integration Tests

```bash
# Run all 5 test scenarios
bash run_tests.sh

# Or run directly
bash scripts/run_appointment_suite.sh
```

Expected output:
```
✓ SCENARIO_1_NORMAL_SUCCESS
✓ SCENARIO_2_CALENDAR_TIMEOUT_NO_BOOKING
✓ SCENARIO_3_IDEMPOTENT_RETRY_NO_DOUBLE_BOOKING
✓ SCENARIO_4_PARTIAL_SUCCESS_COMPENSATION
✓ SCENARIO_5_AUDIT_AND_RECONCILIATION

Pass Rate: 100%
```

### 3. Run API Server (Optional - for manual testing)

```bash
# Terminal 1: Start Flask server
python3 src/api.py
# Listens on http://localhost:5000

# Terminal 2: Open frontend
# Navigate to: frontend/index.html in browser
# Or use simple HTTP server:
cd frontend
python3 -m http.server 8000
# Open http://localhost:8000
```

---

## Architecture Overview

### Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│ Client                                                           │
│ (Browser or CLI)                                                │
└────────────────────┬────────────────────────────────────────────┘
                     │ HTTP POST /api/appointments
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│ Flask API (src/api.py)                                          │
│ - Request validation                                            │
│ - Response formatting                                           │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│ AppointmentService (src/appointment_service.py)                 │
│ ├─ Idempotency check (request_id)                               │
│ ├─ State machine transitions                                    │
│ ├─ Compensation logic                                           │
│ └─ Audit logging                                                │
└────────────────────┬─────────────────┬──────────────────────────┘
                     │                 │
          ┌──────────▼──────┐ ┌────────▼───────────────┐
          │ AppointmentDB   │ │ CalendarAdapter        │
          │ (In-memory)     │ │ (src/calendar_adapter) │
          │                 │ │ - Timeout              │
          │ - Appointments  │ │ - Retry + backoff      │
          │ - Idempotency   │ │ - Circuit breaker      │
          │ - Slots         │ │ - Exception handling   │
          │                 │ └────────────┬───────────┘
          └─────────────────┘              │
                                           │
                                  ┌────────▼────────┐
                                  │ MockCalendar    │
                                  │ (mocks/)        │
                                  │ - Controllable  │
                                  │   errors        │
                                  │ - Delays        │
                                  └─────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ AuditLogger (src/audit_logger.py)                               │
│ - Structured JSON logging                                       │
│ - Event types, statuses, errors                                 │
│ - Redacted sensitive data                                       │
│ → logs/appointment_audit.log                                    │
└─────────────────────────────────────────────────────────────────┘
```

### State Machine

```
INIT
  │
  ├─→ IN_PROGRESS (booking locally)
  │     │
  │     ├─→ SUCCESS (calendar sync succeeded)
  │     │     └─→ [Terminal]
  │     │
  │     ├─→ FAILURE (calendar sync failed, compensated)
  │     │     └─→ [Terminal]
  │     │
  │     ├─→ PARTIAL (local booked, sync pending)
  │     │     └─→ SUCCESS or FAILURE
  │     │
  │     └─→ COMPENSATING (rolling back after failure)
  │           └─→ FAILURE or SUCCESS
  │
  └─→ FAILURE (immediate failure, no booking)
        └─→ [Terminal]
```

### Request Flow (Happy Path)

```
1. POST /appointments
   {
     "user_id": "user_001",
     "patient_name": "John Doe",
     "appointment_date": "2025-12-15",
     "appointment_time": "14:30",
     "request_id": "req_abc123"
   }

2. AppointmentService.request_appointment()
   a. Check idempotency (request_id in cache?)
   b. Create appointment (status=INIT)
   c. Save to database
   d. Transition to IN_PROGRESS
   e. Call calendar_adapter.sync_appointment()
      - Enforce 5s timeout
      - Retry max 2 times with exponential backoff
      - Circuit breaker (open after 5 failures)
   f. On success:
      - Reserve slot in database
      - Transition to SUCCESS
      - Return 201 + appointment details
   g. On failure:
      - Trigger compensation (delete from database)
      - Transition to FAILURE
      - Return 500 + error details

3. AuditLogger emits events:
   - APPOINTMENT_INIT
   - DB_RESERVE_START
   - CALENDAR_SYNC_START
   - CALENDAR_SYNC_SUCCESS (or TIMEOUT/ERROR)
   - FINAL_SUCCESS (or FAILURE)

4. All events logged with:
   - timestamp (ISO 8601)
   - event_type
   - appointment_id
   - request_id
   - status
   - error_code
   - redacted user_id
```

---

## Key Features

### 1. Idempotency via Request ID

Client must provide `request_id` (UUID). Same ID sent twice:

```
First request:
  → Creates appointment, returns 201

Second request (same request_id):
  → Returns cached response from first request
  → is_idempotency_hit=true
  → No new appointment created
  → No double-booking
```

### 2. Resilience Patterns

#### Timeout
- Calendar service calls have 5-second timeout
- Calls exceeding timeout treated as failure
- Appointment rolled back (no inconsistent state)

#### Retry with Exponential Backoff
- Transient failures retried automatically
- Backoff: 100ms → 200ms → 400ms → 800ms
- Jitter added (±25%) to prevent thundering herd

#### Circuit Breaker
- After 5 consecutive failures, circuit opens
- Subsequent calls fail fast (no retry)
- After 30 seconds, half-open state (test recovery)
- Success in half-open → circuit closes

### 3. Compensation / Saga Pattern

If calendar sync fails:
1. Appointment deleted from database
2. Slot reservation released
3. Appointment status set to FAILURE
4. Client receives 500 but database is clean
5. Retry is safe (no orphaned records)

### 4. Structured Audit Logging

Every step logged as JSON:

```json
{
  "timestamp": "2025-11-27T10:30:00.000Z",
  "event_type": "CALENDAR_SYNC_TIMEOUT",
  "appointment_id": "apt_...",
  "request_id": "req_...",
  "status": "IN_PROGRESS",
  "user_id": "usr_abcd...",
  "error_code": "CALENDAR_TIMEOUT",
  "duration_ms": 5123,
  "calendar_response": {
    "http_status": 0,
    "response_time_ms": 5000,
    "error_type": "timeout"
  },
  "db_state": {
    "appointment_exists": true,
    "slot_reserved": false
  }
}
```

**Benefits:**
- Complete audit trail for reconciliation
- Redacted sensitive data (user IDs hashed)
- Parseable by log aggregation tools (ELK, Datadog)

---

## Test Scenarios

### Scenario 1: Normal Success
- Calendar service returns success
- Appointment created and synced
- Expected: HTTP 201, status=SUCCESS

### Scenario 2: Calendar Timeout → 500 with No Booking
- Calendar service times out (6 seconds)
- Appointment created but rolled back via compensation
- Expected: HTTP 500, status=FAILURE, appointment deleted from DB

### Scenario 3: Idempotent Retry Without Double-Booking
- Same request_id submitted twice
- Second request returns cached response
- Expected: Only 1 appointment, only 1 slot reservation, is_idempotency_hit=true

### Scenario 4: Partial Success → Compensation
- Calendar returns 503 (server error)
- Appointment rolled back
- Expected: HTTP 500, status=FAILURE, compensation_action=DB_ROLLBACK

### Scenario 5: Audit Trail & Reconciliation
- All steps logged with timestamps and event types
- Sensitive data redacted
- Expected: 5+ audit events, no sensitive data exposed

---

## API Endpoints

### Create Appointment
```
POST /api/appointments

Request:
{
  "user_id": "user_001",
  "patient_name": "John Doe",
  "appointment_date": "2025-12-15",
  "appointment_time": "14:30",
  "request_id": "req_unique_id"  # Must be unique per client request
}

Response (201 Success):
{
  "appointment_id": "apt_...",
  "request_id": "req_unique_id",
  "status": "SUCCESS",
  "patient_name": "John Doe",
  "appointment_date": "2025-12-15",
  "appointment_time": "14:30",
  "calendar_slot_id": "cal_...",
  "error_code": null,
  "is_idempotency_hit": false,
  "created_at": "2025-11-27T10:30:00"
}

Response (500 Failure):
{
  "appointment_id": "apt_...",
  "request_id": "req_unique_id",
  "status": "FAILURE",
  "calendar_slot_id": null,
  "error_code": "CALENDAR_TIMEOUT",
  "error_message": "Calendar service timeout",
  "is_idempotency_hit": false
}

Response (201 Duplicate):
{
  "appointment_id": "apt_...",
  "request_id": "req_unique_id",
  "status": "SUCCESS",
  "is_idempotency_hit": true
  # ... cached response from original request
}
```

### Get Appointment
```
GET /api/appointments/{appointment_id}

Response (200):
{
  "appointment_id": "apt_...",
  ...
}

Response (404):
{
  "error": "Appointment not found"
}
```

### Get Statistics
```
GET /api/stats

Response:
{
  "database": {
    "total_appointments": 10,
    "by_status": {
      "SUCCESS": 8,
      "FAILURE": 2,
      "IN_PROGRESS": 0
    }
  },
  "calendar_adapter": {
    "circuit_breaker": {
      "state": "CLOSED",
      "failure_count": 0,
      "failure_threshold": 5
    }
  },
  "idempotency_store": {
    "cached_requests": 3
  }
}
```

### Admin: Reset All Data
```
POST /api/admin/reset

Response:
{
  "message": "All state reset"
}
```

### Admin: Configure Mock Calendar
```
POST /api/admin/mock-config

Request:
{
  "error_mode": "success|timeout|invalid_response|server_error",
  "timeout_ms": 6000
}

Response:
{
  "message": "Mock calendar configured",
  "error_mode": "timeout",
  "timeout_ms": 6000
}
```

---

## Configuration

### Environment Variables

```bash
# Calendar adapter timeout (seconds)
export CALENDAR_TIMEOUT_SEC=5.0

# Max retries for calendar sync
export MAX_RETRIES=2

# Circuit breaker failure threshold
export CIRCUIT_BREAKER_THRESHOLD=5

# Audit log file path
export AUDIT_LOG_FILE=logs/appointment_audit.log

# Idempotency store (in_memory | redis)
export IDEMPOTENCY_STORE=in_memory

# Redis URL (if using Redis for idempotency)
export REDIS_URL=redis://localhost:6379
```

---

## Monitoring & Troubleshooting

### View Audit Log

```bash
# Last 20 events
tail -20 logs/appointment_audit.log

# Pretty-print JSON
cat logs/appointment_audit.log | python3 -m json.tool | tail -50

# Filter by event type
grep COMPENSATION logs/appointment_audit.log

# Count by status
cat logs/appointment_audit.log | grep -o '"status":"[^"]*"' | sort | uniq -c
```

### Check System Statistics

```bash
curl http://localhost:5000/api/stats | python3 -m json.tool

# Example output:
{
  "database": {
    "total_appointments": 42,
    "by_status": {
      "SUCCESS": 40,
      "FAILURE": 2,
      "PARTIAL": 0
    }
  },
  "calendar_adapter": {
    "circuit_breaker": {
      "state": "CLOSED",
      "failure_count": 1,
      "failure_threshold": 5
    }
  }
}
```

### Common Issues

**Issue: Tests fail with "Connection refused"**
- Solution: Ensure Flask server is running or tests are using test client (default)

**Issue: Audit log not updating**
- Solution: Check file permissions on `logs/` directory
- Verify path in code matches `AUDIT_LOG_FILE` env var

**Issue: Idempotency not working**
- Solution: Verify request_id is same across retries
- Check that AppointmentService uses get_by_request_id()

**Issue: Compensation never triggered**
- Solution: Test with MockCalendarErrorMode.TIMEOUT or SERVER_ERROR
- Use admin endpoint to set error mode

---

## Development

### Adding New Test Scenario

Edit `tests/run_suite.py`:

```python
def _test_scenario_6_custom(self) -> Dict[str, Any]:
    """Custom test scenario"""
    reset_database()
    reset_calendar_service()
    
    # Setup
    calendar_service = get_calendar_service()
    calendar_service.set_error_mode(MockCalendarErrorMode.SUCCESS)
    
    # Execute
    response = self.client.post("/api/appointments", json={
        "user_id": "user_006",
        "patient_name": "Test User",
        "appointment_date": "2025-12-20",
        "appointment_time": "12:00",
        "request_id": "req_test_006"
    })
    
    data = response.get_json()
    
    # Assertions
    assertions = [
        ("HTTP 201", response.status_code == 201),
        ("Status SUCCESS", data.get("status") == "SUCCESS"),
    ]
    
    passed = all(result for _, result in assertions)
    
    return {
        "name": "SCENARIO_6_CUSTOM",
        "description": "Custom test scenario",
        "passed": passed,
        "assertions": assertions
    }
```

Then add to `run_all_tests()`:
```python
tests = [
    # ... existing tests ...
    self._test_scenario_6_custom,
]
```

### Extending the Calendar Adapter

Add new resilience pattern:

```python
class AdaptiveTimeout:
    """Adaptive timeout based on historical performance"""
    def __init__(self, percentile=95):
        self.percentile = percentile
        self.response_times = []
    
    def get_timeout(self):
        if not self.response_times:
            return 5.0
        return sorted(self.response_times)[int(len(self.response_times) * self.percentile / 100)] / 1000.0
    
    def record(self, duration_ms):
        self.response_times.append(duration_ms)

# Use in CalendarAdapter:
adaptive_timeout = AdaptiveTimeout()
# ... in sync_appointment():
actual_timeout = adaptive_timeout.get_timeout()
```

---

## File Structure

```
workSpace/
├── src/
│   ├── __init__.py
│   ├── models.py              # Domain models, state machine
│   ├── appointment_service.py # Service logic with compensation
│   ├── calendar_adapter.py    # Calendar integration with resilience
│   ├── database.py            # In-memory DB
│   ├── audit_logger.py        # Structured logging
│   ├── resilience.py          # Retry, circuit breaker
│   └── api.py                 # Flask API endpoints
├── mocks/
│   ├── __init__.py
│   └── mock_calendar_service.py # Simulated calendar
├── tests/
│   ├── __init__.py
│   ├── run_suite.py           # Integration test runner
│   └── integration/
│       └── appointment_cases.yaml.py
├── frontend/
│   └── index.html             # Interactive booking UI
├── docs/
│   ├── root_cause_analysis.md
│   ├── remediation_plan.md
│   ├── operation_guide.md
│   ├── audit_schema.json
│   └── screenshots/
├── logs/
│   └── appointment_audit.log  # Audit trail
├── scripts/
│   └── run_appointment_suite.sh
├── requirements.txt
├── setup.sh
├── run_tests.sh
└── README.md
```

---

## Next Steps

1. **Run integration tests**: `bash run_tests.sh`
2. **Review audit logs**: `tail -f logs/appointment_audit.log`
3. **Start API server**: `python3 src/api.py`
4. **Open frontend**: `frontend/index.html`
5. **Deploy to staging**: See remediation_plan.md

---

## Support

For issues or questions:
- Check `docs/root_cause_analysis.md` for context
- Review `docs/remediation_plan.md` for architecture
- Run test suite for validation: `bash run_tests.sh`
- Examine audit logs: `logs/appointment_audit.log`
