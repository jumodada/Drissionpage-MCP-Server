"""Browser capability components used by the MCP tab wrapper."""

from .dialogs import DialogOperations
from .downloads import DownloadOperations
from .elements import ElementOperations
from .frames import FrameOperations
from .interaction import InteractionOperations
from .navigation import NavigationOperations
from .network import NetworkOperations
from .observation import ObservationOperations
from .page import PageOperations
from .pointer import PointerOperations
from .storage import StorageOperations
from .targeting import TargetResolver
from .waits import WaitOperations

__all__ = [
    "DialogOperations",
    "DownloadOperations",
    "ElementOperations",
    "FrameOperations",
    "InteractionOperations",
    "NavigationOperations",
    "NetworkOperations",
    "ObservationOperations",
    "PageOperations",
    "PointerOperations",
    "StorageOperations",
    "TargetResolver",
    "WaitOperations",
]
