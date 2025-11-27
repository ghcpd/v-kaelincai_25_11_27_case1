# Reliable_Appointment_Booking_v2

This workspace demonstrates robustness improvements for an appointment booking API which previously returned intermittent 500s due to calendar sync issues. The implementation showcases idempotency, compensation, structured logs, and tests.

- Run the integration tests: `bash run_tests.sh` (or use WSL in Windows) 
 - Run the integration tests: `bash run_tests.sh` (or use WSL in Windows). PowerShell users can run `.
un_tests.sh` if using WSL or `.
un_tests.ps1` if translated.
- The mock calendar service runs at http://127.0.0.1:5001
- The API runs at http://127.0.0.1:5000
 - To test in async mode, set header `Prefer: respond-async` and check appointment state later via the API.
