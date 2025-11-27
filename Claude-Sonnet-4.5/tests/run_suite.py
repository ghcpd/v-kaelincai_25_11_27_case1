"""
Integration Test Suite for Appointment Booking System

Executes the 5 core test scenarios defined in appointment_cases.yaml
"""

import sys
import os
import json
import yaml
from typing import Dict, Any, List
from datetime import datetime

# Add project root to path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from src.appointment.saga import AppointmentSaga
from src.appointment.controller import AppointmentController
from src.appointment.database import InMemoryDatabase
from src.appointment.idempotency import IdempotencyManager
from src.appointment.audit_logger import AuditLogger
from src.adapters.calendar_adapter import CalendarAdapter
from mocks.mock_calendar_service import create_calendar_service


class TestRunner:
    """
    Test runner for appointment booking integration tests.
    """
    
    def __init__(self, test_cases_file: str):
        """
        Initialize test runner.
        
        Args:
            test_cases_file: Path to appointment_cases.yaml
        """
        self.test_cases_file = test_cases_file
        self.results: List[Dict[str, Any]] = []
        self.start_time = None
        self.end_time = None
    
    def load_test_cases(self) -> Dict[str, Any]:
        """Load test cases from YAML file"""
        with open(self.test_cases_file, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    def run_all_tests(self) -> bool:
        """
        Run all test cases.
        
        Returns:
            True if all tests pass, False otherwise
        """
        print("=" * 80)
        print("APPOINTMENT BOOKING INTEGRATION TEST SUITE")
        print("=" * 80)
        print()
        
        self.start_time = datetime.utcnow()
        
        test_config = self.load_test_cases()
        test_cases = test_config.get("test_cases", [])
        
        print(f"Loaded {len(test_cases)} test cases\n")
        
        all_passed = True
        
        for i, test_case in enumerate(test_cases, 1):
            print(f"{'=' * 80}")
            print(f"Test {i}/{len(test_cases)}: {test_case['id']} - {test_case['name']}")
            print(f"{'=' * 80}")
            print(f"Description: {test_case['description']}\n")
            
            result = self.run_test_case(test_case)
            self.results.append(result)
            
            if result["passed"]:
                print(f"[PASS] TEST PASSED")
            else:
                print(f"[FAIL] TEST FAILED")
                all_passed = False
            
            print()
        
        self.end_time = datetime.utcnow()
        
        # Print summary
        self.print_summary()
        
        return all_passed
    
    def run_test_case(self, test_case: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run a single test case.
        
        Args:
            test_case: Test case configuration
            
        Returns:
            Test result dict
        """
        test_id = test_case["id"]
        scenario = test_case.get("scenario")
        
        result = {
            "test_id": test_id,
            "name": test_case["name"],
            "passed": False,
            "assertions_passed": [],
            "assertions_failed": [],
            "duration_ms": 0,
            "error": None
        }
        
        try:
            if scenario == "idempotent_retry":
                test_result = self.run_idempotency_test(test_case)
            elif scenario == "audit_verification":
                test_result = self.run_audit_test(test_case)
            else:
                test_result = self.run_standard_test(test_case)
            
            result.update(test_result)
        
        except Exception as e:
            result["error"] = str(e)
            result["assertions_failed"].append(f"Unexpected error: {str(e)}")
        
        # Determine if test passed
        result["passed"] = len(result["assertions_failed"]) == 0
        
        return result
    
    def run_standard_test(self, test_case: Dict[str, Any]) -> Dict[str, Any]:
        """Run standard test case (TC001, TC002, TC004)"""
        start_time = datetime.utcnow()
        
        # Setup
        db = InMemoryDatabase()
        db.enable_logging = False
        
        idempotency = IdempotencyManager()
        idempotency.enable_logging = False
        
        audit_logger = AuditLogger(enable_console=False)
        
        calendar_behavior = test_case["calendar_behavior"]
        calendar_service = create_calendar_service(calendar_behavior)
        calendar_service.enable_logging = False
        
        calendar_adapter = CalendarAdapter(calendar_service)
        calendar_adapter.enable_logging = False
        
        saga = AppointmentSaga(db, calendar_adapter, idempotency, audit_logger)
        controller = AppointmentController(saga)
        
        # Execute
        input_data = test_case["input"]
        response, status_code = controller.create_appointment(
            request_data={
                "patient_id": input_data["patient_id"],
                "doctor_id": input_data["doctor_id"],
                "appointment_time": input_data["appointment_time"]
            },
            request_id=input_data["request_id"]
        )
        
        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        
        # Verify
        expected = test_case["expected_outcome"]
        assertions_passed = []
        assertions_failed = []
        
        # Check status
        if response.get("status") == expected["status"]:
            assertions_passed.append(f"Status is '{expected['status']}'")
        else:
            assertions_failed.append(
                f"Status mismatch: expected '{expected['status']}', got '{response.get('status')}'"
            )
        
        # Check HTTP status code
        if status_code == expected["http_status_code"]:
            assertions_passed.append(f"HTTP status code is {expected['http_status_code']}")
        else:
            assertions_failed.append(
                f"HTTP status code mismatch: expected {expected['http_status_code']}, got {status_code}"
            )
        
        # Check appointment ID
        has_appointment_id = "appointment_id" in response and response["appointment_id"] is not None
        if has_appointment_id == expected["has_appointment_id"]:
            assertions_passed.append(f"Appointment ID presence: {has_appointment_id}")
        else:
            assertions_failed.append(
                f"Appointment ID presence mismatch: expected {expected['has_appointment_id']}, got {has_appointment_id}"
            )
        
        # Check calendar event ID
        has_calendar_event_id = "calendar_event_id" in response and response["calendar_event_id"] is not None
        if has_calendar_event_id == expected["has_calendar_event_id"]:
            assertions_passed.append(f"Calendar event ID presence: {has_calendar_event_id}")
        else:
            assertions_failed.append(
                f"Calendar event ID presence mismatch: expected {expected['has_calendar_event_id']}, got {has_calendar_event_id}"
            )
        
        # Check DB state
        appointment_id = response.get("appointment_id")
        if appointment_id:
            appointment = db.get_appointment(appointment_id)
            
            if expected["db_record_exists"]:
                if appointment:
                    assertions_passed.append("DB record exists")
                    
                    if appointment.status == expected["db_status"]:
                        assertions_passed.append(f"DB status is '{expected['db_status']}'")
                    else:
                        assertions_failed.append(
                            f"DB status mismatch: expected '{expected['db_status']}', got '{appointment.status}'"
                        )
                else:
                    assertions_failed.append("DB record does not exist (expected to exist)")
            else:
                if not appointment:
                    assertions_passed.append("DB record does not exist (compensation successful)")
                else:
                    assertions_failed.append("DB record exists (expected to be deleted by compensation)")
        
        # Check state transitions
        if appointment_id:
            transitions = db.get_state_transitions(appointment_id=appointment_id)
            actual_states = [t.to_state for t in transitions]
            expected_states = expected.get("state_transitions", [])
            
            if actual_states == expected_states:
                assertions_passed.append(f"State transitions match: {' → '.join(expected_states)}")
            else:
                assertions_failed.append(
                    f"State transitions mismatch: expected {expected_states}, got {actual_states}"
                )
        
        return {
            "assertions_passed": assertions_passed,
            "assertions_failed": assertions_failed,
            "duration_ms": duration_ms,
            "response": response,
            "status_code": status_code
        }
    
    def run_idempotency_test(self, test_case: Dict[str, Any]) -> Dict[str, Any]:
        """Run idempotency test case (TC003)"""
        start_time = datetime.utcnow()
        
        # Setup
        db = InMemoryDatabase()
        db.enable_logging = False
        
        idempotency = IdempotencyManager()
        idempotency.enable_logging = False
        
        audit_logger = AuditLogger(enable_console=False)
        
        calendar_service = create_calendar_service("success")
        calendar_service.enable_logging = False
        
        calendar_adapter = CalendarAdapter(calendar_service)
        calendar_adapter.enable_logging = False
        
        saga = AppointmentSaga(db, calendar_adapter, idempotency, audit_logger)
        controller = AppointmentController(saga)
        
        # Execute first request
        input_data = test_case["input"]
        request_data = {
            "patient_id": input_data["patient_id"],
            "doctor_id": input_data["doctor_id"],
            "appointment_time": input_data["appointment_time"]
        }
        
        response1, status_code1 = controller.create_appointment(
            request_data=request_data,
            request_id=input_data["request_id"]
        )
        
        # Execute second request (duplicate)
        response2, status_code2 = controller.create_appointment(
            request_data=request_data,
            request_id=input_data["request_id"]  # Same request ID
        )
        
        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        
        # Verify
        expected = test_case["expected_outcome"]
        assertions_passed = []
        assertions_failed = []
        
        # First request checks
        if response1.get("status") == expected["first_request"]["status"]:
            assertions_passed.append("First request status is 'confirmed'")
        else:
            assertions_failed.append(f"First request status mismatch: {response1.get('status')}")
        
        if status_code1 == expected["first_request"]["http_status_code"]:
            assertions_passed.append(f"First request HTTP {status_code1}")
        else:
            assertions_failed.append(f"First request HTTP status mismatch: {status_code1}")
        
        # Second request checks
        if response2.get("status") == expected["second_request"]["status"]:
            assertions_passed.append("Second request status is 'confirmed'")
        else:
            assertions_failed.append(f"Second request status mismatch: {response2.get('status')}")
        
        if response2.get("idempotent") == expected["second_request"]["idempotent"]:
            assertions_passed.append("Second request marked as idempotent")
        else:
            assertions_failed.append("Second request not marked as idempotent")
        
        # Check no duplicate appointments
        all_appointments = db.list_appointments()
        if len(all_appointments) == 1:
            assertions_passed.append("Only ONE DB record created (no duplicate)")
        else:
            assertions_failed.append(f"Multiple DB records created: {len(all_appointments)}")
        
        # Check same appointment ID
        if response1.get("appointment_id") == response2.get("appointment_id"):
            assertions_passed.append("Appointment IDs are identical")
        else:
            assertions_failed.append("Appointment IDs differ (should be same)")
        
        # Check only one calendar event
        calendar_stats = calendar_service.get_stats()
        if calendar_stats["events_created"] == 1:
            assertions_passed.append("Only ONE calendar event created")
        else:
            assertions_failed.append(f"Multiple calendar events: {calendar_stats['events_created']}")
        
        return {
            "assertions_passed": assertions_passed,
            "assertions_failed": assertions_failed,
            "duration_ms": duration_ms,
            "response": response2,
            "status_code": status_code2
        }
    
    def run_audit_test(self, test_case: Dict[str, Any]) -> Dict[str, Any]:
        """Run audit verification test case (TC005)"""
        start_time = datetime.utcnow()
        
        # Setup with log file
        log_file = "logs/test_audit.log"
        
        # Clear log file
        if os.path.exists(log_file):
            os.remove(log_file)
        
        db = InMemoryDatabase()
        db.enable_logging = False
        
        idempotency = IdempotencyManager()
        idempotency.enable_logging = False
        
        audit_logger = AuditLogger(log_file=log_file, enable_console=False)
        
        # Execute multiple requests
        requests = test_case["input"]["requests"]
        
        for req in requests:
            calendar_service = create_calendar_service(req["calendar_behavior"])
            calendar_service.enable_logging = False
            
            calendar_adapter = CalendarAdapter(calendar_service)
            calendar_adapter.enable_logging = False
            
            saga = AppointmentSaga(db, calendar_adapter, idempotency, audit_logger)
            controller = AppointmentController(saga)
            
            request_data = {
                "patient_id": req["patient_id"],
                "doctor_id": req["doctor_id"],
                "appointment_time": req["appointment_time"]
            }
            
            # Add PII fields if present
            if "patient_name" in req:
                request_data["patient_name"] = req["patient_name"]
            if "patient_dob" in req:
                request_data["patient_dob"] = req["patient_dob"]
            if "patient_phone" in req:
                request_data["patient_phone"] = req["patient_phone"]
            
            controller.create_appointment(
                request_data=request_data,
                request_id=req["request_id"]
            )
        
        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        
        # Verify logs
        assertions_passed = []
        assertions_failed = []
        
        if not os.path.exists(log_file):
            assertions_failed.append("Log file does not exist")
            return {
                "assertions_passed": assertions_passed,
                "assertions_failed": assertions_failed,
                "duration_ms": duration_ms
            }
        
        # Read and parse logs
        with open(log_file, 'r') as f:
            log_lines = f.readlines()
        
        log_entries = []
        for line in log_lines:
            try:
                entry = json.loads(line.strip())
                log_entries.append(entry)
            except:
                pass
        
        if len(log_entries) > 0:
            assertions_passed.append(f"Found {len(log_entries)} log entries")
        else:
            assertions_failed.append("No valid log entries found")
            return {
                "assertions_passed": assertions_passed,
                "assertions_failed": assertions_failed,
                "duration_ms": duration_ms
            }
        
        # Check log format
        all_json_format = True
        for entry in log_entries:
            if not isinstance(entry, dict):
                all_json_format = False
                break
        
        if all_json_format:
            assertions_passed.append("All logs are in JSON format")
        else:
            assertions_failed.append("Some logs are not in JSON format")
        
        # Check required fields
        required_fields = ["timestamp", "level", "action", "request_id"]
        missing_fields = []
        
        for entry in log_entries:
            for field in required_fields:
                if field not in entry:
                    missing_fields.append(field)
                    break
        
        if not missing_fields:
            assertions_passed.append("All logs have required fields")
        else:
            assertions_failed.append(f"Some logs missing fields: {set(missing_fields)}")
        
        # Check PII redaction
        pii_redacted = True
        for entry in log_entries:
            metadata = entry.get("metadata", {})
            
            if "patient_name" in metadata:
                if metadata["patient_name"] != "***REDACTED***":
                    pii_redacted = False
                    break
            
            if "patient_dob" in metadata:
                if metadata["patient_dob"] != "****-**-**":
                    pii_redacted = False
                    break
        
        if pii_redacted:
            assertions_passed.append("PII fields are properly redacted")
        else:
            assertions_failed.append("PII fields are not properly redacted")
        
        # Check redacted_fields array
        has_redacted_fields_array = False
        for entry in log_entries:
            if "redacted_fields" in entry and len(entry["redacted_fields"]) > 0:
                has_redacted_fields_array = True
                break
        
        if has_redacted_fields_array:
            assertions_passed.append("'redacted_fields' array present")
        else:
            assertions_failed.append("'redacted_fields' array not found")
        
        return {
            "assertions_passed": assertions_passed,
            "assertions_failed": assertions_failed,
            "duration_ms": duration_ms,
            "log_entries_count": len(log_entries)
        }
    
    def print_summary(self):
        """Print test summary"""
        print("=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)
        
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results if r["passed"])
        failed_tests = total_tests - passed_tests
        
        print(f"\nTotal Tests: {total_tests}")
        print(f"✅ Passed: {passed_tests}")
        print(f"❌ Failed: {failed_tests}")
        
        if self.start_time and self.end_time:
            duration = (self.end_time - self.start_time).total_seconds()
            print(f"⏱️  Duration: {duration:.2f}s")
        
        print()
        
        # Details for failed tests
        if failed_tests > 0:
            print("FAILED TESTS:")
            print("-" * 80)
            for result in self.results:
                if not result["passed"]:
                    print(f"\n{result['test_id']}: {result['name']}")
                    print("Failed assertions:")
                    for assertion in result["assertions_failed"]:
                        print(f"  ❌ {assertion}")
        
        print()
        
        # Overall result
        if failed_tests == 0:
            print("🎉 ALL TESTS PASSED!")
        else:
            print(f"⚠️  {failed_tests} TEST(S) FAILED")
        
        print("=" * 80)


def main():
    """Main entry point"""
    test_cases_file = os.path.join(
        os.path.dirname(__file__),
        "integration",
        "appointment_cases.yaml"
    )
    
    runner = TestRunner(test_cases_file)
    success = runner.run_all_tests()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
