"""
Type stub file for Python CAN library.

This file provides basic type hints for commonly used Python CAN components.
Only includes essential functionality used in the CoachIQ project.
"""

from typing import Any

class Message:
    """CAN Message class."""

    arbitration_id: int
    data: bytes
    is_extended_id: bool

    def __init__(
        self,
        arbitration_id: int,
        data: bytes | list[int],
        is_extended_id: bool = False,
        **kwargs: Any,
    ) -> None: ...

class BusABC:
    """Abstract Base Class for CAN bus implementations."""

    def send(self, message: Message, timeout: float | None = None) -> None: ...
    async def send_periodic(self, message: Message, period: float) -> Any: ...

class Bus(BusABC):
    """CAN bus implementation."""

    def __init__(
        self,
        channel: str | None = None,
        bustype: str | None = None,
        **kwargs: Any,
    ) -> None: ...

class CanError(Exception):
    """Base class for all python-can exceptions."""

class CanOperationError(CanError):
    """Indicates an operational error occurred in python-can."""

class CanInterfaceNotImplementedError(CanError):
    """Indicates that the CAN interface is not implemented or available."""

# Interface module
class Interface:
    """Interface module for CAN."""

    @staticmethod
    def Bus(
        channel: str | None = None,
        bustype: str | None = None,
        **kwargs: Any,
    ) -> Bus: ...

interface = Interface()

# Module structure for submodule imports
class BusModule:
    """bus module namespace."""

    BusABC = BusABC
    Bus = Bus

class ExceptionsModule:
    """exceptions module namespace."""

    CanError = CanError
    CanOperationError = CanOperationError
    CanInterfaceNotImplementedError = CanInterfaceNotImplementedError

# Export modules for submodule imports
bus = BusModule()
exceptions = ExceptionsModule()
