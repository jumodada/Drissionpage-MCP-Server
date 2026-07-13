"""Browser capability components used by the MCP tab wrapper."""

from .elements import ElementOperations
from .frames import FrameOperations
from .interaction import InteractionOperations
from .navigation import NavigationOperations
from .network import NetworkOperations
from .observation import ObservationOperations
from .page import PageOperations
from .pointer import PointerOperations
from .storage import StorageOperations
from .waits import WaitOperations
from .vision import VisionOperations
from .workflows import WorkflowOperations

__all__ = [
    "ElementOperations",
    "FrameOperations",
    "InteractionOperations",
    "NavigationOperations",
    "NetworkOperations",
    "ObservationOperations",
    "PageOperations",
    "PointerOperations",
    "StorageOperations",
    "WaitOperations",
    "VisionOperations",
    "WorkflowOperations",
]
