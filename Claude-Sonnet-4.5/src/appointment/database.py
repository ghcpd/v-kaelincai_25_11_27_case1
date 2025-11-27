"""
Database Models and In-Memory Storage

For demo purposes, uses in-memory storage. In production, use PostgreSQL/MySQL.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, asdict
import json


@dataclass
class Appointment:
    """Appointment database model"""
    appointment_id: str
    request_id: str
    patient_id: str
    doctor_id: str
    appointment_time: str
    status: str  # AppointmentState value
    calendar_event_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        data = asdict(self)
        if self.metadata is None:
            data['metadata'] = {}
        return data
    
    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict())


@dataclass
class StateTransitionRecord:
    """State transition audit record"""
    id: int
    appointment_id: str
    request_id: str
    from_state: Optional[str]
    to_state: str
    timestamp: str
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)


class InMemoryDatabase:
    """
    In-memory database for demo purposes.
    
    In production, replace with SQLAlchemy models and PostgreSQL/MySQL.
    """
    
    def __init__(self):
        self.appointments: Dict[str, Appointment] = {}
        self.state_transitions: List[StateTransitionRecord] = []
        self.next_transition_id = 1
        self.enable_logging = True
    
    # Appointment CRUD operations
    
    def create_appointment(
        self,
        appointment_id: str,
        request_id: str,
        patient_id: str,
        doctor_id: str,
        appointment_time: str,
        status: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Appointment:
        """
        Create new appointment record.
        
        Args:
            appointment_id: Unique appointment ID
            request_id: Request ID for idempotency
            patient_id: Patient identifier
            doctor_id: Doctor identifier
            appointment_time: ISO 8601 timestamp
            status: Initial status (AppointmentState value)
            metadata: Optional metadata
            
        Returns:
            Created Appointment object
        """
        now = datetime.utcnow().isoformat() + "Z"
        
        appointment = Appointment(
            appointment_id=appointment_id,
            request_id=request_id,
            patient_id=patient_id,
            doctor_id=doctor_id,
            appointment_time=appointment_time,
            status=status,
            created_at=now,
            updated_at=now,
            metadata=metadata or {}
        )
        
        self.appointments[appointment_id] = appointment
        
        if self.enable_logging:
            print(f"[DB] 📝 Created appointment {appointment_id}")
        
        return appointment
    
    def get_appointment(self, appointment_id: str) -> Optional[Appointment]:
        """Get appointment by ID"""
        return self.appointments.get(appointment_id)
    
    def update_appointment_status(
        self,
        appointment_id: str,
        status: str,
        calendar_event_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[Appointment]:
        """
        Update appointment status.
        
        Args:
            appointment_id: Appointment ID
            status: New status (AppointmentState value)
            calendar_event_id: Optional calendar event ID
            metadata: Optional metadata to merge
            
        Returns:
            Updated Appointment or None if not found
        """
        appointment = self.appointments.get(appointment_id)
        if not appointment:
            return None
        
        appointment.status = status
        appointment.updated_at = datetime.utcnow().isoformat() + "Z"
        
        if calendar_event_id:
            appointment.calendar_event_id = calendar_event_id
        
        if metadata:
            appointment.metadata = appointment.metadata or {}
            appointment.metadata.update(metadata)
        
        if self.enable_logging:
            print(f"[DB] 📝 Updated appointment {appointment_id} status={status}")
        
        return appointment
    
    def delete_appointment(self, appointment_id: str) -> bool:
        """
        Delete appointment (for compensation).
        
        Args:
            appointment_id: Appointment ID
            
        Returns:
            True if deleted, False if not found
        """
        if appointment_id in self.appointments:
            del self.appointments[appointment_id]
            if self.enable_logging:
                print(f"[DB] 🗑️  Deleted appointment {appointment_id}")
            return True
        return False
    
    def list_appointments(
        self,
        patient_id: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[Appointment]:
        """
        List appointments with optional filters.
        
        Args:
            patient_id: Filter by patient ID
            status: Filter by status
            
        Returns:
            List of matching appointments
        """
        results = list(self.appointments.values())
        
        if patient_id:
            results = [a for a in results if a.patient_id == patient_id]
        
        if status:
            results = [a for a in results if a.status == status]
        
        return results
    
    # State transition audit operations
    
    def record_state_transition(
        self,
        appointment_id: str,
        request_id: str,
        from_state: Optional[str],
        to_state: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> StateTransitionRecord:
        """
        Record state transition for audit.
        
        Args:
            appointment_id: Appointment ID
            request_id: Request ID
            from_state: Previous state
            to_state: New state
            metadata: Optional transition metadata
            
        Returns:
            Created StateTransitionRecord
        """
        record = StateTransitionRecord(
            id=self.next_transition_id,
            appointment_id=appointment_id,
            request_id=request_id,
            from_state=from_state,
            to_state=to_state,
            timestamp=datetime.utcnow().isoformat() + "Z",
            metadata=metadata or {}
        )
        
        self.next_transition_id += 1
        self.state_transitions.append(record)
        
        if self.enable_logging:
            print(f"[DB] 📊 Recorded transition {from_state} → {to_state} for {appointment_id}")
        
        return record
    
    def get_state_transitions(
        self,
        appointment_id: Optional[str] = None,
        request_id: Optional[str] = None
    ) -> List[StateTransitionRecord]:
        """
        Get state transition history.
        
        Args:
            appointment_id: Filter by appointment ID
            request_id: Filter by request ID
            
        Returns:
            List of matching state transitions
        """
        results = self.state_transitions.copy()
        
        if appointment_id:
            results = [t for t in results if t.appointment_id == appointment_id]
        
        if request_id:
            results = [t for t in results if t.request_id == request_id]
        
        return results
    
    # Utility methods
    
    def clear_all(self):
        """Clear all data (for testing)"""
        self.appointments.clear()
        self.state_transitions.clear()
        self.next_transition_id = 1
        if self.enable_logging:
            print("[DB] 🧹 Cleared all data")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics"""
        status_counts = {}
        for appointment in self.appointments.values():
            status_counts[appointment.status] = status_counts.get(appointment.status, 0) + 1
        
        return {
            "total_appointments": len(self.appointments),
            "total_transitions": len(self.state_transitions),
            "status_counts": status_counts
        }
    
    def export_data(self) -> Dict[str, Any]:
        """Export all data (for debugging/testing)"""
        return {
            "appointments": [a.to_dict() for a in self.appointments.values()],
            "state_transitions": [t.to_dict() for t in self.state_transitions]
        }
