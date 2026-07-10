"""Browser capability components used by the MCP tab wrapper."""

from .elements import ElementOperations
from .frames import FrameOperations
from .interaction import InteractionOperations
from .navigation import NavigationOperations
from .network import NetworkOperations
from .observation import ObservationOperations
from .page import PageOperations
from .storage import StorageOperations
from .waits import WaitOperations
from .workflows import WorkflowOperations

__all__ = [
    "ElementOperations",
    "FrameOperations",
    "InteractionOperations",
    "NavigationOperations",
    "NetworkOperations",
    "ObservationOperations",
    "PageOperations",
    "StorageOperations",
    "WaitOperations",
    "WorkflowOperations",
]
