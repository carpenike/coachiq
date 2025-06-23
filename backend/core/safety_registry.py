"""
Safety-aware ServiceRegistry for ISO 26262-compliant RV-C vehicle control.

This module extends the standard ServiceRegistry with safety-specific functionality,
enabling centralized safety monitoring, emergency stop coordination, and safety
classification management across all services.
"""

import logging
from typing import Any, Dict, List, Optional, Set

from backend.core.safety_interfaces import SafetyCapable, SafetyClassification, SafetyStatus
from backend.core.service_dependency_resolver import DependencyType, ServiceDependency
from backend.core.service_registry import EnhancedServiceRegistry

logger = logging.getLogger(__name__)


class SafetyServiceRegistry(EnhancedServiceRegistry):
    """
    ServiceRegistry with safety-specific extensions for vehicle control systems.

    This registry maintains safety classifications, coordinates emergency stops,
    and provides safety status monitoring across all registered services.
    """

    def __init__(self):
        """Initialize safety-aware service registry."""
        super().__init__()
        self._safety_classifications: dict[str, SafetyClassification] = {}
        self._safety_metadata: dict[str, dict[str, Any]] = {}

    def register_safety_service(
        self,
        name: str,
        init_func,
        safety_classification: SafetyClassification,
        dependencies: list[ServiceDependency] | None = None,
        description: str = "",
        tags: set[str] | None = None,
        health_check=None,
        **kwargs,
    ) -> None:
        """
        Register a safety-aware service with safety classification.

        Args:
            name: Service name
            init_func: Service initialization function
            safety_classification: ISO 26262 safety classification
            dependencies: Service dependencies
            description: Service description
            tags: Service tags
            health_check: Health check function
            **kwargs: Additional registration parameters
        """
        # Add safety-specific tags
        if tags is None:
            tags = set()
        tags.add("safety-aware")
        tags.add(f"safety-{safety_classification.value}")

        # Store safety classification
        self._safety_classifications[name] = safety_classification

        # Store safety metadata
        self._safety_metadata[name] = {
            "classification": safety_classification,
            "description": description,
            "registered_at": self._get_current_timestamp(),
        }

        # Register with parent class
        self.register_service(
            name=name,
            init_func=init_func,
            dependencies=dependencies or [],
            description=f"[{safety_classification.value.upper()}] {description}",
            tags=tags,
            health_check=health_check,
            **kwargs,
        )

        logger.info(
            f"Registered safety service '{name}' with classification {safety_classification.value}"
        )

    def get_safety_critical_services(self) -> list[str]:
        """
        Get list of safety-critical service names.

        Returns:
            List of service names with CRITICAL classifications
        """
        critical_classifications = {
            SafetyClassification.CRITICAL,
        }

        return [
            name
            for name, classification in self._safety_classifications.items()
            if classification in critical_classifications
        ]

    def get_services_by_safety_classification(
        self, classification: SafetyClassification
    ) -> list[str]:
        """
        Get services by safety classification.

        Args:
            classification: Safety classification to filter by

        Returns:
            List of service names with the specified classification
        """
        return [name for name, cls in self._safety_classifications.items() if cls == classification]

    def get_safety_classification(self, service_name: str) -> SafetyClassification | None:
        """
        Get safety classification for a service.

        Args:
            service_name: Name of the service

        Returns:
            Safety classification or None if not a safety service
        """
        return self._safety_classifications.get(service_name)

    async def execute_emergency_stop(self, reason: str, triggered_by: str) -> dict[str, bool]:
        """
        Execute emergency stop on all safety-critical services.

        Args:
            reason: Reason for emergency stop
            triggered_by: Who/what triggered the emergency stop

        Returns:
            Dictionary mapping service names to success status
        """
        logger.critical(f"Executing emergency stop: {reason} (triggered by: {triggered_by})")

        results = {}
        critical_services = self.get_safety_critical_services()

        # Execute emergency stop in order of criticality
        # CRITICAL services first, then OPERATIONAL
        classification_order = [
            SafetyClassification.CRITICAL,
            SafetyClassification.OPERATIONAL,
        ]

        for classification in classification_order:
            services = self.get_services_by_safety_classification(classification)

            for service_name in services:
                if service_name not in critical_services:
                    continue

                try:
                    service = self.get_service(service_name)

                    if hasattr(service, "emergency_stop"):
                        logger.critical(f"Emergency stop: {service_name}")
                        await service.emergency_stop(reason)
                        results[service_name] = True
                    elif hasattr(service, "stop"):
                        logger.critical(f"Emergency stop (fallback): {service_name}")
                        await service.stop()
                        results[service_name] = True
                    else:
                        logger.warning(
                            f"Service {service_name} has no emergency_stop or stop method"
                        )
                        results[service_name] = False

                except Exception as e:
                    logger.error(f"Emergency stop failed for {service_name}: {e}")
                    results[service_name] = False

        logger.critical(f"Emergency stop completed. Results: {results}")
        return results

    async def get_safety_status_summary(self) -> dict[str, Any]:
        """
        Get comprehensive safety status across all services.

        Returns:
            Dictionary with safety status summary
        """
        status = {
            "critical_services": {},
            "safety_related_services": {},
            "position_critical_services": {},
            "operational_services": {},
            "overall_safety_status": SafetyStatus.SAFE.value,
            "summary": {
                "total_safety_services": len(self._safety_classifications),
                "critical_count": 0,
                "degraded_count": 0,
                "unsafe_count": 0,
                "emergency_stop_count": 0,
            },
        }

        worst_status = SafetyStatus.SAFE

        for service_name, classification in self._safety_classifications.items():
            try:
                service = self.get_service(service_name)

                # Get safety status
                if hasattr(service, "get_safety_status"):
                    svc_status = await service.get_safety_status()
                else:
                    # Fallback based on service registry status
                    reg_status = self.get_service_status(service_name)
                    if reg_status == "HEALTHY":
                        svc_status = SafetyStatus.SAFE
                    elif reg_status in ["DEGRADED"]:
                        svc_status = SafetyStatus.DEGRADED
                    else:
                        svc_status = SafetyStatus.UNSAFE

                # Categorize by classification
                classification_key = f"{classification.value}_services"
                if classification_key in status:
                    status[classification_key][service_name] = svc_status.value

                # Update summary counts
                if svc_status == SafetyStatus.EMERGENCY_STOP:
                    status["summary"]["emergency_stop_count"] += 1
                    worst_status = SafetyStatus.EMERGENCY_STOP
                elif svc_status == SafetyStatus.UNSAFE:
                    status["summary"]["unsafe_count"] += 1
                    if worst_status != SafetyStatus.EMERGENCY_STOP:
                        worst_status = SafetyStatus.UNSAFE
                elif svc_status == SafetyStatus.DEGRADED:
                    status["summary"]["degraded_count"] += 1
                    if worst_status == SafetyStatus.SAFE:
                        worst_status = SafetyStatus.DEGRADED

            except Exception as e:
                logger.error(f"Safety status check failed for {service_name}: {e}")
                status["critical_services"][service_name] = "unknown"
                status["summary"]["unsafe_count"] += 1
                worst_status = SafetyStatus.UNSAFE

        status["overall_safety_status"] = worst_status.value
        return status

    def get_safety_metadata(self, service_name: str) -> dict[str, Any] | None:
        """
        Get safety metadata for a service.

        Args:
            service_name: Name of the service

        Returns:
            Safety metadata dictionary or None
        """
        return self._safety_metadata.get(service_name)

    def list_safety_services(self) -> dict[str, dict[str, Any]]:
        """
        List all safety services with their classifications and metadata.

        Returns:
            Dictionary mapping service names to their safety information
        """
        result = {}

        for service_name, classification in self._safety_classifications.items():
            result[service_name] = {
                "classification": classification.value,
                "metadata": self._safety_metadata.get(service_name, {}),
                "status": self.get_service_status(service_name),
                "registered": self.has_service(service_name),
            }

        return result

    def _get_current_timestamp(self) -> str:
        """Get current timestamp for metadata."""
        from datetime import UTC, datetime

        return datetime.now(UTC).isoformat()
