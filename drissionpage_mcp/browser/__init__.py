"""Browser capability components used by the MCP tab wrapper."""

from .accessibility import AccessibilityOperations
from .artifacts import PageArtifactOperations
from .auth import HttpAuthOperations
from .dialogs import DialogOperations
from .downloads import DownloadOperations
from .elements import ElementOperations
from .file_chooser import FileChooserOperations
from .frames import FrameOperations
from .interaction import InteractionOperations
from .navigation import NavigationOperations
from .network import NetworkOperations
from .observation import ObservationOperations
from .page import PageOperations
from .permissions import PermissionOperations
from .pointer import PointerOperations
from .storage import StorageOperations
from .targeting import DomTargetResolver, TargetResolver
from .waits import WaitOperations

__all__ = [
    "DialogOperations",
    "AccessibilityOperations",
    "PageArtifactOperations",
    "HttpAuthOperations",
    "DownloadOperations",
    "ElementOperations",
    "FileChooserOperations",
    "FrameOperations",
    "InteractionOperations",
    "NavigationOperations",
    "NetworkOperations",
    "ObservationOperations",
    "PageOperations",
    "PointerOperations",
    "PermissionOperations",
    "StorageOperations",
    "TargetResolver",
    "DomTargetResolver",
    "WaitOperations",
]
