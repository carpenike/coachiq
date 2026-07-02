"""
CAN Facade Service - Unified Entry Point for CAN Operations

Provides a single guardrail-critical entry point for all CAN command operations,
coordinating multiple underlying services with command validation and command-halt
coordination.

Note: "safety-critical" / "safety" naming in this file is historical and
refers to **API guardrail / command-validation** behavior, NOT vehicle safety.
The OEM Firefly MIRA panel owns the actual vehicle safety case. See
`docs/adr/ADR-0004-coachiq-is-not-the-safety-system.md`.
"""

import asyncio
import logging
from typing import Any, override

# CAN-specific Prometheus metrics for guardrail-critical monitoring
from prometheus_client import Counter, Gauge

# Health monitoring will be implemented later
from backend.core.guardrail_interfaces import (
    CommandHaltAction,
    GuardrailParticipant,
    GuardrailStatus,
    GuardrailTier,
)

logger = logging.getLogger(__name__)


def _counter_total(stats: dict[str, Any], *field_names: str) -> int:
    """Sum integer counter fields from an interface statistics dictionary."""
    total = 0
    for field_name in field_names:
        value = stats.get(field_name)
        if isinstance(value, int) and not isinstance(value, bool):
            total += value
    return total


# CAN-specific Prometheus metrics for guardrail-critical monitoring
CAN_MESSAGE_QUEUE_DEPTH = Gauge(
    "coachiq_can_message_queue_depth",
    "Number of messages in the CAN transmission queue",
    labelnames=["interface"],
)

CAN_BUS_LOAD_PERCENT = Gauge(
    "coachiq_can_bus_load_percent", "CAN bus utilization percentage", labelnames=["interface"]
)

CAN_ERROR_FRAMES_TOTAL = Counter(
    "coachiq_can_error_frames_total",
    "Total number of CAN error frames detected",
    labelnames=["interface", "error_type"],
)

CAN_COMMAND_HALTS_TOTAL = Counter(
    "coachiq_can_command_halts_total",
    "Total number of CAN facade command halts",
    labelnames=["reason"],
)

CAN_GUARDRAIL_STATUS = Gauge(
    "coachiq_can_guardrail_status",
    "Current CAN guardrail status (0=SAFE, 1=DEGRADED, 2=UNSAFE, 3=COMMAND_HALTED)",
)

CAN_MESSAGE_LATENCY_SECONDS = Gauge(
    "coachiq_can_message_latency_seconds",
    "Average CAN message processing latency",
    labelnames=["operation"],
)


