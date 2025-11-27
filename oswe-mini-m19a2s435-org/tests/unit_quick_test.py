from src.services.appointment_service import AppointmentService
from src.adapters.calendar_adapter import CalendarAdapter
from src.db import init_db, SessionLocal

print('Starting quick service test')
init_db()
cal = CalendarAdapter(service_url='http://127.0.0.1:9876')
svc = AppointmentService(cal)
# Mock adapter: replace create_event with success
cal.create_event = lambda appointment_id, user_id, slot, mode=None, client_request_id=None: (True, {'event_id': f'evt-{appointment_id}'})
res = svc.confirm_appointment('cli-test-1', 'u1', 's1', async_confirm=False, mode=None)
print('Result:', res)
