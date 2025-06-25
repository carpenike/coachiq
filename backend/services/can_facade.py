"""
CAN Facade Service - Unified Entry Point for CAN Operations

Provides a single, safety-critical entry point for all CAN operations,
coordinating multiple underlying services with proper safety validation
and emergency stop coordination.
"""

import asyncio
import logging
from typing import Any

# CAN-specific Prometheus metrics for safety-critical monitoring
from prometheus_client import Counter, Gauge

# Health monitoring will be implemented later
from backend.core.safety_interfaces import (
    SafeStateAction,
    SafetyAware,
    SafetyClassification,
    SafetyStatus,
)

logger = logging.getLogger(__name__)

# CAN-specific Prometheus metrics for safety-critical monitoring
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

CAN_EMERGENCY_STOPS_TOTAL = Counter(
    "coachiq_can_emergency_stops_total",
    "Total number of CAN facade emergency stops",
    labelnames=["reason"],
)

CAN_SAFETY_STATUS = Gauge(
    "coachiq_can_safety_status",
    "Current CAN safety status (0=SAFE, 1=DEGRADED, 2=UNSAFE, 3=EMERGENCY_STOP)",
)

CAN_MESSAGE_LATENCY_SECONDS = Gauge(
    "coachiq_can_message_latency_seconds",
    "Average CAN message processing latency",
    labelnames=["operation"],
)


class CANFacade(SafetyAware):
    """
    Unified facade for all CAN operations.

    This is the ONLY service that API routers should interact with
    for CAN-related functionality. It coordinates all underlying
    CAN services and ensures safety-critical operations.
    """

    def __init__(
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
            safety_classification=SafetyClassification.CRITICAL,
            safe_state_action=SafeStateAction.DISABLE,
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
        self._health_task: asyncio.Task | None = None

        # Performance monitoring helper
        self._monitor = self._performance_monitor.monitor_service_method

        # Instrument all public methods for performance monitoring
        self.send_message = self._monitor(
            service_name="CANFacade",
            method_name="send_message",
            alert_threshold_ms=50,  # Safety-critical: 50ms max
        )(self.send_message)

        self.emergency_stop = self._monitor(
            service_name="CANFacade",
            method_name="emergency_stop",
            alert_threshold_ms=20,  # Emergency stop: 20ms max
        )(self.emergency_stop)

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

        self.send_raw_message = self._monitor(
            service_name="CANFacade",
            method_name="send_raw_message",
            alert_threshold_ms=50,  # Safety-critical: 50ms max
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

    async def emergency_stop(self, reason: str) -> None:
        """Execute coordinated emergency stop across all services."""
        logger.critical("CANFacade EMERGENCY STOP: %s", reason)
        self._set_emergency_stop_active(True)

        # Update Prometheus metrics
        CAN_EMERGENCY_STOPS_TOTAL.labels(reason=reason).inc()
        CAN_SAFETY_STATUS.set(3)  # EMERGENCY_STOP

        # Stop all safety-critical services in parallel
        stop_tasks = [
            self._bus_service.emergency_stop(reason),
            self._injector.emergency_stop(reason),
            self._filter.emergency_stop(reason),
            self._recorder.emergency_stop(reason),
            self._analyzer.stop(),  # Operational services just stop
            self._anomaly_detector.stop(),
        ]

        results = await asyncio.gather(*stop_tasks, return_exceptions=True)

        # Log any failures
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.critical("Emergency stop failed for service %s: %s", i, result)

        logger.critical("CANFacade emergency stop completed")

    async def get_interface_status(self) -> dict[str, Any]:
        """Get CAN interface status from all services."""
        return await self._bus_service.get_health_status()

    async def send_message(
        self, logical_interface: str, can_id: int, data: bytes
    ) -> dict[str, Any]:
        """Send a CAN message through the proper interface."""
        # Validate safety before sending
        if not await self.validate_safety_interlock("send_message"):
            return {"success": False, "error": "Safety interlock active - cannot send message"}

        # Resolve logical to physical interface
        physical_interface = self._interface_service.resolve_interface(logical_interface)

        # Send through injector service
        return await self._injector.inject_message(
            interface=physical_interface, can_id=can_id, data=data
        )

    async def get_comprehensive_health(self) -> dict[str, Any]:
        """Get comprehensive health status from all services."""
        health_data = {
            "facade_status": self._safety_status.value,
            "emergency_stop_active": self._emergency_stop_active,
            "services": {},
            "performance": {},
        }

        # Collect health from all services
        service_health_tasks = {
            "bus_service": self._bus_service.get_health_status(),
            "filter": self._filter.get_health_status(),
            "recorder": self._recorder.get_health_status(),
            "analyzer": self._analyzer.get_health_status(),
            "interface_service": self._interface_service.get_health_status(),
        }

        # Gather all health data
        for name, task in service_health_tasks.items():
            try:
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

                # Update safety status and Prometheus metrics
                if not bus_healthy:
                    self._set_safety_status(SafetyStatus.DEGRADED)
                    CAN_SAFETY_STATUS.set(1)  # DEGRADED
                elif self._emergency_stop_active:
                    self._set_safety_status(SafetyStatus.EMERGENCY_STOP)
                    CAN_SAFETY_STATUS.set(3)  # EMERGENCY_STOP
                else:
                    self._set_safety_status(SafetyStatus.SAFE)
                    CAN_SAFETY_STATUS.set(0)  # SAFE

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
                        error_count = stats.get("error_count", 0)
                        if error_count > 0:
                            CAN_ERROR_FRAMES_TOTAL.labels(
                                interface=iface_name, error_type="general"
                            ).inc(error_count)

                        # Calculate and update bus load percentage
                        message_count = stats.get("message_count", 0)
                        # Rough estimation: assume 500 messages/sec is 100% load
                        load_percent = min((message_count / 500.0) * 100, 100)
                        CAN_BUS_LOAD_PERCENT.labels(interface=iface_name).set(load_percent)

                except Exception as e:
                    logger.warning("Failed to update CAN metrics: %s", e)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Health monitoring error: %s", e)
                self._set_safety_status(SafetyStatus.UNSAFE)
                CAN_SAFETY_STATUS.set(2)  # UNSAFE

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
            iface.get("message_count", 0) for iface in stats["interfaces"].values()
        )
        total_errors = sum(iface.get("error_count", 0) for iface in stats["interfaces"].values())

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
        """Get basic health status for ServiceRegistry."""
        return {
            "healthy": self._safety_status in [SafetyStatus.SAFE, SafetyStatus.DEGRADED],
            "safety_status": self._safety_status.value,
            "emergency_stop_active": self._emergency_stop_active,
        }
