"""
In-memory appointment database for testing
Simulates persistence layer with transaction support
"""
from typing import Dict, List, Optional, Any
from datetime import datetime
from src.models import Appointment, AppointmentStatus


class AppointmentDatabase:
    """In-memory appointment database with transaction support"""
    
    def __init__(self):
        self.appointments: Dict[str, Appointment] = {}
        self.request_id_index: Dict[str, str] = {}  # request_id -> appointment_id
        self.slot_reservations: Dict[str, List[str]] = {}  # slot_id -> [appointment_ids]

    def create(self, appointment: Appointment) -> bool:
        """Create new appointment"""
        if appointment.request_id in self.request_id_index:
            return False  # Duplicate request
        
        self.appointments[appointment.appointment_id] = appointment
        self.request_id_index[appointment.request_id] = appointment.appointment_id
        return True

    def get_by_id(self, appointment_id: str) -> Optional[Appointment]:
        """Retrieve appointment by ID"""
        return self.appointments.get(appointment_id)

    def get_by_request_id(self, request_id: str) -> Optional[Appointment]:
        """Retrieve appointment by request ID (idempotency)"""
        appointment_id = self.request_id_index.get(request_id)
        if appointment_id:
            return self.appointments.get(appointment_id)
        return None

    def update(self, appointment: Appointment) -> bool:
        """Update existing appointment"""
        if appointment.appointment_id not in self.appointments:
            return False
        
        self.appointments[appointment.appointment_id] = appointment
        return True

    def reserve_slot(self, appointment_id: str, calendar_slot_id: str) -> bool:
        """Reserve calendar slot for appointment"""
        appointment = self.appointments.get(appointment_id)
        if not appointment:
            return False

        if calendar_slot_id not in self.slot_reservations:
            self.slot_reservations[calendar_slot_id] = []

        # Check if slot is already reserved
        if appointment_id not in self.slot_reservations[calendar_slot_id]:
            self.slot_reservations[calendar_slot_id].append(appointment_id)
            appointment.calendar_slot_id = calendar_slot_id
            return True

        return False

    def release_slot(self, calendar_slot_id: str, appointment_id: str) -> bool:
        """Release slot reservation (compensation)"""
        if calendar_slot_id in self.slot_reservations:
            if appointment_id in self.slot_reservations[calendar_slot_id]:
                self.slot_reservations[calendar_slot_id].remove(appointment_id)
                return True
        return False

    def get_slot_reservation_count(self, calendar_slot_id: str) -> int:
        """Get number of appointments for a slot"""
        return len(self.slot_reservations.get(calendar_slot_id, []))

    def has_duplicate_booking(self, calendar_slot_id: str) -> bool:
        """Check if slot is over-booked (double-booking)"""
        return self.get_slot_reservation_count(calendar_slot_id) > 1

    def delete(self, appointment_id: str) -> bool:
        """Delete appointment (for rollback)"""
        if appointment_id in self.appointments:
            appointment = self.appointments[appointment_id]
            del self.appointments[appointment_id]
            
            # Clean up request_id index
            if appointment.request_id in self.request_id_index:
                del self.request_id_index[appointment.request_id]
            
            # Clean up slot reservations
            if appointment.calendar_slot_id:
                self.release_slot(appointment.calendar_slot_id, appointment_id)
            
            return True
        return False

    def get_all(self) -> List[Appointment]:
        """Get all appointments"""
        return list(self.appointments.values())

    def count_by_status(self, status: AppointmentStatus) -> int:
        """Count appointments by status"""
        return sum(1 for apt in self.appointments.values() if apt.status == status)

    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics"""
        return {
            "total_appointments": len(self.appointments),
            "total_requests": len(self.request_id_index),
            "total_slots": len(self.slot_reservations),
            "by_status": {
                status.value: self.count_by_status(status)
                for status in AppointmentStatus
            }
        }

    def clear(self) -> None:
        """Clear all data (for testing)"""
        self.appointments.clear()
        self.request_id_index.clear()
        self.slot_reservations.clear()


# Global singleton instance
_database: Optional[AppointmentDatabase] = None


def get_database() -> AppointmentDatabase:
    """Get or create database singleton"""
    global _database
    if _database is None:
        _database = AppointmentDatabase()
    return _database


def reset_database() -> None:
    """Reset database for testing"""
    global _database
    if _database is not None:
        _database.clear()
