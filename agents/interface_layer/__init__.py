"""Interface layer public contract for external request validation and normalization.

This package is intentionally independent from intent, session, monitoring, and
infrastructure layers. It exposes only the minimal request/response models and
service entry point required by a future downstream caller.
"""

from .schemas import InterfaceRequest, InterfaceResponse
from .service import InterfaceService

__all__ = [
    "InterfaceRequest",
    "InterfaceResponse",
    "InterfaceService",
]
