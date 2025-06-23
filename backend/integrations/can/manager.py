"""
Manages CAN bus communication for the CoachIQ daemon.

This module is responsible for:
- Initializing and managing CAN bus listener threads for specified interfaces.
- Providing a writer task to send messages from an asynchronous queue to the CAN bus.
- Constructing RV-C specific CAN messages (e.g., for light control).
- Storing and providing access to active CAN bus interface objects.
"""

import asyncio
import logging
import time
from typing import Any

import can
from can.bus import BusABC
from can.exceptions import CanInterfaceNotImplementedError

from backend.core.config import get_settings
from backend.core.metrics import get_can_tx_queue_length

logger = logging.getLogger(__name__)

can_tx_queue: asyncio.Queue[tuple[can.Message, str]] = asyncio.Queue()
buses: dict[str, BusABC] = {}


async def can_writer(
    can_tracking_repository: Any = None, system_state_repository: Any = None
) -> None:
    """
    Continuously dequeues messages from can_tx_queue and sends them over the CAN bus.
    Handles sending each message twice as per RV-C specification.
    Attempts to initialize a bus if not already available in the 'buses' dictionary.

    Args:
        can_tracking_repository: Repository for CAN tracking operations
        system_state_repository: Repository for system state operations
    """
    settings = get_settings()
    default_bustype = settings.can.bustype
    try:
        while True:
            msg, interface_name = await can_tx_queue.get()
            try:
                get_can_tx_queue_length().set(can_tx_queue.qsize())
            except RuntimeError as e:
                logger.warning("Failed to update queue length metric: %s", e)
            try:
                bus = buses.get(interface_name)
                if not bus:
                    logger.warning(
                        "CAN writer: Bus for interface '%s' not pre-initialized. "
                        "Attempting to open with bustype '%s'.",
                        interface_name,
                        default_bustype,
                    )
                    try:
                        bus = can.interface.Bus(channel=interface_name, bustype=default_bustype)
                        buses[interface_name] = bus
                        logger.info(
                            "CAN writer: Successfully opened and registered bus for '%s'.",
                            interface_name,
                        )
                    except CanInterfaceNotImplementedError as e:
                        logger.error(
                            "CAN writer: CAN interface '%s' (%s) "
                            "is not implemented or configuration is missing: %s",
                            interface_name,
                            default_bustype,
                            e,
                        )
                        can_tx_queue.task_done()
                        continue
                    except Exception as e:
                        logger.error(
                            "CAN writer: Failed to initialize CAN bus '%s' (%s): %s",
                            interface_name,
                            default_bustype,
                            e,
                        )
                        can_tx_queue.task_done()
                        continue
                try:
                    bus.send(msg)
                    logger.info(
                        "CAN TX (1/2): %s ID: %08X Data: %s",
                        interface_name,
                        msg.arbitration_id,
                        msg.data.hex().upper(),
                    )
                    # --- CAN Sniffer Logging (TX, ALL messages) ---
                    now = time.time()
                    # Note: Decoder functionality moved to RVC integration feature
                    # For now, we'll log without decoding to maintain functionality
                    entry = None
                    instance = None
                    decoded = None
                    raw = None
                    source_addr = msg.arbitration_id & 0xFF
                    # Get controller source address from repository
                    controller_addr = 0x7F  # Default fallback
                    if system_state_repository:
                        try:
                            controller_addr = system_state_repository.get_controller_source_addr()
                        except Exception as e:
                            logger.warning("Failed to get controller source address: %s", e)

                    origin = "self" if source_addr == controller_addr else "other"
                    sniffer_entry = {
                        "timestamp": now,
                        "direction": "tx",
                        "arbitration_id": msg.arbitration_id,
                        "data": msg.data.hex().upper(),
                        "decoded": decoded,
                        "raw": raw,
                        "iface": interface_name,
                        "pgn": entry.get("pgn") if entry else None,
                        "dgn_hex": entry.get("dgn_hex") if entry else None,
                        "name": entry.get("name") if entry else None,
                        "instance": instance,
                        "source_addr": source_addr,
                        "origin": origin,
                    }
                    # Add to CAN tracking repository
                    if can_tracking_repository:
                        can_tracking_repository.add_can_sniffer_entry(sniffer_entry)
                        can_tracking_repository.add_pending_command(sniffer_entry)
                    else:
                        logger.warning(
                            "CAN tracking repository not available for sniffer/command tracking"
                        )
                    await asyncio.sleep(0.05)  # RV-C spec: send commands twice
                    bus.send(msg)
                    logger.info(
                        "CAN TX (2/2): %s ID: %08X Data: %s",
                        interface_name,
                        msg.arbitration_id,
                        msg.data.hex().upper(),
                    )
                except can.exceptions.CanError as e:
                    logger.error("CAN writer failed to send message on %s: %s", interface_name, e)
                except Exception as e:
                    logger.error(
                        "CAN writer encountered an unexpected error during send on %s: %s",
                        interface_name,
                        e,
                    )
            except Exception as e:
                logger.error(
                    "CAN writer encountered a critical unexpected error for %s: %s",
                    interface_name,
                    e,
                    exc_info=True,
                )
            finally:
                can_tx_queue.task_done()
                try:
                    get_can_tx_queue_length().set(can_tx_queue.qsize())
                except RuntimeError as e:
                    logger.warning("Failed to update queue length metric: %s", e)
    except asyncio.CancelledError:
        logger.info("CAN writer task cancelled, shutting down gracefully")
        return
