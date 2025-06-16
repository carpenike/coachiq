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
from backend.services.feature_manager import FeatureManager

logger = logging.getLogger(__name__)


def register_can_tools_features(feature_manager: FeatureManager) -> None:
    """
    Register CAN tools features with the feature manager.

    Args:
        feature_manager: Feature manager instance
    """
    logger.info("Registering CAN tools features")

    # Load the raw YAML to get custom fields
    yaml_path = Path(__file__).parent.parent.parent / "services" / "feature_flags.yaml"
    try:
        with open(yaml_path) as f:
            raw_config = yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to load feature flags YAML: {e}")
        return

    # Register CAN message injector
    injector_def = feature_manager.feature_definitions.get("can_message_injector")
    if not injector_def:
        logger.warning("CAN message injector not found in feature definitions")
        return

    # Get raw config with custom fields
    injector_raw_config = raw_config.get("can_message_injector", {})
    injector_config = injector_def.dict()

    if injector_config.get("enabled_by_default", False):
        # Parse safety level from raw config
        safety_level_str = injector_raw_config.get("safety_level", "moderate").lower()
        safety_level_map = {
            "strict": SafetyLevel.STRICT,
            "moderate": SafetyLevel.MODERATE,
            "permissive": SafetyLevel.PERMISSIVE,
        }
        safety_level = safety_level_map.get(safety_level_str, SafetyLevel.MODERATE)

        # Create audit callback if enabled
        audit_callback = None
        if injector_raw_config.get("audit_enabled", True):
            audit_callback = create_audit_callback(feature_manager)

        # Create and register message injector
        injector = CANMessageInjector(
            name="can_message_injector",
            enabled=True,
            core=injector_config.get("core", False),
            safety_level=safety_level,
            audit_callback=audit_callback,
        )

        feature_manager.register_feature(injector)
        logger.info(
            "Registered CAN message injector: safety_level=%s, audit=%s",
            safety_level.value,
            injector_raw_config.get("audit_enabled", True),
        )
    else:
        logger.info("CAN message injector is disabled")

    # Register CAN bus recorder
    recorder_def = feature_manager.feature_definitions.get("can_bus_recorder")
    if not recorder_def:
        logger.info("CAN bus recorder not found in feature definitions")
        recorder_raw_config = raw_config.get("can_bus_recorder", {})
    else:
        recorder_raw_config = raw_config.get("can_bus_recorder", {})
        recorder_config = recorder_def.dict()

    if recorder_def and recorder_config.get("enabled_by_default", False):
        # Create and register recorder
        recorder = CANBusRecorder(
            name="can_bus_recorder",
            enabled=True,
            core=recorder_config.get("core", False),
            buffer_size=recorder_raw_config.get("buffer_size", 100000),
            auto_save_interval=recorder_raw_config.get("auto_save_interval", 60.0),
            max_file_size_mb=recorder_raw_config.get("max_file_size_mb", 100.0),
        )

        feature_manager.register_feature(recorder)
        logger.info(
            "Registered CAN bus recorder: buffer_size=%d, auto_save=%fs",
            recorder.buffer_size,
            recorder.auto_save_interval,
        )
    else:
        logger.info("CAN bus recorder is disabled")

    # Register CAN protocol analyzer
    analyzer_def = feature_manager.feature_definitions.get("can_protocol_analyzer")
    if not analyzer_def:
        logger.info("CAN protocol analyzer not found in feature definitions")
        analyzer_raw_config = raw_config.get("can_protocol_analyzer", {})
    else:
        analyzer_raw_config = raw_config.get("can_protocol_analyzer", {})
        analyzer_config = analyzer_def.dict()

    if analyzer_def and analyzer_config.get("enabled_by_default", False):
        # Create and register analyzer
        analyzer = ProtocolAnalyzer(
            name="can_protocol_analyzer",
            enabled=True,
            core=analyzer_config.get("core", False),
            buffer_size=analyzer_raw_config.get("buffer_size", 10000),
            pattern_window_ms=analyzer_raw_config.get("pattern_window_ms", 5000.0),
        )

        feature_manager.register_feature(analyzer)
        logger.info(
            "Registered CAN protocol analyzer: buffer_size=%d, pattern_window=%fms",
            analyzer.buffer_size,
            analyzer.pattern_window_ms,
        )
    else:
        logger.info("CAN protocol analyzer is disabled")

    # Register CAN message filter
    filter_def = feature_manager.feature_definitions.get("can_message_filter")
    if not filter_def:
        logger.info("CAN message filter not found in feature definitions")
        filter_raw_config = raw_config.get("can_message_filter", {})
    else:
        filter_raw_config = raw_config.get("can_message_filter", {})
        filter_config = filter_def.dict()

    if filter_def and filter_config.get("enabled_by_default", False):
        # Create alert callback if needed
        alert_callback = None
        if filter_raw_config.get("enable_alerts", True):
            alert_callback = create_alert_callback(feature_manager)

        # Create and register message filter
        message_filter = MessageFilter(
            name="can_message_filter",
            enabled=True,
            core=filter_config.get("core", False),
            max_rules=filter_raw_config.get("max_rules", 100),
            alert_callback=alert_callback,
            capture_buffer_size=filter_raw_config.get("capture_buffer_size", 10000),
        )

        feature_manager.register_feature(message_filter)
        logger.info(
            "Registered CAN message filter: max_rules=%d, capture_buffer=%d",
            message_filter.max_rules,
            message_filter.capture_buffer_size,
        )
    else:
        logger.info("CAN message filter is disabled")


def create_audit_callback(
    feature_manager: FeatureManager,
) -> Callable[[InjectionRequest, InjectionResult], None] | None:
    """
    Create audit callback for message injection logging.

    Args:
        feature_manager: Feature manager instance

    Returns:
        Audit callback function or None
    """
    def audit_injection(request: InjectionRequest, result: InjectionResult) -> None:
        """Log injection attempt for audit trail."""
        try:
            # Get security audit service if available
            security_audit = feature_manager.get_feature("security_audit")

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
                    request.user, request.can_id, result.success, severity
                )

                # TODO: Call security audit service method when available
                # security_audit.log_event(audit_data, severity=severity)

            else:
                # Fallback to standard logging
                logger.info(
                    "CAN message injection: user=%s, interface=%s, can_id=0x%X, "
                    "mode=%s, success=%s, sent=%d, duration=%.3fs, reason=%s",
                    request.user, request.interface, request.can_id,
                    request.mode.value, result.success, result.messages_sent,
                    result.duration, request.reason
                )

                if result.warnings:
                    logger.warning("Injection warnings: %s", ", ".join(result.warnings))

                if result.error:
                    logger.error("Injection error: %s", result.error)

        except Exception as e:
            logger.error("Audit callback error: %s", e)

    return audit_injection


def create_alert_callback(
    feature_manager: FeatureManager,
) -> Callable[[dict[str, Any]], Any] | None:
    """
    Create alert callback for message filter alerts.

    Args:
        feature_manager: Feature manager instance

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

            # Get notification service if available
            notifications = feature_manager.get_feature("notifications")

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

            # Update WebSocket clients if available
            websocket = feature_manager.get_feature("websocket")
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
