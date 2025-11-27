import time
from typing import Dict, Tuple, Optional


class MockCalendarService:
    """
    Simulated calendar service with configurable behaviors per request_id or slot_id.
    Behaviors are tuples of (status, detail) where status in {success, timeout, malformed, partial, exception}.
    """

    def __init__(self):
        # behavior_lookup[key] = (status, detail)
        self.behavior_lookup: Dict[str, Tuple[str, str]] = {}
        self.default_behavior: Tuple[str, str] = ("success", "ok")

    def set_behavior(self, key: str, status: str, detail: str = ""):
        self.behavior_lookup[key] = (status, detail or status)

    def clear(self):
        self.behavior_lookup.clear()

    def sync(self, slot_id: str, request_id: str) -> Tuple[str, str]:
        # Priority: request_id > slot_id > default
        if request_id in self.behavior_lookup:
            status, detail = self.behavior_lookup[request_id]
        elif slot_id in self.behavior_lookup:
            status, detail = self.behavior_lookup[slot_id]
        else:
            status, detail = self.default_behavior

        # Simulate delay for timeout scenario
        if status == "timeout":
            time.sleep(0.1)
        return status, detail or status


# Shared singleton for tests (optional)
_default_instance: Optional[MockCalendarService] = None

def get_default_mock() -> MockCalendarService:
    global _default_instance
    if _default_instance is None:
        _default_instance = MockCalendarService()
    return _default_instance
