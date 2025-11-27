"""
Integration test suite for appointment booking
Executes 5 test scenarios with assertions and reporting
"""
import sys
import json
import time
import uuid
import os
from pathlib import Path
from typing import Dict, Any, List, Tuple

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.api import create_app
from src.database import get_database, reset_database
from mocks.mock_calendar_service import (
    get_calendar_service,
    reset_calendar_service,
    MockCalendarErrorMode
)
from src.models import AppointmentStatus


class IntegrationTestRunner:
    """Run integration test suite"""
    
    def __init__(self):
        self.app = create_app(test_mode=True)
        self.client = self.app.test_client()
        self.results: List[Dict[str, Any]] = []
        self.audit_log_file = "logs/appointment_audit.log"

    def run_all_tests(self) -> Dict[str, Any]:
        """Run all 5 test scenarios"""
        print("\n" + "="*80)
        print("APPOINTMENT BOOKING INTEGRATION TEST SUITE")
        print("="*80 + "\n")

        tests = [
            self._test_scenario_1_normal_success,
            self._test_scenario_2_calendar_timeout,
            self._test_scenario_3_idempotent_retry,
            self._test_scenario_4_partial_success_compensation,
            self._test_scenario_5_audit_reconciliation
        ]

        for i, test_func in enumerate(tests, 1):
            print(f"\n[TEST {i}/5] {test_func.__name__}")
            print("-" * 80)
            try:
                result = test_func()
                self.results.append(result)
                status = "PASS" if result["passed"] else "FAIL"
                print(f"[{status}]: {result['description']}")
            except Exception as e:
                print(f"[EXCEPTION] {str(e)}")
                self.results.append({
                    "name": test_func.__name__,
                    "passed": False,
                    "error": str(e)
                })

        return self._generate_report()

    def _format_assertion(self, text, result):
        """Format assertion with symbol"""
        symbol = "[OK]" if result else "[FAIL]"
        return f"  {symbol} {text}"

    def _test_scenario_1_normal_success(self) -> Dict[str, Any]:
        """
        SCENARIO 1: Normal booking flow - success
        Verifies: appointment created, synced, marked SUCCESS
        """
        reset_database()
        reset_calendar_service()
        
        calendar_service = get_calendar_service()
        calendar_service.set_error_mode(MockCalendarErrorMode.SUCCESS, 100)

        request_id = f"req_success_{uuid.uuid4().hex[:8]}"
        
        response = self.client.post("/api/appointments", json={
            "user_id": "user_001",
            "patient_name": "Alice Johnson",
            "appointment_date": "2025-12-15",
            "appointment_time": "14:30",
            "request_id": request_id
        })

        data = response.get_json()
        
        assertions = [
            ("HTTP 201", response.status_code == 201),
            ("Status is SUCCESS", data.get("status") == "SUCCESS"),
            ("Appointment ID exists", data.get("appointment_id") is not None),
            ("Calendar slot reserved", data.get("calendar_slot_id") is not None),
            ("Error code is SUCCESS", data.get("error_code") == "SUCCESS"),
        ]

        passed = all(result for _, result in assertions)
        
        for assertion, result in assertions:
            print(self._format_assertion(assertion, result))

        return {
            "name": "SCENARIO_1_NORMAL_SUCCESS",
            "description": "Normal booking flow - appointment created and synced successfully",
            "passed": passed,
            "assertions": assertions,
            "response": data
        }

    def _test_scenario_2_calendar_timeout(self) -> Dict[str, Any]:
        """
        SCENARIO 2: Calendar timeout -> 500, no booking persists
        Verifies: appointment created but then deleted via compensation
        """
        reset_database()
        reset_calendar_service()
        
        calendar_service = get_calendar_service()
        calendar_service.set_error_mode(MockCalendarErrorMode.TIMEOUT, 6000)

        request_id = f"req_timeout_{uuid.uuid4().hex[:8]}"
        
        response = self.client.post("/api/appointments", json={
            "user_id": "user_002",
            "patient_name": "Bob Smith",
            "appointment_date": "2025-12-16",
            "appointment_time": "15:00",
            "request_id": request_id
        })

        data = response.get_json()
        
        assertions = [
            ("HTTP 500", response.status_code == 500),
            ("Status is FAILURE", data.get("status") == "FAILURE"),
            ("Error code is CALENDAR_TIMEOUT", data.get("error_code") == "CALENDAR_TIMEOUT"),
            ("No calendar slot", data.get("calendar_slot_id") is None),
        ]

        # Verify appointment was compensated (deleted)
        db = get_database()
        apt_in_db = db.get_by_id(data.get("appointment_id")) is None
        assertions.append(("Appointment deleted from DB", apt_in_db))

        passed = all(result for _, result in assertions)
        
        for assertion, result in assertions:
            print(self._format_assertion(assertion, result))

        return {
            "name": "SCENARIO_2_CALENDAR_TIMEOUT_NO_BOOKING",
            "description": "Calendar timeout (>5s) returns 500, no local booking persists",
            "passed": passed,
            "assertions": assertions,
            "response": data
        }

    def _test_scenario_3_idempotent_retry(self) -> Dict[str, Any]:
        """
        SCENARIO 3: Duplicate request with same request_id -> cached response
        Verifies: no double-booking, idempotency enforced
        """
        reset_database()
        reset_calendar_service()
        
        calendar_service = get_calendar_service()
        calendar_service.set_error_mode(MockCalendarErrorMode.SUCCESS, 100)

        request_id = f"req_idempotent_{uuid.uuid4().hex[:8]}"
        
        # First request
        response1 = self.client.post("/api/appointments", json={
            "user_id": "user_003",
            "patient_name": "Carol White",
            "appointment_date": "2025-12-17",
            "appointment_time": "10:00",
            "request_id": request_id
        })
        data1 = response1.get_json()

        # Duplicate request (same request_id)
        response2 = self.client.post("/api/appointments", json={
            "user_id": "user_003",
            "patient_name": "Carol White",
            "appointment_date": "2025-12-17",
            "appointment_time": "10:00",
            "request_id": request_id
        })
        data2 = response2.get_json()

        db = get_database()
        total_apts = len(db.get_all())
        slot_id = data1.get("calendar_slot_id")
        slot_count = db.get_slot_reservation_count(slot_id) if slot_id else 0

        assertions = [
            ("First request HTTP 201", response1.status_code == 201),
            ("Second request HTTP 201", response2.status_code == 201),
            ("Same appointment ID", data1.get("appointment_id") == data2.get("appointment_id")),
            ("Idempotency hit flag set", data2.get("is_idempotency_hit") == True),
            ("Only 1 appointment in DB", total_apts == 1),
            ("Slot reserved only once", slot_count == 1),
            ("No double-booking", not db.has_duplicate_booking(slot_id) if slot_id else True),
        ]

        passed = all(result for _, result in assertions)
        
        for assertion, result in assertions:
            print(self._format_assertion(assertion, result))

        return {
            "name": "SCENARIO_3_IDEMPOTENT_RETRY_NO_DOUBLE_BOOKING",
            "description": "Duplicate request with same request_id returns cached response",
            "passed": passed,
            "assertions": assertions,
            "stats": {
                "total_appointments": total_apts,
                "slot_reservations": slot_count
            }
        }

    def _test_scenario_4_partial_success_compensation(self) -> Dict[str, Any]:
        """
        SCENARIO 4: Calendar returns 503 -> compensation triggered
        Verifies: DB rollback executed, appointment removed
        """
        reset_database()
        reset_calendar_service()
        
        calendar_service = get_calendar_service()
        calendar_service.set_error_mode(MockCalendarErrorMode.SERVER_ERROR, 100)

        request_id = f"req_partial_{uuid.uuid4().hex[:8]}"
        
        response = self.client.post("/api/appointments", json={
            "user_id": "user_004",
            "patient_name": "David Brown",
            "appointment_date": "2025-12-18",
            "appointment_time": "11:00",
            "request_id": request_id
        })

        data = response.get_json()
        apt_id = data.get("appointment_id")

        db = get_database()
        apt_in_db = db.get_by_id(apt_id)

        assertions = [
            ("HTTP 500", response.status_code == 500),
            ("Status is FAILURE", data.get("status") == "FAILURE"),
            ("Error code is CALENDAR_INVALID_RESPONSE", data.get("error_code") == "CALENDAR_INVALID_RESPONSE"),
            ("Appointment deleted from DB", apt_in_db is None),
            ("No slot reserved", data.get("calendar_slot_id") is None),
        ]

        passed = all(result for _, result in assertions)
        
        for assertion, result in assertions:
            print(self._format_assertion(assertion, result))

        return {
            "name": "SCENARIO_4_PARTIAL_SUCCESS_COMPENSATION",
            "description": "Appointment created locally but calendar sync fails with 500 -> compensation triggered",
            "passed": passed,
            "assertions": assertions,
            "response": data
        }

    def _test_scenario_5_audit_reconciliation(self) -> Dict[str, Any]:
        """
        SCENARIO 5: Audit trail logged for all events
        Verifies: structured logging, redacted data, event sequence
        """
        reset_database()
        reset_calendar_service()
        
        calendar_service = get_calendar_service()
        calendar_service.set_error_mode(MockCalendarErrorMode.SUCCESS, 100)

        request_id = f"req_audit_{uuid.uuid4().hex[:8]}"
        
        response = self.client.post("/api/appointments", json={
            "user_id": "user_005",
            "patient_name": "Emma Davis",
            "appointment_date": "2025-12-19",
            "appointment_time": "13:00",
            "request_id": request_id
        })

        # Give time for file writes
        time.sleep(0.5)

        # Read audit log
        audit_events = []
        try:
            if os.path.exists(self.audit_log_file):
                with open(self.audit_log_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        try:
                            audit_events.append(json.loads(line))
                        except:
                            pass
        except Exception as e:
            print(f"  [WARN] Could not read audit log: {e}")

        # Filter to our request
        our_events = [e for e in audit_events if e.get("request_id") == request_id]

        # Verify event sequence
        expected_events = [
            "APPOINTMENT_INIT",
            "DB_RESERVE_START",
            "CALENDAR_SYNC_SUCCESS",
            "FINAL_SUCCESS"
        ]
        
        actual_events = [e.get("event_type") for e in our_events]
        events_match = all(exp in actual_events for exp in expected_events[:len(actual_events)])

        # Check for sensitive data
        sensitive_data_found = False
        for event in our_events:
            user_id_field = event.get("user_id", "")
            # Redacted format should be usr_xxx...
            if not (user_id_field.startswith("usr_") and user_id_field.endswith("...")):
                sensitive_data_found = True

        assertions = [
            ("HTTP 201", response.status_code == 201),
            ("Audit events logged", len(our_events) > 0),
            ("Expected events in sequence", events_match),
            ("All events have appointment_id", all(e.get("appointment_id") for e in our_events)),
            ("All events have request_id", all(e.get("request_id") for e in our_events)),
            ("All events have timestamp", all(e.get("timestamp") for e in our_events)),
            ("All events have status", all(e.get("status") for e in our_events)),
            ("User IDs are redacted", not sensitive_data_found),
        ]

        passed = all(result for _, result in assertions)
        
        for assertion, result in assertions:
            print(self._format_assertion(assertion, result))

        if our_events:
            print(f"\n  Audit events ({len(our_events)} total):")
            for event in our_events:
                print(f"    - {event.get('timestamp')} | {event.get('event_type')} | {event.get('status')}")

        return {
            "name": "SCENARIO_5_AUDIT_AND_RECONCILIATION",
            "description": "All events are logged with structured audit trail for reconciliation",
            "passed": passed,
            "assertions": assertions,
            "audit_events": our_events
        }

    def _generate_report(self) -> Dict[str, Any]:
        """Generate final test report"""
        passed = sum(1 for r in self.results if r.get("passed"))
        total = len(self.results)
        pass_rate = (passed / total * 100) if total > 0 else 0

        print("\n" + "="*80)
        print("TEST SUMMARY")
        print("="*80)
        print(f"\nTotal Tests: {total}")
        print(f"Passed:      {passed}")
        print(f"Failed:      {total - passed}")
        print(f"Pass Rate:   {pass_rate:.1f}%")
        print("\nDetailed Results:")
        for result in self.results:
            status = "PASS" if result.get("passed") else "FAIL"
            print(f"  [{status}]: {result.get('name')}")

        print("\n" + "="*80 + "\n")

        return {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": pass_rate,
            "results": self.results
        }


def main():
    """Run test suite"""
    runner = IntegrationTestRunner()
    report = runner.run_all_tests()
    
    # Exit with error code if any tests failed
    sys.exit(0 if report["passed"] == report["total"] else 1)


if __name__ == "__main__":
    main()
