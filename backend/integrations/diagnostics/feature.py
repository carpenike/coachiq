"""
Advanced Diagnostics Feature

Feature integration for the advanced diagnostics system following the
established feature management patterns.
"""

import asyncio
import logging
import time
from typing import Any

from backend.integrations.diagnostics.config import AdvancedDiagnosticsSettings
from backend.integrations.diagnostics.handler import DiagnosticHandler
from backend.integrations.diagnostics.models import (
    DTCSeverity,
    ProtocolType,
    SystemType,
)
from backend.integrations.diagnostics.predictive import PredictiveMaintenanceEngine
from backend.services.feature_base import Feature
from backend.services.feature_models import SafetyClassification

logger = logging.getLogger(__name__)


class AdvancedDiagnosticsFeature(Feature):
    """
    Advanced diagnostics feature providing comprehensive diagnostic capabilities
    across all RV protocols and systems.

    Integrates with existing RV-C, J1939, and OEM-specific diagnostic capabilities
    to provide unified fault analysis, correlation, and predictive maintenance.
    """

    def __init__(
        self,
        name: str = "advanced_diagnostics",
        enabled: bool = False,
        core: bool = False,
        config: dict[str, Any] | None = None,
        dependencies: list[str] | None = None,
        friendly_name: str | None = None,
        safety_classification: SafetyClassification | None = None,
        log_state_transitions: bool = True,
    ):
        """Initialize the advanced diagnostics feature."""
        super().__init__(
            name=name,
            enabled=enabled,
            core=core,
            config=config,
            dependencies=dependencies,
            friendly_name=friendly_name or "Advanced Diagnostics",
            safety_classification=safety_classification,
            log_state_transitions=log_state_transitions,
        )

        # Get settings internally
        from backend.core.config import get_settings

        settings = get_settings()

        # Store settings reference
        self.settings = settings

        # Get diagnostics-specific settings
        self.diag_settings = getattr(
            settings, "advanced_diagnostics", AdvancedDiagnosticsSettings()
        )

        # Initialize components
        self.handler: DiagnosticHandler | None = None
        self.predictive_engine: PredictiveMaintenanceEngine | None = None

        # Integration hooks
        self._protocol_integrations: dict[str, Any] = {}

        # Statistics
        self._stats = {
            "startup_time": 0.0,
            "dtcs_processed": 0,
            "predictions_generated": 0,
            "correlations_found": 0,
            "health_assessments": 0,
        }

    async def startup(self) -> None:
        """Initialize advanced diagnostics components."""
        if not self.diag_settings.enabled:
            logger.info("Advanced diagnostics feature disabled")
            return

        try:
            start_time = time.perf_counter()

            # Initialize diagnostic handler
            logger.info("Initializing diagnostic handler")
            self.handler = DiagnosticHandler(self.settings)
            await self.handler.startup()

            # Initialize predictive maintenance engine
            logger.info("Initializing predictive maintenance engine")
            self.predictive_engine = PredictiveMaintenanceEngine(self.diag_settings)

            # Set up protocol integrations
            await self._setup_protocol_integrations()

            startup_time = time.perf_counter() - start_time
            self._stats["startup_time"] = startup_time

            logger.info(f"Advanced diagnostics feature started successfully ({startup_time:.2f}s)")

        except Exception as e:
            logger.error(f"Failed to start advanced diagnostics feature: {e}")
            raise

    async def shutdown(self) -> None:
        """Shutdown advanced diagnostics components."""
        try:
            if self.handler:
                await self.handler.shutdown()
                self.handler = None

            self.predictive_engine = None
            self._protocol_integrations.clear()

            logger.info("Advanced diagnostics feature shutdown complete")

        except Exception as e:
            logger.error(f"Error during advanced diagnostics shutdown: {e}")

    def is_healthy(self) -> bool:
        """Check if the advanced diagnostics feature is healthy."""
        if not self.diag_settings.enabled:
            return True

        return self.handler is not None and self.predictive_engine is not None

    @property
    def health(self) -> str:
        """Get the health status of the feature as a string."""
        if not self.diag_settings.enabled:
            return "disabled"

        if self.is_healthy():
            return "healthy"
        return "unhealthy"

    def get_status(self) -> dict[str, Any]:
        """Get comprehensive status of the advanced diagnostics feature."""
        status = {
            "enabled": self.diag_settings.enabled,
            "healthy": self.is_healthy(),
            "components": {
                "diagnostic_handler": self.handler is not None,
                "predictive_engine": self.predictive_engine is not None,
            },
            "configuration": {
                "dtc_processing": self.diag_settings.enable_dtc_processing,
                "fault_correlation": self.diag_settings.enable_fault_correlation,
                "predictive_maintenance": self.diag_settings.enable_predictive_maintenance,
                "cross_protocol_analysis": self.diag_settings.enable_cross_protocol_analysis,
            },
            "statistics": self._stats.copy(),
        }

        if self.handler:
            status["diagnostic_statistics"] = self.handler.get_diagnostic_statistics()

        if self.predictive_engine:
            status["predictive_statistics"] = self.predictive_engine.get_prediction_statistics()

        return status

    # Public API methods for integration with other features

    def process_protocol_dtc(
        self,
        protocol: str,
        code: int,
        system_type: str,
        source_address: int = 0,
        pgn: int | None = None,
        dgn: int | None = None,
        raw_data: bytes | None = None,
        severity: str | None = None,
        description: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """
        Process a DTC from any protocol.

        Args:
            protocol: Protocol name (rvc, j1939, firefly, spartan_k2)
            code: DTC code number
            system_type: Affected system type
            source_address: CAN source address
            pgn: J1939 PGN (if applicable)
            dgn: RV-C DGN (if applicable)
            raw_data: Raw message data
            severity: Override severity classification
            description: Human-readable description
            metadata: Additional metadata

        Returns:
            Processed DTC information or None if processing failed
        """
        if not self.handler or not self.diag_settings.enable_dtc_processing:
            return None

        try:
            # Convert string parameters to enums
            protocol_enum = self._parse_protocol(protocol)
            system_type_enum = self._parse_system_type(system_type)
            severity_enum = self._parse_severity(severity) if severity else None

            # Process DTC
            dtc = self.handler.process_dtc(
                code=code,
                protocol=protocol_enum,
                system_type=system_type_enum,
                source_address=source_address,
                pgn=pgn,
                dgn=dgn,
                raw_data=raw_data,
                severity=severity_enum,
                description=description,
                metadata=metadata,
            )

            self._stats["dtcs_processed"] += 1

            return dtc.to_dict() if dtc else None

        except Exception as e:
            logger.error(f"Error processing DTC {code} from {protocol}: {e}")
            return None

    def record_performance_data(
        self,
        system_type: str,
        component_name: str,
        metrics: dict[str, float],
        timestamp: float | None = None,
    ) -> bool:
        """
        Record performance data for predictive analysis.

        Args:
            system_type: System type being measured
            component_name: Specific component name
            metrics: Performance metrics
            timestamp: Optional timestamp

        Returns:
            True if data was recorded successfully
        """
        if not self.predictive_engine:
            return False

        try:
            system_type_enum = self._parse_system_type(system_type)
            self.predictive_engine.record_performance_data(
                system_type_enum, component_name, metrics, timestamp
            )
            return True

        except Exception as e:
            logger.error(
                f"Error recording performance data for {system_type}.{component_name}: {e}"
            )
            return False

    def get_system_health(self, system_type: str | None = None) -> dict[str, Any]:
        """
        Get system health status.

        Args:
            system_type: Specific system to query, or None for all systems

        Returns:
            System health information
        """
        if not self.handler:
            return {}

        try:
            if system_type:
                system_type_enum = self._parse_system_type(system_type)
                return self.handler.get_system_health(system_type_enum)
            return self.handler.get_system_health()

        except Exception as e:
            logger.error(f"Error getting system health for {system_type}: {e}")
            return {}

    def get_maintenance_predictions(self, time_horizon_days: int = 90) -> list[dict[str, Any]]:
        """
        Get maintenance predictions for the specified time horizon.

        Args:
            time_horizon_days: Planning horizon in days

        Returns:
            List of maintenance predictions
        """
        if not self.predictive_engine:
            return []

        try:
            predictions = self.predictive_engine.get_maintenance_schedule(time_horizon_days)
            self._stats["predictions_generated"] += len(predictions)

            return [prediction.to_dict() for prediction in predictions]

        except Exception as e:
            logger.error(f"Error getting maintenance predictions: {e}")
            return []

    def get_fault_correlations(
        self, time_window_seconds: float | None = None
    ) -> list[dict[str, Any]]:
        """
        Get fault correlations within the specified time window.

        Args:
            time_window_seconds: Time window for correlation analysis

        Returns:
            List of fault correlations
        """
        if not self.handler:
            return []

        try:
            correlations = self.handler.get_fault_correlations(time_window_seconds)
            return [correlation.to_dict() for correlation in correlations]

        except Exception as e:
            logger.error(f"Error getting fault correlations: {e}")
            return []

    def resolve_dtc(self, protocol: str, code: int, source_address: int = 0) -> bool:
        """
        Mark a DTC as resolved.

        Args:
            protocol: Protocol name
            code: DTC code number
            source_address: CAN source address

        Returns:
            True if DTC was found and resolved
        """
        if not self.handler:
            return False

        try:
            protocol_enum = self._parse_protocol(protocol)
            return self.handler.resolve_dtc(code, protocol_enum, source_address)

        except Exception as e:
            logger.error(f"Error resolving DTC {code} from {protocol}: {e}")
            return False

    # Internal helper methods

    async def _setup_protocol_integrations(self) -> None:
        """Set up integrations with existing protocol features."""
        try:
            # This would typically register callbacks with RVC, J1939, etc. features
            # For now, we'll just track which integrations are available

            # Integration with protocol features now happens via ServiceRegistry
            # Mark all protocols as available for now
            for feature_name in ["rvc", "j1939", "firefly", "spartan_k2", "multi_network"]:
                self._protocol_integrations[feature_name] = True
                logger.debug(f"Advanced diagnostics integrated with {feature_name} feature")

        except Exception as e:
            logger.warning(f"Could not set up all protocol integrations: {e}")

    def _parse_protocol(self, protocol: str) -> ProtocolType:
        """Parse protocol string to enum."""
        protocol_map = {
            "rvc": ProtocolType.RVC,
            "j1939": ProtocolType.J1939,
            "firefly": ProtocolType.FIREFLY,
            "spartan_k2": ProtocolType.SPARTAN_K2,
            "proprietary": ProtocolType.PROPRIETARY,
        }

        return protocol_map.get(protocol.lower(), ProtocolType.UNKNOWN)

    def _parse_system_type(self, system_type: str) -> SystemType:
        """Parse system type string to enum."""
        try:
            return SystemType(system_type.lower())
        except ValueError:
            return SystemType.UNKNOWN

    def _parse_severity(self, severity: str) -> DTCSeverity:
        """Parse severity string to enum."""
        severity_map = {
            "critical": DTCSeverity.CRITICAL,
            "high": DTCSeverity.HIGH,
            "medium": DTCSeverity.MEDIUM,
            "low": DTCSeverity.LOW,
            "info": DTCSeverity.INFORMATIONAL,
            "informational": DTCSeverity.INFORMATIONAL,
        }

        return severity_map.get(severity.lower(), DTCSeverity.MEDIUM)
