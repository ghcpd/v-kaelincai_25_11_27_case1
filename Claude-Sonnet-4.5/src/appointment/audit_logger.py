"""
Structured Audit Logger

Emits JSON-formatted logs with request ID correlation and PII redaction.
"""

import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import re


class AuditLogger:
    """
    Structured logger for appointment booking audit trail.
    
    Features:
        - JSON-formatted logs
        - Request ID correlation
        - PII redaction (patient names, DOB, contact info)
        - State transition tracking
        - Performance metrics
    """
    
    def __init__(self, log_file: Optional[str] = None, enable_console: bool = True):
        """
        Initialize audit logger.
        
        Args:
            log_file: Optional file path for log output
            enable_console: Whether to also log to console
        """
        self.log_file = log_file
        self.enable_console = enable_console
        
        # Configure Python logger
        self.logger = logging.getLogger("AppointmentAudit")
        self.logger.setLevel(logging.INFO)
        
        # Remove existing handlers
        self.logger.handlers.clear()
        
        # Add file handler if specified
        if log_file:
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(logging.Formatter('%(message)s'))
            self.logger.addHandler(file_handler)
        
        # Add console handler if enabled
        if enable_console:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(logging.Formatter('%(message)s'))
            self.logger.addHandler(console_handler)
        
        self.pii_fields = ["patient_name", "patient_dob", "patient_phone", "patient_email"]
    
    def log(
        self,
        level: str,
        action: str,
        request_id: str,
        appointment_id: Optional[str] = None,
        state_from: Optional[str] = None,
        state_to: Optional[str] = None,
        duration_ms: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ):
        """
        Log structured audit event.
        
        Args:
            level: Log level (INFO, WARNING, ERROR)
            action: Action being performed
            request_id: Unique request ID
            appointment_id: Optional appointment ID
            state_from: Previous state
            state_to: New state
            duration_ms: Operation duration in milliseconds
            metadata: Additional metadata
            error: Error message if applicable
        """
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": level,
            "action": action,
            "request_id": request_id,
        }
        
        if appointment_id:
            log_entry["appointment_id"] = appointment_id
        
        if state_from:
            log_entry["state_from"] = state_from
        
        if state_to:
            log_entry["state_to"] = state_to
        
        if duration_ms is not None:
            log_entry["duration_ms"] = duration_ms
        
        if error:
            log_entry["error"] = error
        
        if metadata:
            # Redact PII from metadata
            redacted_metadata = self._redact_pii(metadata)
            log_entry["metadata"] = redacted_metadata
            
            # Track which fields were redacted
            redacted_fields = self._get_redacted_fields(metadata)
            if redacted_fields:
                log_entry["redacted_fields"] = redacted_fields
        
        # Emit log
        log_json = json.dumps(log_entry)
        
        if level == "ERROR":
            self.logger.error(log_json)
        elif level == "WARNING":
            self.logger.warning(log_json)
        else:
            self.logger.info(log_json)
    
    def log_request_received(
        self,
        request_id: str,
        appointment_data: Dict[str, Any]
    ):
        """Log incoming appointment request"""
        self.log(
            level="INFO",
            action="request_received",
            request_id=request_id,
            metadata=appointment_data
        )
    
    def log_state_transition(
        self,
        request_id: str,
        appointment_id: str,
        from_state: Optional[str],
        to_state: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Log state transition"""
        self.log(
            level="INFO",
            action="state_transition",
            request_id=request_id,
            appointment_id=appointment_id,
            state_from=from_state,
            state_to=to_state,
            metadata=metadata
        )
    
    def log_calendar_sync_start(
        self,
        request_id: str,
        appointment_id: str
    ):
        """Log start of calendar sync"""
        self.log(
            level="INFO",
            action="calendar_sync_start",
            request_id=request_id,
            appointment_id=appointment_id
        )
    
    def log_calendar_sync_success(
        self,
        request_id: str,
        appointment_id: str,
        calendar_event_id: str,
        duration_ms: int
    ):
        """Log successful calendar sync"""
        self.log(
            level="INFO",
            action="calendar_sync_success",
            request_id=request_id,
            appointment_id=appointment_id,
            duration_ms=duration_ms,
            metadata={"calendar_event_id": calendar_event_id}
        )
    
    def log_calendar_sync_failure(
        self,
        request_id: str,
        appointment_id: str,
        error: str,
        duration_ms: int
    ):
        """Log failed calendar sync"""
        self.log(
            level="ERROR",
            action="calendar_sync_failure",
            request_id=request_id,
            appointment_id=appointment_id,
            error=error,
            duration_ms=duration_ms
        )
    
    def log_compensation_start(
        self,
        request_id: str,
        appointment_id: str,
        reason: str
    ):
        """Log start of compensation (rollback)"""
        self.log(
            level="WARNING",
            action="compensation_start",
            request_id=request_id,
            appointment_id=appointment_id,
            metadata={"reason": reason}
        )
    
    def log_compensation_complete(
        self,
        request_id: str,
        appointment_id: str,
        actions_taken: List[str]
    ):
        """Log completed compensation"""
        self.log(
            level="INFO",
            action="compensation_complete",
            request_id=request_id,
            appointment_id=appointment_id,
            metadata={"actions": actions_taken}
        )
    
    def log_idempotency_hit(
        self,
        request_id: str,
        appointment_id: str
    ):
        """Log idempotency cache hit (duplicate request)"""
        self.log(
            level="INFO",
            action="idempotency_hit",
            request_id=request_id,
            appointment_id=appointment_id
        )
    
    def log_circuit_breaker_open(
        self,
        request_id: str,
        service_name: str
    ):
        """Log circuit breaker opened"""
        self.log(
            level="ERROR",
            action="circuit_breaker_open",
            request_id=request_id,
            metadata={"service": service_name}
        )
    
    def log_retry_attempt(
        self,
        request_id: str,
        appointment_id: str,
        attempt: int,
        max_attempts: int
    ):
        """Log retry attempt"""
        self.log(
            level="WARNING",
            action="retry_attempt",
            request_id=request_id,
            appointment_id=appointment_id,
            metadata={"attempt": attempt, "max_attempts": max_attempts}
        )
    
    def _redact_pii(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Redact PII from data dictionary.
        
        Args:
            data: Dictionary that may contain PII
            
        Returns:
            Dictionary with PII redacted
        """
        if not isinstance(data, dict):
            return data
        
        redacted = {}
        for key, value in data.items():
            # Check specific PII field formats first
            if key == "patient_dob" or "dob" in key.lower():
                redacted[key] = "****-**-**"
            elif key == "patient_phone" or "phone" in key.lower():
                # Keep last 4 digits
                if isinstance(value, str) and len(value) >= 4:
                    redacted[key] = "****-****-" + value[-4:]
                else:
                    redacted[key] = "***REDACTED***"
            elif key in self.pii_fields or self._is_pii_field(key):
                redacted[key] = "***REDACTED***"
            elif isinstance(value, dict):
                redacted[key] = self._redact_pii(value)
            else:
                redacted[key] = value
        
        return redacted
    
    def _is_pii_field(self, field_name: str) -> bool:
        """Check if field name indicates PII"""
        pii_keywords = ["name", "email", "ssn", "address", "phone"]
        field_lower = field_name.lower()
        return any(keyword in field_lower for keyword in pii_keywords)
    
    def _get_redacted_fields(self, data: Dict[str, Any]) -> List[str]:
        """Get list of fields that were redacted"""
        redacted = []
        for key in data.keys():
            if key in self.pii_fields or self._is_pii_field(key):
                redacted.append(key)
        return redacted


# Global logger instance (can be configured at app startup)
_global_logger: Optional[AuditLogger] = None


def get_logger() -> AuditLogger:
    """Get global audit logger instance"""
    global _global_logger
    if _global_logger is None:
        _global_logger = AuditLogger()
    return _global_logger


def configure_logger(log_file: Optional[str] = None, enable_console: bool = True):
    """Configure global audit logger"""
    global _global_logger
    _global_logger = AuditLogger(log_file=log_file, enable_console=enable_console)
