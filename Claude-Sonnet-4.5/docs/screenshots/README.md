# UI Screenshots Documentation

This directory contains screenshots of the appointment booking UI demonstrating various states and workflows.

## Screenshot Inventory

### 1. Success Flow
**File**: `01_success_confirmed.png`  
**Description**: Appointment successfully confirmed  
**State**: CONFIRMED  
**Details**:
- Green success panel showing "✅ Appointment Confirmed"
- Appointment ID and Calendar Event ID displayed
- State flow shows: Initiated → DB Write → Calendar Sync → **Confirmed** (highlighted)
- All state steps marked as completed

**What to capture**:
- Open `frontend/index.html` in browser
- Select "Success (Normal)" from test scenario dropdown
- Fill in patient ID, doctor, date/time
- Click "Book Appointment"
- Wait for success message
- Take screenshot

---

### 2. Timeout / In-Progress Flow
**File**: `02_timeout_in_progress.png`  
**Description**: Calendar sync timed out, appointment queued for retry  
**State**: PENDING_RETRY (IN_PROGRESS)  
**Details**:
- Orange/yellow in-progress panel showing "⏳ Processing..."
- Spinner animation visible
- Message: "Calendar sync timed out. Appointment queued for retry."
- Warning box showing poll URL for status checking
- State flow shows: Initiated → DB Write → **Calendar Sync** (active with spinner)

**What to capture**:
- Select "Timeout (11s delay)" from test scenario dropdown
- Fill in appointment details
- Click "Book Appointment"
- Wait 11 seconds for timeout
- Take screenshot of in-progress state

---

### 3. Idempotent Retry Blocked
**File**: `03_idempotent_retry.png`  
**Description**: Duplicate request blocked by idempotency layer  
**State**: CONFIRMED (cached)  
**Details**:
- Green success panel (same as success flow)
- Response includes `"idempotent": true` field in details
- Same Appointment ID returned
- Status details show "Idempotent: true"
- Message indicates this is a cached response

