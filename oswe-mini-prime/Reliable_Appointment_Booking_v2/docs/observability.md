# Observability & Structured Logging

All events are emitted as structured JSON lines to `logs/appointments.jsonl`. Each event has a minimal set of fields:
- timestamp: ISO8601 UTC
- level: INFO/ERROR
- event: the event name
- appointment_id, request_id, idempotency_key
- state: current appointment state (where appropriate)
- message: human friendly message

We also include extra fields for retries, attempts, and errors. PII is not logged; client_id should be redacted; if present it will not be stored in logs unless explicitly needed.

Use the provided `logs/audit_schema.json` for integration with an external audit system.
