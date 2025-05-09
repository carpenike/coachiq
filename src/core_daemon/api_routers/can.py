"""
Defines FastAPI APIRouter for CAN bus related operations.

This module includes routes to get the status of CAN interfaces,
check the CAN transmit queue, and potentially other CAN-specific actions.
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter
from pyroute2 import IPRoute  # Import IPRoute

# Assuming can_tx_queue is in core_daemon.can_manager
from core_daemon.can_manager import can_tx_queue

# Assuming CANInterfaceStats model is in core_daemon.models
from core_daemon.models import AllCANStats, CANInterfaceStats

logger = logging.getLogger(__name__)

api_router_can = APIRouter()  # FastAPI router for CAN-related endpoints


def get_stats_from_pyroute2_link(link: Any) -> CANInterfaceStats:
    """
    Populates a CANInterfaceStats object from pyroute2 link data.

    Args:
        link: A dictionary representing a network interface from pyroute2.

    Returns:
        A CANInterfaceStats object.
    """
    interface_name = link.get_attr("IFLA_IFNAME")
    stats = CANInterfaceStats(name=interface_name)

    stats.state = link.get_attr("IFLA_OPERSTATE")  # General operstate (UP, DOWN, UNKNOWN etc)

    if link.get_attr("IFLA_LINKMODE") == 1:  # LINKMODE_DORMANT is 1, LINKMODE_DEFAULT is 0
        stats.state = "DORMANT"  # More specific if link is DORMANT

    # Statistics are usually under IFLA_STATS or IFLA_STATS64
    link_stats = link.get_attr("IFLA_STATS64") or link.get_attr("IFLA_STATS")
    if link_stats:
        stats.rx_packets = link_stats.get("rx_packets")
        stats.tx_packets = link_stats.get("tx_packets")
        stats.rx_bytes = link_stats.get("rx_bytes")
        stats.tx_bytes = link_stats.get("tx_bytes")
        stats.rx_errors = link_stats.get("rx_errors")
        stats.tx_errors = link_stats.get("tx_errors")
        # pyroute2 stats names are fairly direct: 'rx_dropped', 'tx_dropped', 'multicast',
        # 'collisions', 'rx_crc_errors', 'rx_frame_errors', 'rx_fifo_errors',
        # 'rx_missed_errors', etc. 'tx_aborted_errors', 'tx_carrier_errors',
        # 'tx_fifo_errors', 'tx_heartbeat_errors', 'tx_window_errors'
        # These are general interface stats, not CAN specific error counters like bus_off,
        # error_passive etc.

    # CAN specific details are often in IFLA_LINKINFO -> INFO_DATA
    linkinfo = link.get("linkinfo")
    if linkinfo and linkinfo.get_attr("IFLA_INFO_KIND") == "can":
        info_data = linkinfo.get("info_data")
        if info_data:
            stats.bitrate = info_data.get_attr("CAN_BITTIMING_BITRATE")
            # sample_point is often in permille (1/1000)
            stats.sample_point = info_data.get_attr("CAN_BITTIMING_SAMPLE_POINT") / 1000.0
            # stats.tq = info_data.get_attr('CAN_BITTIMING_TQ')
            # stats.prop_seg = info_data.get_attr('CAN_BITTIMING_PROP_SEG')
            # stats.phase_seg1 = info_data.get_attr('CAN_BITTIMING_PHASE_SEG1')
            # stats.phase_seg2 = info_data.get_attr('CAN_BITTIMING_PHASE_SEG2')
            # stats.sjw = info_data.get_attr('CAN_BITTIMING_SJW')
            # stats.brp = info_data.get_attr('CAN_BITTIMING_BRP')

            # CAN controller mode details
            # ctrlmode = info_data.get_attr('CAN_CTRLMODE')
            # if ctrlmode:
            #     stats.loopback = bool(ctrlmode & CAN_CTRLMODE_LOOPBACK)
            #     stats.listen_only = bool(ctrlmode & CAN_CTRLMODE_LISTENONLY)
            #     stats.triple_sampling = bool(ctrlmode & CAN_CTRLMODE_3_SAMPLES)
            #     stats.one_shot = bool(ctrlmode & CAN_CTRLMODE_ONE_SHOT)
            #     stats.berr_reporting = bool(ctrlmode & CAN_CTRLMODE_BERR_REPORTING)

            # CAN state (ERROR-ACTIVE, ERROR-WARNING, ERROR-PASSIVE, BUS-OFF)
            can_state_val = info_data.get_attr("CAN_STATE")
            if can_state_val is not None:
                # pyroute2 provides integer constants for these states
                # from pyroute2.netlink.rtnl.ifinfmsg import CAN_STATE
                # Example: CAN_STATE_ERROR_ACTIVE = 0, CAN_STATE_ERROR_WARNING = 1, etc.
                # Mapping these integers to string representations:
                can_state_map = {
                    0: "ERROR-ACTIVE",
                    1: "ERROR-WARNING",
                    2: "ERROR-PASSIVE",
                    3: "BUS-OFF",
                    4: "STOPPED",
                    5: "SLEEPING",
                }
                stats.state = can_state_map.get(
                    can_state_val, stats.state
                )  # Override general state

            # CAN specific error counters (these might be under IFLA_XSTATS)
            # xstats = link.get_attr('IFLA_XSTATS')
            # if xstats and xstats.get_attr('LINK_XSTATS_TYPE') == IFLA_XSTATS_LINK_CAN:
            #    stats.bus_errors = xstats.get_attr('can_stats_bus_error')
            #    stats.error_warning = xstats.get_attr('can_stats_error_warning')
            #    stats.error_passive = xstats.get_attr('can_stats_error_passive')
            #    stats.bus_off = xstats.get_attr('can_stats_bus_off')
            #    stats.restarts = xstats.get_attr('can_stats_restarts')
            # Accessing CAN error counters (bus_off_cnt, error_passive_cnt, etc.)
            # via IFLA_LINKINFO -> INFO_DATA -> CAN_BERR_COUNTER might be more reliable.
            berr_counter = info_data.get_attr("CAN_BERR_COUNTER")
            if berr_counter:
                # These are receive and transmit error counters, not state counters.
                # stats.rx_errors_can = berr_counter.get('rxerr')
                # stats.tx_errors_can = berr_counter.get('txerr')
                pass  # Placeholder for more detailed CAN error counter parsing

            # Clock frequency
            # clock_info = info_data.get_attr('CAN_CLOCK')
            # if clock_info:
            #    stats.clock_freq = clock_info.get('freq')

    # For fields like promiscuity, allmulti, parentbus, parentdev,
    # these are attributes of the link itself.
    stats.promiscuity = link.get_attr("IFLA_PROMISCUITY")
    # stats.allmulti = link.get_attr('IFLA_ALLMULTI')

    # Parent device info
    # master_idx = link.get_attr('IFLA_MASTER')
    # if master_idx:
    #    try:
    #        with IPRoute() as ipr_master:
    #            master_link = ipr_master.get_links(master_idx)
    #            if master_link:
    #                stats.parentdev = master_link[0].get_attr('IFLA_IFNAME')
    #    except Exception as e:
    #        logger.warning(f"Could not get master link name for {interface_name}: {e}")

    # Note: Some fields like restart_ms, tq, prop_seg, etc. from `ip -details`
    # are derived or specific to the `ip` command's interpretation and might not
    # be directly available as separate attributes in pyroute2's raw netlink data.
    # They are part of the CAN_BITTIMING structure but pyroute2 might not expose
    # them individually without deeper parsing of raw netlink messages or if they
    # are not standard attributes.

    return stats


async def get_can_interfaces_pyroute2() -> list[str]:
    """
    Lists available CAN interfaces using pyroute2.

    Returns:
        A list of CAN interface names (e.g., ["can0", "can1"]), or an empty
        list if none are found or an error occurs.
    """
    interfaces = []
    try:
        with IPRoute() as ipr:
            # Get links of type 'can'.
            # Modern pyroute2 should support kind filtering.
            links = ipr.get_links(kind="can")
            for link in links:
                interfaces.append(link.get_attr("IFLA_IFNAME"))
        return interfaces
    except Exception as e:
        logger.error(f"Error listing CAN interfaces with pyroute2: {e}", exc_info=True)
        return []


@api_router_can.get("/can/status", response_model=AllCANStats)
async def get_can_status():
    """
    Retrieves detailed status for all CAN interfaces using pyroute2.
    """
    interfaces_data: Dict[str, CANInterfaceStats] = {}

    try:
        with IPRoute() as ipr:
            # Get all links and then filter for CAN, or get CAN links directly
            # This ensures we have the full link object for stats, not just names.
            can_links = ipr.get_links(kind="can")

            if not can_links:
                logger.info("No CAN interfaces found with pyroute2.")
                return AllCANStats(interfaces={})

            for link in can_links:
                interface_name = link.get_attr("IFLA_IFNAME")
                try:
                    # The 'link' object already contains most of the info.
                    parsed_stats = get_stats_from_pyroute2_link(link)
                    interfaces_data[interface_name] = parsed_stats
                except Exception as e:
                    logger.exception(
                        f"Exception processing interface {interface_name} with pyroute2: {e}"
                    )
                    interfaces_data[interface_name] = CANInterfaceStats(
                        name=interface_name, state="Exception/Pyroute2Error"
                    )

        if not interfaces_data and can_links:  # Should only happen if all parsing failed
            logger.warning(
                "CAN interfaces found but failed to retrieve status for all using pyroute2."
            )
            # Populate with minimal error state if all parsing failed
            for link_obj in can_links:
                ifname = link_obj.get_attr("IFLA_IFNAME")
                if ifname not in interfaces_data:
                    interfaces_data[ifname] = CANInterfaceStats(
                        name=ifname, state="Error/ParseFailure"
                    )

    except Exception as e:
        logger.error(f"Failed to get CAN status using pyroute2: {e}", exc_info=True)
        # This would be a more global error, like failing to open the netlink socket.
        return AllCANStats(interfaces={})  # Or raise HTTPException

    return AllCANStats(interfaces=interfaces_data)


@api_router_can.get("/queue", response_model=Dict[str, Any])
async def get_queue_status():
    """
    Return the current status of the CAN transmit queue.

    Provides the current number of items in the `can_tx_queue` and its
    maximum configured size.

    Returns:
        A dictionary with "length" (current queue size) and "maxsize"
        (maximum queue size, or "unbounded").
    """
    return {"length": can_tx_queue.qsize(), "maxsize": can_tx_queue.maxsize or "unbounded"}
