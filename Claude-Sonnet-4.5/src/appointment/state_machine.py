"""
Appointment State Machine

Defines states and transitions for the appointment booking lifecycle.
"""

from enum import Enum
from typing import Optional, List, Dict, Any
from datetime import datetime
import json


class AppointmentState(Enum):
    """Appointment lifecycle states"""
    INITIATED = "initiated"
    IN_PROGRESS = "in_progress"
    CALENDAR_SYNCING = "calendar_syncing"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    COMPENSATING = "compensating"
    PENDING_RETRY = "pending_retry"
    CANCELLED = "cancelled"


class StateTransition:
    """Represents a state transition event"""
    
    def __init__(
        self,
        appointment_id: str,
        request_id: str,
        from_state: Optional[AppointmentState],
        to_state: AppointmentState,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.appointment_id = appointment_id
        self.request_id = request_id
        self.from_state = from_state
        self.to_state = to_state
        self.timestamp = datetime.utcnow()
        self.metadata = metadata or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/storage"""
        return {
            "appointment_id": self.appointment_id,
            "request_id": self.request_id,
            "from_state": self.from_state.value if self.from_state else None,
            "to_state": self.to_state.value,
            "timestamp": self.timestamp.isoformat() + "Z",
            "metadata": self.metadata
        }
    
    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict())


class AppointmentStateMachine:
    """
    State machine for appointment lifecycle management.
    
    Validates state transitions and maintains transition history.
    """
    
    # Define valid state transitions
    VALID_TRANSITIONS = {
        None: [AppointmentState.INITIATED],  # Initial state
        AppointmentState.INITIATED: [
            AppointmentState.IN_PROGRESS,
            AppointmentState.FAILED
        ],
        AppointmentState.IN_PROGRESS: [
            AppointmentState.CALENDAR_SYNCING,
            AppointmentState.COMPENSATING,
            AppointmentState.FAILED
        ],
        AppointmentState.CALENDAR_SYNCING: [
            AppointmentState.CONFIRMED,
            AppointmentState.PENDING_RETRY,
            AppointmentState.COMPENSATING,
            AppointmentState.FAILED
        ],
        AppointmentState.PENDING_RETRY: [
            AppointmentState.CALENDAR_SYNCING,
            AppointmentState.COMPENSATING,
            AppointmentState.FAILED
        ],
        AppointmentState.COMPENSATING: [
            AppointmentState.FAILED,
            AppointmentState.CANCELLED
        ],
        AppointmentState.CONFIRMED: [
            AppointmentState.CANCELLED  # Allow cancellation of confirmed appointments
        ],
        AppointmentState.FAILED: [],  # Terminal state
        AppointmentState.CANCELLED: []  # Terminal state
    }
    
    def __init__(self):
        self.current_state: Optional[AppointmentState] = None
        self.transition_history: List[StateTransition] = []
    
    def can_transition(
        self,
        from_state: Optional[AppointmentState],
        to_state: AppointmentState
    ) -> bool:
        """
        Check if a state transition is valid.
        
        Args:
            from_state: Current state (None for initial state)
            to_state: Desired next state
            
        Returns:
            True if transition is valid, False otherwise
        """
        valid_next_states = self.VALID_TRANSITIONS.get(from_state, [])
        return to_state in valid_next_states
    
    def transition(
        self,
        appointment_id: str,
        request_id: str,
        to_state: AppointmentState,
        metadata: Optional[Dict[str, Any]] = None
    ) -> StateTransition:
        """
        Perform a state transition.
        
        Args:
            appointment_id: Unique appointment ID
            request_id: Unique request ID
            to_state: Target state
            metadata: Optional transition metadata
            
        Returns:
            StateTransition object
            
        Raises:
            InvalidStateTransitionError: If transition is not valid
        """
        if not self.can_transition(self.current_state, to_state):
            raise InvalidStateTransitionError(
                f"Invalid transition from {self.current_state} to {to_state}"
            )
        
        transition = StateTransition(
            appointment_id=appointment_id,
            request_id=request_id,
            from_state=self.current_state,
            to_state=to_state,
            metadata=metadata
        )
        
        self.transition_history.append(transition)
        self.current_state = to_state
        
        return transition
    
    def get_current_state(self) -> Optional[AppointmentState]:
        """Get the current state"""
        return self.current_state
    
    def is_terminal_state(self) -> bool:
        """Check if current state is terminal (no further transitions)"""
        if self.current_state is None:
            return False
        return len(self.VALID_TRANSITIONS.get(self.current_state, [])) == 0
    
    def get_transition_history(self) -> List[StateTransition]:
        """Get all state transitions"""
        return self.transition_history.copy()
    
    def get_last_transition(self) -> Optional[StateTransition]:
        """Get the most recent transition"""
        return self.transition_history[-1] if self.transition_history else None


class InvalidStateTransitionError(Exception):
    """Raised when an invalid state transition is attempted"""
    pass


# Helper functions for common state checks

def is_success_state(state: AppointmentState) -> bool:
    """Check if state represents successful booking"""
    return state == AppointmentState.CONFIRMED


def is_failure_state(state: AppointmentState) -> bool:
    """Check if state represents failed booking"""
    return state in [AppointmentState.FAILED, AppointmentState.CANCELLED]


def is_in_progress_state(state: AppointmentState) -> bool:
    """Check if state represents in-progress booking"""
    return state in [
        AppointmentState.INITIATED,
        AppointmentState.IN_PROGRESS,
        AppointmentState.CALENDAR_SYNCING,
        AppointmentState.PENDING_RETRY,
        AppointmentState.COMPENSATING
    ]


def get_state_description(state: AppointmentState) -> str:
    """Get human-readable description of state"""
    descriptions = {
        AppointmentState.INITIATED: "Request received and validated",
        AppointmentState.IN_PROGRESS: "Creating appointment record",
        AppointmentState.CALENDAR_SYNCING: "Syncing with calendar service",
        AppointmentState.CONFIRMED: "Appointment confirmed successfully",
        AppointmentState.FAILED: "Appointment booking failed",
        AppointmentState.COMPENSATING: "Rolling back changes",
        AppointmentState.PENDING_RETRY: "Queued for retry",
        AppointmentState.CANCELLED: "Appointment cancelled"
    }
    return descriptions.get(state, "Unknown state")