class CANFacade(GuardrailParticipant):
    """
    Unified facade for all CAN operations.

    This is the ONLY service that API routers should interact with
    for CAN-related functionality. It coordinates all underlying
    CAN services and ensures guardrail-critical operations.
    """

    def __init__(  # noqa: PLR0913 - facade coordinates several CAN services by design
        self,
        bus_service: Any,
        injector: Any,
        message_filter: Any,
        recorder: Any,
        analyzer: Any,
        anomaly_detector: Any,
        interface_service: Any,
        performance_monitor: Any,
    ):
        super().__init__(
            guardrail_tier=GuardrailTier.CRITICAL,
            command_halt_action=CommandHaltAction.DISABLE_COMMANDS,
        )

        # Core services
        self._bus_service = bus_service
        self._injector = injector
        self._filter = message_filter
        self._recorder = recorder
        self._analyzer = analyzer
        self._anomaly_detector = anomaly_detector
        self._interface_service = interface_service
        self._performance_monitor = performance_monitor

        # Health monitoring
        self._health_task: asyncio.Task[None] | None = None

        # Performance monitoring helper
        self._monitor = self._performance_monitor.monitor_service_method

        # Instrument all public methods for performance monitoring
        self.send_message = self._monitor(
            service_name="CANFacade",
            method_name="send_message",
            alert_threshold_ms=50,  # Guardrail-critical: 50ms max
        )(self.send_message)

        self.halt_command_emission = self._monitor(
            service_name="CANFacade",
            method_name="halt_command_emission",
            alert_threshold_ms=20,  # Command halt: 20ms max
        )(self.halt_command_emission)

        self.get_queue_status = self._monitor(
            service_name="CANFacade", method_name="get_queue_status", alert_threshold_ms=100
        )(self.get_queue_status)

        self.get_bus_statistics = self._monitor(
            service_name="CANFacade", method_name="get_bus_statistics", alert_threshold_ms=200
        )(self.get_bus_statistics)

        self.get_recent_messages = self._monitor(
            service_name="CANFacade", method_name="get_recent_messages", alert_threshold_ms=150
        )(self.get_recent_messages)

        self.get_interfaces = self._monitor(
            service_name="CANFacade", method_name="get_interfaces", alert_threshold_ms=100
        )(self.get_interfaces)

        self.get_interface_details = self._monitor(
            service_name="CANFacade", method_name="get_interface_details", alert_threshold_ms=200
        )(self.get_interface_details)

        self.get_interface_mappings = self._monitor(
            service_name="CANFacade", method_name="get_interface_mappings", alert_threshold_ms=100
        )(self.get_interface_mappings)

        self.get_interface_status = self._monitor(
            service_name="CANFacade", method_name="get_interface_status", alert_threshold_ms=100
        )(self.get_interface_status)

        self.send_raw_message = self._monitor(
            service_name="CANFacade",
            method_name="send_raw_message",
            alert_threshold_ms=50,  # Guardrail-critical: 50ms max
        )(self.send_raw_message)

        self.get_comprehensive_health = self._monitor(
            service_name="CANFacade", method_name="get_comprehensive_health", alert_threshold_ms=300
        )(self.get_comprehensive_health)

    async def start(self) -> None:
        """Start all CAN services in proper order."""
        logger.info("Starting CANFacade and all underlying services")

        # Start services in dependency order
        await self._bus_service.start()
        await self._recorder.start()
        await self._filter.start()
        await self._analyzer.start()
        # Anomaly detector is passive, no start needed

        # Start health monitoring
        self._health_task = asyncio.create_task(self._monitor_health())

        logger.info("CANFacade started successfully")

    async def stop(self) -> None:
        """Stop all services gracefully."""
        logger.info("Stopping CANFacade")

        # Cancel health monitoring
        if self._health_task:
            self._health_task.cancel()

        # Stop services in reverse order
        await self._analyzer.stop()
        await self._filter.stop()
        await self._recorder.stop()
        await self._bus_service.stop()

    @override
    async def halt_command_emission(self, reason: str) -> None:
        """Halt CAN command emission through the facade-owned command path."""
        logger.critical("CANFacade command halt: %s", reason)
        self._set_command_halt_active(True)

        # Update Prometheus metrics
        CAN_COMMAND_HALTS_TOTAL.labels(reason=reason).inc()
        CAN_GUARDRAIL_STATUS.set(3)  # COMMAND_HALTED

        # Stop command emitters in parallel. The message filter is monitoring-only
        # for transmit flow today, so it remains outside the command-halt cascade.
        stop_tasks = [
            self._bus_service.halt_command_emission(reason),
            self._injector.halt_command_emission(reason),
            self._recorder.halt_command_emission(reason),
            self._analyzer.stop(),  # Operational analyzer stops observing during halt.
            self._anomaly_detector.stop(),
        ]

        results = await asyncio.gather(*stop_tasks, return_exceptions=True)

        # Log any failures
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.critical("Command halt failed for service %s: %s", i, result)

        logger.critical("CANFacade command halt completed")

    async def get_interface_status(self) -> dict[str, Any]:
        """Get CAN bus service health/status information."""
        status = self._bus_service.get_health_status()
        if asyncio.iscoroutine(status):
            return await status
        return status

    async def send_message(
        self, logical_interface: str, can_id: int, data: bytes
    ) -> dict[str, Any]:
        """Send a CAN message through the proper interface."""
        # Validate safety before sending
        if not await self.validate_command_precondition("send_message"):
            return {"success": False, "error": "Safety interlock active - cannot send message"}

        # Resolve logical to physical interface
        physical_interface = self._interface_service.resolve_interface(logical_interface)

        # Send through injector service
        return await self._injector.inject_message(
            interface=physical_interface, can_id=can_id, data=data
        )

    async def get_comprehensive_health(self) -> dict[str, Any]:
        """Get comprehensive health status from all services."""
        health_data: dict[str, Any] = {
            "facade_status": self._guardrail_status.value,
            "command_halt_active": self._command_halt_active,
            "services": {},
            "performance": {},
        }

        services = {
            "bus_service": self._bus_service,
            "filter": self._filter,
            "recorder": self._recorder,
            "analyzer": self._analyzer,
            "interface_service": self._interface_service,
        }

        for name, service in services.items():
            try:
                get_health_status = getattr(service, "get_health_status", None)
                if not callable(get_health_status):
                    health_data["services"][name] = {
                        "healthy": True,
                        "status": "available",
                        "detail": "Service does not expose detailed health status",
                    }
                    continue

                task = get_health_status()
                # Handle both sync and async health status methods
                if asyncio.iscoroutine(task):
                    health_data["services"][name] = await task
                else:
                    health_data["services"][name] = task
            except Exception as e:
                health_data["services"][name] = {"healthy": False, "error": str(e)}

        # Get performance metrics
        try:
            health_data["performance"] = await self._performance_monitor.get_service_metrics("1h")
        except Exception as e:
            health_data["performance"] = {"error": str(e)}

        return health_data

    async def _monitor_health(self) -> None:
        """Monitor health of all services continuously."""
        while True:
            try:
                await asyncio.sleep(5.0)  # Check every 5 seconds

                # Check critical services
                bus_health = self._bus_service.get_health_status()
                bus_healthy = (
                    bus_health.get("healthy", False) if isinstance(bus_health, dict) else False
                )

                # Update guardrail status and Prometheus metrics
                if not bus_healthy:
                    self._set_guardrail_status(GuardrailStatus.DEGRADED)
                    CAN_GUARDRAIL_STATUS.set(1)  # DEGRADED
                elif self._command_halt_active:
                    self._set_guardrail_status(GuardrailStatus.COMMAND_HALTED)
                    CAN_GUARDRAIL_STATUS.set(3)  # COMMAND_HALTED
                else:
                    self._set_guardrail_status(GuardrailStatus.SAFE)
                    CAN_GUARDRAIL_STATUS.set(0)  # SAFE

                # Update CAN-specific metrics
                try:
                    # Update queue depth metrics
                    queue_status = await self._recorder.get_queue_status()
                    queue_depth = queue_status.get("length", 0)
                    CAN_MESSAGE_QUEUE_DEPTH.labels(interface="primary").set(queue_depth)

                    # Update interface statistics
                    interface_stats = await self._interface_service.get_interface_stats()
                    for iface_name, stats in interface_stats.items():
                        # Update error frame metrics if available
                        error_count = _counter_total(stats, "rx_errors", "tx_errors")
                        if error_count > 0:
                            CAN_ERROR_FRAMES_TOTAL.labels(
                                interface=iface_name, error_type="general"
                            ).inc(error_count)

                        # Calculate and update bus load percentage
                        message_count = _counter_total(stats, "rx_packets", "tx_packets")
                        # Rough estimation: assume 500 messages/sec is 100% load
                        load_percent = min((message_count / 500.0) * 100, 100)
                        CAN_BUS_LOAD_PERCENT.labels(interface=iface_name).set(load_percent)

                except Exception as e:
                    logger.warning("Failed to update CAN metrics: %s", e)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Health monitoring error: %s", e)
                self._set_guardrail_status(GuardrailStatus.UNSAFE)
                CAN_GUARDRAIL_STATUS.set(2)  # UNSAFE

    async def get_queue_status(self) -> dict[str, Any]:
        """Get the current status of the CAN transmission queue."""
        # Try to get queue status from recorder if it has the method
        if hasattr(self._recorder, "get_queue_status"):
            return await self._recorder.get_queue_status()

        # Otherwise return a default/empty queue status
        logger.debug("Recorder service does not have get_queue_status method, returning default")
        return {
            "queue_length": 0,
            "queue_capacity": 1000,  # Default capacity
            "messages_processed": 0,
            "messages_dropped": 0,
            "queue_full_events": 0,
            "status": "operational",
        }

    async def get_bus_statistics(self) -> dict[str, Any]:
        """Get comprehensive statistics about CAN bus operations."""
        # Combine statistics from multiple services
        stats = {
            "interfaces": await self._interface_service.get_interface_stats(),
            "queue": await self.get_queue_status(),
            "analyzer": await self._analyzer.get_statistics(),
        }

        # Get performance baselines from monitor
        try:
            performance_data = await self._performance_monitor.get_performance_baselines()
            stats["performance"] = performance_data
        except Exception as e:
            logger.warning("Failed to get performance baselines: %s", e)
            stats["performance"] = {"error": str(e)}

        # Calculate summary metrics
        total_messages = sum(
            _counter_total(iface, "rx_packets", "tx_packets")
            for iface in stats["interfaces"].values()
        )
        total_errors = sum(
            _counter_total(iface, "rx_errors", "tx_errors")
            for iface in stats["interfaces"].values()
        )

        # Calculate message rate from performance data
        message_rate = 0.0
        if "performance" in stats and isinstance(stats["performance"], dict):
            # Performance data has structure: {"metrics": {...}, "summary": {...}}
            performance_summary = stats["performance"].get("summary", {})
            if isinstance(performance_summary, dict):
                # Look for CANFacade.send_message in the summary
                facade_send_key = "CANFacade.send_message"
                if facade_send_key in performance_summary:
                    send_stats = performance_summary[facade_send_key]
                    if isinstance(send_stats, dict):
                        # Calculate rate from count and time window (rough estimate)
                        count = send_stats.get("count", 0)
                        # Assume 1-hour window for rate calculation
                        message_rate = count / 3600.0  # messages per second

        stats["summary"] = {
            "total_messages": total_messages,
            "total_errors": total_errors,
            "message_rate": message_rate,
            "error_rate_percent": (total_errors / max(total_messages, 1)) * 100,
            "uptime": stats["performance"].get("uptime_seconds", 0.0),
        }

        return stats

    async def get_recent_messages(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get recent CAN messages captured on the bus."""
        # Delegate to recorder service
        return await self._recorder.get_recent_messages(limit)

    async def get_interfaces(self) -> list[str]:
        """Get a list of active CAN interfaces."""
        return await self._interface_service.get_interfaces()

    async def get_interface_details(self) -> dict[str, dict[str, Any]]:
        """Get detailed information about all CAN interfaces."""
        return await self._interface_service.get_interface_details()

    async def get_interface_mappings(self) -> dict[str, str]:
        """Get configured logical-to-physical CAN interface mappings."""
        return self._interface_service.get_all_mappings()

    async def send_raw_message(
        self, arbitration_id: int, data: bytes, interface: str
    ) -> dict[str, Any]:
        """Send a raw CAN message to the specified interface."""
        # Use the existing send_message method which already includes safety checks
        result = await self.send_message(
            logical_interface=interface, can_id=arbitration_id, data=data
        )

        # Transform result to match expected format
        if result.get("success", False):
            return {
                "success": True,
                "status": "sent",
                "arbitration_id": arbitration_id,
                "arbitration_id_hex": f"0x{arbitration_id:08X}",
                "data": data.hex().upper(),
                "interface": interface,
            }
        return {
            "success": False,
            "status": "error",
            "error": result.get("error", "Unknown error"),
            "arbitration_id": arbitration_id,
            "arbitration_id_hex": f"0x{arbitration_id:08X}",
            "data": data.hex().upper(),
            "interface": interface,
        }

    def get_health_status(self) -> dict[str, Any]:
        """Get basic health status for composition root."""
        return {
            "healthy": self._guardrail_status in [GuardrailStatus.SAFE, GuardrailStatus.DEGRADED],
            "guardrail_status": self._guardrail_status.value,
            "command_halt_active": self._command_halt_active,
        }
