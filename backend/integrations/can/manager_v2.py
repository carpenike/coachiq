"""
CAN Manager V2 - Repository Pattern Implementation

This is the migrated version of CAN manager functions that use repositories
directly instead of accessing AppState. Part of Phase 2R.3 migration.
"""

import asyncio
import logging
import time
from typing import TYPE_CHECKING

import can
from can.exceptions import CanInterfaceNotImplementedError

from backend.core.config import get_settings
from backend.core.metrics import get_can_tx_queue_length
from backend.integrations.can.manager import buses, can_tx_queue

if TYPE_CHECKING:
    from backend.services.can_service_v2 import CANWriterContext

logger = logging.getLogger(__name__)


async def can_writer_v2(writer_context: "CANWriterContext") -> None:
    """
    Continuously dequeues messages from can_tx_queue and sends them over the CAN bus.
    Handles sending each message twice as per RV-C specification.
    Attempts to initialize a bus if not already available in the 'buses' dictionary.

    This version uses repository pattern instead of AppState.

    Args:
        writer_context: Context object with repositories and controller info
    """
    settings = get_settings()
    default_bustype = settings.can.bustype
    try:
        while True:
            msg, interface_name = await can_tx_queue.get()
            try:
                get_can_tx_queue_length().set(can_tx_queue.qsize())
            except RuntimeError as e:
                logger.warning(f"Failed to update queue length metric: {e}")
            try:
                bus = buses.get(interface_name)
                if not bus:
                    logger.warning(
                        f"CAN writer: Bus for interface '{interface_name}' not pre-initialized. "
                        f"Attempting to open with bustype '{default_bustype}'."
                    )
                    try:
                        bus = can.interface.Bus(channel=interface_name, bustype=default_bustype)
                        buses[interface_name] = bus
                        logger.info(
                            f"CAN writer: Successfully opened and "
                            f"registered bus for '{interface_name}'."
                        )
                    except CanInterfaceNotImplementedError as e:
                        logger.error(
                            f"CAN writer: CAN interface '{interface_name}' ({default_bustype}) "
                            f"is not implemented or configuration is missing: {e}"
                        )
                        can_tx_queue.task_done()
                        continue
                    except Exception as e:
                        logger.error(
                            f"CAN writer: Failed to initialize CAN bus '{interface_name}' "
                            f"({default_bustype}): {e}"
                        )
                        can_tx_queue.task_done()
                        continue
                try:
                    bus.send(msg)
                    logger.info(
                        f"CAN TX (1/2): {interface_name} ID: {msg.arbitration_id:08X} "
                        f"Data: {msg.data.hex().upper()}"
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
                    origin = (
                        "self" if source_addr == writer_context.get_controller_source_addr() else "other"
                    )
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
                    writer_context.add_can_sniffer_entry(sniffer_entry)
                    writer_context.add_pending_command(sniffer_entry)
                    await asyncio.sleep(0.05)  # RV-C spec: send commands twice
                    bus.send(msg)
                    logger.info(
                        f"CAN TX (2/2): {interface_name} ID: {msg.arbitration_id:08X} "
                        f"Data: {msg.data.hex().upper()}"
                    )
                except can.exceptions.CanError as e:
                    logger.error(f"CAN writer failed to send message on {interface_name}: {e}")
                except Exception as e:
                    logger.error(
                        f"CAN writer encountered an unexpected error "
                        f"during send on {interface_name}: {e}"
                    )
            except Exception as e:
                logger.error(
                    f"CAN writer encountered a critical unexpected error for {interface_name}: {e}",
                    exc_info=True,
                )
            finally:
                can_tx_queue.task_done()
                try:
                    get_can_tx_queue_length().set(can_tx_queue.qsize())
                except RuntimeError as e:
                    logger.warning(f"Failed to update queue length metric: {e}")
    except asyncio.CancelledError:
        logger.info("CAN writer task cancelled, shutting down gracefully")
        return
