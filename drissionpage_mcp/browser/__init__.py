"""Browser capability components used by the MCP tab wrapper."""

from .elements import ElementOperations
from .frames import FrameOperations
from .interaction import InteractionOperations
from .navigation import NavigationOperations
from .network import NetworkOperations
from .storage import StorageOperations
from .waits import WaitOperations

__all__ = [
    "ElementOperations",
    "FrameOperations",
    "InteractionOperations",
    "NavigationOperations",
    "NetworkOperations",
    "StorageOperations",
    "WaitOperations",
]
