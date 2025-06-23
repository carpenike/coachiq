"""
CAN Tools Feature Registration

Register CAN bus tools and utilities with the feature manager.
"""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from backend.integrations.can.can_bus_recorder import CANBusRecorder
from backend.integrations.can.message_filter import MessageFilter
from backend.integrations.can.message_injector import (
    CANMessageInjector,
    InjectionRequest,
    InjectionResult,
    SafetyLevel,
)
from backend.integrations.can.protocol_analyzer import ProtocolAnalyzer

logger = logging.getLogger(__name__)


def _register_with_service_registry(service_name: str, service_instance: Any) -> None:
    """
    Register a service with ServiceRegistry if available.

    Args:
        service_name: Name to register the service under
        service_instance: Service instance to register
    """
    # Note: ServiceRegistry registration should happen during application startup,
    # not at runtime. This function is kept for backward compatibility but
    # effectively does nothing now. Services should be registered in main.py
    # during the application startup phase.
    logger.debug(
        "Skipping runtime ServiceRegistry registration for %s. "
        "Services should be registered during application startup.",
        service_name,
    )


def register_can_tools_features() -> None:
    """
    Register CAN tools features (DEPRECATED).

    This function is kept for backward compatibility but does nothing.
    CAN tools are now managed by ServiceRegistry.
    """
    logger.info("CAN tools registration called but deprecated - use ServiceRegistry")


def create_audit_callback() -> Callable[[InjectionRequest, InjectionResult], None] | None:
    """
    Create audit callback for message injection logging.

    Returns:
        Audit callback function or None
    """

    def audit_injection(request: InjectionRequest, result: InjectionResult) -> None:
        """Log injection attempt for audit trail."""
        try:
            # Get security audit service if available from ServiceRegistry
            security_audit = None
            try:
                from backend.core.dependencies import get_service_registry

                service_registry = get_service_registry()
                if service_registry.has_service("security_audit_service"):
                    security_audit = service_registry.get_service("security_audit_service")
            except Exception as e:
                logger.debug("Could not get security audit service: %s", e)

            if security_audit:
                # Log to security audit
                audit_data = {
                    "action": "can_message_injection",
                    "user": request.user,
                    "interface": request.interface,
                    "can_id": f"0x{request.can_id:X}",
                    "data": request.data.hex(),
                    "mode": request.mode.value,
                    "success": result.success,
                    "messages_sent": result.messages_sent,
                    "duration": result.duration,
                    "warnings": result.warnings,
                    "error": result.error,
                    "reason": request.reason,
                    "description": request.description,
                }

                # Determine severity based on result
                severity = "info"
                if result.error:
                    severity = "error"
                elif result.warnings or not result.success:
                    severity = "warning"

                # Log audit event
                logger.info(
                    "CAN injection audit: user=%s, can_id=0x%X, success=%s, severity=%s",
                    request.user,
                    request.can_id,
                    result.success,
                    severity,
                )

                # TODO: Call security audit service method when available
                # security_audit.log_event(audit_data, severity=severity)

            else:
                # Fallback to standard logging
                logger.info(
                    "CAN message injection: user=%s, interface=%s, can_id=0x%X, "
                    "mode=%s, success=%s, sent=%d, duration=%.3fs, reason=%s",
                    request.user,
                    request.interface,
                    request.can_id,
                    request.mode.value,
                    result.success,
                    result.messages_sent,
                    result.duration,
                    request.reason,
                )

                if result.warnings:
                    logger.warning("Injection warnings: %s", ", ".join(result.warnings))

                if result.error:
                    logger.error("Injection error: %s", result.error)

        except Exception as e:
            logger.error("Audit callback error: %s", e)

    return audit_injection


def create_alert_callback() -> Callable[[dict[str, Any]], Any] | None:
    """
    Create alert callback for message filter alerts.

    Returns:
        Alert callback function or None
    """

    async def send_filter_alert(alert_data: dict[str, Any]) -> None:
        """Send alert for matched filter rule."""
        try:
            rule = alert_data.get("rule")
            message = alert_data.get("message", {})
            alert_params = alert_data.get("alert_data", {})

            if not rule:
                logger.error("Alert callback received without rule data")
                return

            # Log the alert
            logger.warning(
                "CAN filter alert: rule=%s, can_id=0x%X, interface=%s",
                rule.name,
                message.get("can_id", 0),
                message.get("interface", "unknown"),
            )

            # Get notification service if available from ServiceRegistry
            notifications = None
            try:
                from backend.core.dependencies import get_service_registry

                service_registry = get_service_registry()
                if service_registry.has_service("notifications"):
                    notifications = service_registry.get_service("notifications")
            except Exception as e:
                logger.debug("Could not get notifications service: %s", e)

            if notifications:
                # Send notification
                notification_data = {
                    "title": f"CAN Filter Alert: {rule.name}",
                    "body": (
                        f"Filter rule '{rule.name}' matched message on "
                        f"{message.get('interface', 'unknown')}"
                    ),
                    "priority": alert_params.get("priority", "medium"),
                    "data": {
                        "rule_id": rule.id,
                        "rule_name": rule.name,
                        "can_id": f"0x{message.get('can_id', 0):X}",
                        "interface": message.get("interface", "unknown"),
                        "data": message.get("data", ""),
                        "timestamp": message.get("timestamp", 0),
                    },
                }

                # TODO: Call notification service when method is available
                # await notifications.send_notification(notification_data)

            # Update WebSocket clients if available from ServiceRegistry
            websocket = None
            try:
                from backend.core.dependencies import get_service_registry

                service_registry = get_service_registry()
                if service_registry.has_service("websocket_manager"):
                    websocket = service_registry.get_service("websocket_manager")
            except Exception as e:
                logger.debug("Could not get websocket service: %s", e)
            if websocket:
                ws_message = {
                    "type": "can_filter_alert",
                    "rule": {
                        "id": rule.id,
                        "name": rule.name,
                        "priority": rule.priority,
                    },
                    "message": {
                        "can_id": f"0x{message.get('can_id', 0):X}",
                        "interface": message.get("interface", "unknown"),
                        "data": message.get("data", ""),
                        "timestamp": message.get("timestamp", 0),
                    },
                }

                # TODO: Broadcast to WebSocket clients when method is available
                # await websocket.broadcast(ws_message)

        except Exception as e:
            logger.error("Alert callback error: %s", e)

    return send_filter_alert
