"""DCP — Device Context Protocol.

Bridge between LLM agents and physical devices.
"""
from dcp.bridge import Bridge, CallResult
from dcp.manifest import Event, Intent, Manifest, Param
from dcp.safety import SafetyError, check_call
from dcp.simulator import GenericSimulator
from dcp.wire import WIRE_VERSION, Frame, Kind, intent_id

__version__ = "0.3.0"

__all__ = [
    "Bridge",
    "CallResult",
    "Event",
    "Frame",
    "GenericSimulator",
    "Intent",
    "Kind",
    "Manifest",
    "Param",
    "SafetyError",
    "WIRE_VERSION",
    "check_call",
    "intent_id",
]
