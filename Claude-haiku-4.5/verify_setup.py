#!/usr/bin/env python3
"""
Simple verification script to test integration without Flask
"""
import sys
sys.path.insert(0, '/root')

print("\n" + "="*80)
print("APPOINTMENT BOOKING SYSTEM v2 - VERIFICATION")
print("="*80 + "\n")

# Test 1: Import models
print("[1/5] Importing domain models...")
try:
    from src.models import Appointment, AppointmentStatus, ErrorCode, AppointmentStateMachine, IdempotencyStore
    print("  ✓ Models imported")
except Exception as e:
    print(f"  ✗ Error: {e}")
    sys.exit(1)

# Test 2: Import resilience
print("[2/5] Importing resilience patterns...")
try:
    from src.resilience import RetryPolicy, CircuitBreaker, RetryStrategy
    print("  ✓ Resilience patterns imported")
except Exception as e:
    print(f"  ✗ Error: {e}")
    sys.exit(1)

# Test 3: Import services
print("[3/5] Importing services...")
try:
    from src.database import AppointmentDatabase
    from src.audit_logger import AuditLogger
    from mocks.mock_calendar_service import MockCalendarService, MockCalendarErrorMode
    from src.calendar_adapter import CalendarAdapter
    from src.appointment_service import AppointmentService
    print("  ✓ Services imported")
except Exception as e:
    print(f"  ✗ Error: {e}")
    sys.exit(1)

# Test 4: Create appointment lifecycle
print("[4/5] Testing appointment lifecycle...")
try:
    # Setup
    db = AppointmentDatabase()
    calendar = MockCalendarService(default_delay_ms=50)
    adapter = CalendarAdapter(calendar, timeout_sec=5.0)
    logger = AuditLogger("logs/test_audit.log")
    service = AppointmentService(db, adapter, logger)
    
    # Create appointment
    request_id = "req_test_001"
    success, response = service.request_appointment(
        user_id="test_user_001",
        patient_name="Test Patient",
        appointment_date="2025-12-15",
        appointment_time="14:30",
        request_id=request_id
    )
    
    if success and response['status'] == 'SUCCESS':
        print("  ✓ Appointment lifecycle works")
        print(f"    - Appointment ID: {response['appointment_id']}")
        print(f"    - Status: {response['status']}")
        print(f"    - Calendar slot: {response['calendar_slot_id']}")
    else:
        print(f"  ✗ Appointment failed: {response}")
        sys.exit(1)
except Exception as e:
    print(f"  ✗ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 5: Test idempotency
print("[5/5] Testing idempotency...")
try:
    success2, response2 = service.request_appointment(
        user_id="test_user_001",
        patient_name="Test Patient",
        appointment_date="2025-12-15",
        appointment_time="14:30",
        request_id=request_id  # Same request_id
    )
    
    if isinstance(response2, dict) and response2.get('is_idempotency_hit') == True:
        print("  ✓ Idempotency enforced")
        print(f"    - Same appointment ID: {response2['appointment_id'] == response['appointment_id']}")
        print(f"    - Total appointments: {len(db.get_all())}")
    else:
        print("  ✗ Idempotency not working")
        print(f"    Response type: {type(response2)}, value: {response2}")
        sys.exit(1)
except Exception as e:
    print(f"  ✗ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "="*80)
print("✓ ALL VERIFICATION TESTS PASSED")
print("="*80 + "\n")

print("System ready for full integration test suite!")
print("Run: python3 tests/run_suite.py\n")
