"""Feature wrapper for advanced diagnostics components."""

from typing import Any

from backend.core.config import Settings
from backend.integrations.diagnostics.config import AdvancedDiagnosticsSettings
from backend.integrations.diagnostics.handler import DiagnosticHandler
from backend.integrations.diagnostics.models import ProtocolType, SystemType
from backend.integrations.diagnostics.predictive import PredictiveMaintenanceEngine


class AdvancedDiagnosticsFeature:
    """Lifecycle wrapper for diagnostic handler and predictive maintenance engine."""

    def __init__(self, settings: Settings):
        """Initialize the diagnostics feature from application settings."""
        self.settings = settings
        self.diag_settings = getattr(
            settings, "advanced_diagnostics", AdvancedDiagnosticsSettings()
        )
        self.handler: DiagnosticHandler | None = None
        self.predictive_engine: PredictiveMaintenanceEngine | None = None

    async def startup(self) -> None:
        """Start diagnostics components when enabled."""
        if not self.diag_settings.enabled:
            return

        self.handler = DiagnosticHandler(self.settings)
        await self.handler.startup()
        self.predictive_engine = PredictiveMaintenanceEngine(self.diag_settings)

    async def shutdown(self) -> None:
        """Stop diagnostics components."""
        if self.handler is not None:
            await self.handler.shutdown()
        self.handler = None
        self.predictive_engine = None

    def is_healthy(self) -> bool:
        """Return whether the feature is healthy."""
        return True

    def process_protocol_dtc(
        self,
        protocol: str,
        code: int,
        system_type: str,
        description: str = "",
        **metadata: Any,
    ) -> dict[str, Any] | None:
        """Process a DTC through the diagnostic handler."""
        if not self.diag_settings.enable_dtc_processing or self.handler is None:
            return None

        dtc = self.handler.process_dtc(
            code=code,
            protocol=ProtocolType(protocol),
            system_type=SystemType(system_type),
            description=description,
            metadata=metadata,
        )
        return dtc.to_dict()

    def record_performance_data(
        self, system_type: str, component_name: str, metrics: dict[str, float]
    ) -> bool:
        """Record performance metrics for predictive diagnostics."""
        if self.predictive_engine is None:
            return False

        self.predictive_engine.record_performance_data(
            SystemType(system_type), component_name, metrics
        )
        return True

    def get_system_health(self, system_type: str | None = None) -> dict[str, Any]:
        """Get system health from the diagnostic handler."""
        if self.handler is None:
            return {}
        return self.handler.get_system_health(SystemType(system_type) if system_type else None)

    def get_maintenance_predictions(self, time_horizon_days: int = 90) -> list[dict[str, Any]]:
        """Get maintenance predictions from the predictive engine."""
        if self.predictive_engine is None:
            return []
        predictions = self.predictive_engine.get_maintenance_schedule(time_horizon_days)
        return [prediction.to_dict() for prediction in predictions]

    def get_status(self) -> dict[str, Any]:
        """Get feature component status and statistics."""
        status: dict[str, Any] = {
            "enabled": self.diag_settings.enabled,
            "healthy": self.is_healthy(),
            "components": {
                "diagnostic_handler": self.handler is not None,
                "predictive_engine": self.predictive_engine is not None,
            },
        }
        if self.handler is not None:
            status["diagnostic_statistics"] = self.handler.get_diagnostic_statistics()
        if self.predictive_engine is not None:
            status["predictive_statistics"] = self.predictive_engine.get_prediction_statistics()
        return status