**What to capture**:
1. First, submit a successful appointment booking
2. Note the Request ID from status details
3. Without refreshing, click "Book Appointment" again with same details
4. System returns cached response
5. Take screenshot showing idempotency hit
6. (Note: Frontend demo doesn't persist request ID, so this is conceptual - in real implementation, Request-ID header would be reused)

---

### 4. Failure - Service Unavailable
**File**: `04_failure_service_unavailable.png`  
**Description**: Calendar service returned 503, compensation triggered  
**State**: FAILED (after compensation)  
**Details**:
- Red failure panel showing "❌ Booking Failed"
- Error code: SERVICE_UNAVAILABLE
- Error message: "Calendar service is temporarily unavailable"
- Retry after: 30 seconds
- State flow stops at Calendar Sync (no Confirmed step reached)

**What to capture**:
- Select "Service Unavailable (503)" from test scenario dropdown
- Fill in appointment details
- Click "Book Appointment"
- Wait for error response
- Take screenshot of failure state

---

### 5. Failure - Rate Limited
**File**: `05_failure_rate_limited.png`  
**Description**: Calendar service rate limit exceeded (429)  
**State**: FAILED  
**Details**:
- Red failure panel
- Error code: RATE_LIMITED
- Error message: "Calendar service rate limit exceeded"
- Retry after: 60 seconds
- Suggests user should wait before retrying

**What to capture**:
- Select "Rate Limited (429)" from test scenario dropdown
- Fill in appointment details
- Click "Book Appointment"
- Take screenshot of rate limit error

---

### 6. Compensation Flow
**File**: `06_compensation_triggered.png`  
**Description**: Partial success with DB write but calendar failure - shows compensation  
**State**: COMPENSATING → FAILED  
**Details**:
- Red failure panel
- Message indicates DB rollback occurred
- Status shows appointment record was deleted (compensation)
- No appointment ID in final state (or marked as CANCELLED)

**What to capture**:
- Select "Service Unavailable (503)" scenario
- This triggers compensation logic (DB write succeeds, calendar fails, then rollback)
- Take screenshot showing failed state with compensation details

---

## Instructions for Generating Screenshots

### Prerequisites
- Python 3.x installed
- All dependencies installed (see `requirements.txt`)
- Frontend HTML file ready at `frontend/index.html`

### Steps
1. **Open Frontend UI**:
   ```bash
   # Open in your default browser
   start frontend/index.html  # Windows
   open frontend/index.html   # macOS
   xdg-open frontend/index.html  # Linux
   ```

2. **Resize Browser Window**:
   - Set browser width to 1200px
   - Set browser height to 900px
   - This ensures consistent screenshot dimensions

3. **Capture Screenshots**:
   For each scenario:
   - Select the appropriate test scenario from dropdown
   - Fill in appointment details:
     - Patient ID: P10001
     - Doctor: Dr. Sarah Johnson - Cardiology
     - Date/Time: Tomorrow at 2:00 PM
   - Click "Book Appointment"
   - Wait for state transition to complete
   - Take screenshot using:
     - Windows: Win + Shift + S (Snipping Tool)
     - macOS: Cmd + Shift + 4
     - Linux: Use Screenshot utility
   - Save with appropriate filename (e.g., `01_success_confirmed.png`)

4. **Annotate (Optional)**:
   - Use image editing tool to add arrows/callouts
   - Highlight key UI elements:
     - Request ID
     - State flow progression
     - Error messages
     - Retry warnings

### Screenshot Specifications
- **Format**: PNG
- **Resolution**: 1200x900 (or native browser size)
- **Color**: RGB
- **Compression**: Medium (balance quality and file size)
- **File naming**: `##_description.png` (e.g., `01_success_confirmed.png`)

---

## Screenshot Metadata

### Success Flow
```json
{
  "file": "01_success_confirmed.png",
  "scenario": "success",
  "http_status": 200,
  "appointment_status": "confirmed",
  "states_shown": ["initiated", "in_progress", "calendar_syncing", "confirmed"],
  "key_elements": ["appointment_id", "calendar_event_id", "green_success_panel"]
}
```

### Timeout Flow
```json
{
  "file": "02_timeout_in_progress.png",
  "scenario": "timeout",
  "http_status": 202,
  "appointment_status": "in_progress",
  "states_shown": ["initiated", "in_progress", "calendar_syncing"],
  "key_elements": ["spinner", "poll_url", "retry_warning", "orange_panel"]
}
```

### Failure Flow (Service Unavailable)
```json
{
  "file": "04_failure_service_unavailable.png",
  "scenario": "service_unavailable",
  "http_status": 503,
  "appointment_status": "failed",
  "states_shown": ["initiated", "in_progress", "calendar_syncing"],
  "key_elements": ["error_code", "retry_after", "red_failure_panel"]
}
```

---

## Verification Checklist

For each screenshot, verify:
- [ ] State flow visualization is visible
- [ ] Status panel shows correct color (green/orange/red)
- [ ] Icon matches state (✅/⏳/❌)
- [ ] Request ID is visible in status details
- [ ] Appointment ID is shown (or "N/A" for failures)
- [ ] Error messages are clear and actionable
- [ ] Sensitive data is NOT visible (PII redacted)
- [ ] Timestamp or date/time fields are reasonable
- [ ] UI is fully rendered (no loading artifacts)

---

## Redaction Requirements

Before sharing screenshots externally:
1. **Redact Request IDs** if they're real UUIDs (replace with placeholder)
2. **Redact Appointment IDs** if using production data
3. **Redact Patient IDs** if using real identifiers
4. **Blur browser tabs** if other sensitive content is visible
5. **Remove system time** from taskbar if revealing internal schedules

Example redaction:
- Original: `req-a1b2c3d4-e5f6-7890-abcd-ef1234567890`
- Redacted: `req-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`

---

## Screenshot Comparison

### Before (Old System)
- Only shows HTTP 500 error on any failure
- No state progression visible
- No retry information
- Cryptic error messages
- User doesn't know if appointment was created

### After (Reliable_v2)
- Clear state progression (Initiated → DB Write → Calendar Sync → Confirmed)
- Distinguishes between success, in-progress, and failure
- Provides retry information (202 Accepted with poll URL)
- User-friendly error messages with error codes
- Shows whether appointment was created (Appointment ID present/absent)

---

**Last Updated**: 2025-11-27  
**Prepared By**: QA Team  
**Status**: Ready for screenshot capture
