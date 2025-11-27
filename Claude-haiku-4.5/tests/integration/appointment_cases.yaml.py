"""
Integration test scenarios for appointment booking
Tests idempotency, compensation, and resilience
"""
import yaml
from typing import Dict, Any, List


def load_test_scenarios() -> List[Dict[str, Any]]:
    """Load test scenarios from YAML"""
    scenarios_yaml = """
scenarios:
  - name: "SCENARIO_1_NORMAL_SUCCESS"
    description: "Normal booking flow - appointment created and synced successfully"
    steps:
      - action: "setup"
        config:
          error_mode: "success"
          delay_ms: 100
      - action: "create_appointment"
        input:
          user_id: "user_001"
          patient_name: "Alice Johnson"
          appointment_date: "2025-12-15"
          appointment_time: "14:30"
          request_id: "req_success_001"
        expected:
          status: "SUCCESS"
          http_code: 201
          error_code: null
          calendar_slot_id: null  # Will be set
    assertions:
      - type: "status_equals"
        value: "SUCCESS"
      - type: "appointment_exists"
      - type: "slot_reserved"
    description_long: |
      Tests the happy path: user submits appointment request, 
      it's created in DB, calendar sync succeeds, appointment is marked SUCCESS.
      Verifies: appointment exists, slot is reserved, status is SUCCESS.

  - name: "SCENARIO_2_CALENDAR_TIMEOUT_NO_BOOKING"
    description: "Calendar timeout (>5s) returns 500, no local booking persists"
    steps:
      - action: "setup"
        config:
          error_mode: "timeout"
          timeout_ms: 6000
      - action: "create_appointment"
        input:
          user_id: "user_002"
          patient_name: "Bob Smith"
          appointment_date: "2025-12-16"
          appointment_time: "15:00"
          request_id: "req_timeout_002"
        expected:
          status: "FAILURE"
          http_code: 500
          error_code: "CALENDAR_TIMEOUT"
    assertions:
      - type: "status_equals"
        value: "FAILURE"
      - type: "appointment_not_in_db"
      - type: "error_code_equals"
        value: "CALENDAR_TIMEOUT"
    description_long: |
      Tests failure scenario: calendar service times out after 5 seconds.
      The appointment is initially created in DB (IN_PROGRESS),
      but when calendar sync fails, compensation (DB_ROLLBACK) is triggered.
      Verifies: appointment is deleted from DB, status is FAILURE, 
      no slot is reserved.

  - name: "SCENARIO_3_IDEMPOTENT_RETRY_NO_DOUBLE_BOOKING"
    description: "Duplicate request with same request_id returns cached response"
    steps:
      - action: "setup"
        config:
          error_mode: "success"
          delay_ms: 100
      - action: "create_appointment"
        input:
          user_id: "user_003"
          patient_name: "Carol White"
          appointment_date: "2025-12-17"
          appointment_time: "10:00"
          request_id: "req_idempotent_003"
        expected:
          status: "SUCCESS"
          http_code: 201
      - action: "create_appointment"
        input:
          user_id: "user_003"
          patient_name: "Carol White"
          appointment_date: "2025-12-17"
          appointment_time: "10:00"
          request_id: "req_idempotent_003"  # Same request_id
        expected:
          status: "SUCCESS"
          http_code: 201
          is_idempotency_hit: true
    assertions:
      - type: "total_appointments_equals"
        value: 1  # Only one appointment should exist
      - type: "slot_reservation_count_equals"
        value: 1  # Slot reserved only once
      - type: "no_double_booking"
    description_long: |
      Tests idempotency: same request_id submitted twice should not create
      two appointments or reserve slot twice. Second request returns cached response
      with is_idempotency_hit=true. Verifies: only 1 appointment exists,
      only 1 slot reservation.

  - name: "SCENARIO_4_PARTIAL_SUCCESS_COMPENSATION"
    description: "Appointment created locally but calendar sync fails with 500 -> compensation triggered"
    steps:
      - action: "setup"
        config:
          error_mode: "server_error"  # Calendar returns 503
          delay_ms: 100
      - action: "create_appointment"
        input:
          user_id: "user_004"
          patient_name: "David Brown"
          appointment_date: "2025-12-18"
          appointment_time: "11:00"
          request_id: "req_partial_004"
        expected:
          status: "FAILURE"
          http_code: 500
          error_code: "CALENDAR_INVALID_RESPONSE"
    assertions:
      - type: "status_equals"
        value: "FAILURE"
      - type: "compensation_action_executed"
        value: "DB_ROLLBACK"
      - type: "appointment_not_in_db"
      - type: "slot_not_reserved"
    description_long: |
      Tests compensation: appointment is created in DB and moved to IN_PROGRESS,
      but calendar sync returns 500. Compensation is triggered to rollback 
      the DB record and release any slot reservation. Verifies: appointment
      is deleted, slot is released, status is FAILURE.

  - name: "SCENARIO_5_AUDIT_AND_RECONCILIATION"
    description: "All events are logged with structured audit trail for reconciliation"
    steps:
      - action: "setup"
        config:
          error_mode: "success"
          delay_ms: 100
      - action: "create_appointment"
        input:
          user_id: "user_005"
          patient_name: "Emma Davis"
          appointment_date: "2025-12-19"
          appointment_time: "13:00"
          request_id: "req_audit_005"
        expected:
          status: "SUCCESS"
          http_code: 201
      - action: "verify_audit_log"
        expected_events:
          - "APPOINTMENT_INIT"
          - "DB_RESERVE_START"
          - "CALENDAR_SYNC_START"
          - "CALENDAR_SYNC_SUCCESS"
          - "FINAL_SUCCESS"
        required_fields:
          - "timestamp"
          - "event_type"
          - "appointment_id"
          - "request_id"
          - "status"
          - "error_code"
    assertions:
      - type: "audit_events_logged"
        count: 5
      - type: "all_events_contain_appointment_id"
      - type: "all_events_contain_request_id"
      - type: "sensitive_data_redacted"
    description_long: |
      Tests audit logging: each step of the appointment lifecycle is logged
      with structured JSON including appointment_id, request_id, status,
      error_code, and timestamps. User IDs are redacted. Verifies: all
      required events are logged, no sensitive data is exposed, 
      reconciliation is possible via audit trail.
"""
    
    data = yaml.safe_load(scenarios_yaml)
    return data["scenarios"]


if __name__ == "__main__":
    scenarios = load_test_scenarios()
    for i, scenario in enumerate(scenarios, 1):
        print(f"\n{i}. {scenario['name']}")
        print(f"   {scenario['description']}")
        print(f"   Long: {scenario.get('description_long', '').split(chr(10))[0]}")
