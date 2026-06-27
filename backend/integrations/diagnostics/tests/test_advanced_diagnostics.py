"""
Advanced Diagnostics Tests

Comprehensive tests for the advanced diagnostics system including
fault correlation, predictive maintenance, and cross-protocol analysis.
"""

import time
from unittest.mock import Mock, patch

import pytest

from backend.core.config import Settings
from backend.integrations.diagnostics.config import AdvancedDiagnosticsSettings
from backend.integrations.diagnostics.feature import AdvancedDiagnosticsFeature
from backend.integrations.diagnostics.handler import DiagnosticHandler
from backend.integrations.diagnostics.models import (
    DiagnosticTroubleCode,
    DTCSeverity,
    MaintenanceUrgency,
    ProtocolType,
    SystemType,
)
from backend.integrations.diagnostics.predictive import PredictiveMaintenanceEngine


@pytest.fixture
def diagnostics_settings():
    """Create diagnostics settings for testing."""
    return AdvancedDiagnosticsSettings(
        enabled=True,
        enable_dtc_processing=True,
        enable_fault_correlation=True,
        enable_predictive_maintenance=True,
        correlation_time_window_seconds=10.0,
        health_assessment_interval_seconds=30.0,  # Must be >= 30
        prediction_confidence_threshold=0.5,
        trend_analysis_minimum_samples=3,
    )


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""
    settings = Mock(spec=Settings)
    settings.advanced_diagnostics = AdvancedDiagnosticsSettings(
        enabled=True,
        enable_dtc_processing=True,
        enable_fault_correlation=True,
        enable_predictive_maintenance=True,
    )
    return settings


@pytest.fixture
def diagnostic_handler(mock_settings: Settings) -> DiagnosticHandler:
    """Create diagnostic handler for testing."""
    return DiagnosticHandler(mock_settings)


@pytest.fixture
def predictive_engine(diagnostics_settings):
    """Create predictive maintenance engine for testing."""
    return PredictiveMaintenanceEngine(diagnostics_settings)


@pytest.fixture
def advanced_diagnostics_feature(mock_settings):
    """Create advanced diagnostics feature for testing."""
    return AdvancedDiagnosticsFeature(mock_settings)


class TestAdvancedDiagnosticsSettings:
    """Test advanced diagnostics configuration."""

    def test_default_settings(self):
        """Test default settings values."""
        settings = AdvancedDiagnosticsSettings()

        assert settings.enabled is False
        assert settings.enable_dtc_processing is True
        assert settings.enable_fault_correlation is True
        assert settings.enable_predictive_maintenance is True
        assert settings.correlation_time_window_seconds == 60.0
        assert settings.dtc_retention_days == 90
        assert settings.prediction_confidence_threshold == 0.7

    def test_environment_variable_override(self):
        """Test environment variable configuration override."""
        with patch.dict(
            "os.environ",
            {
                "COACHIQ_ADVANCED_DIAGNOSTICS__ENABLED": "true",
                "COACHIQ_ADVANCED_DIAGNOSTICS__CORRELATION_TIME_WINDOW_SECONDS": "120.0",
                "COACHIQ_ADVANCED_DIAGNOSTICS__DTC_RETENTION_DAYS": "180",
            },
        ):
            settings = AdvancedDiagnosticsSettings()

            assert settings.enabled is True
            assert settings.correlation_time_window_seconds == 120.0
            assert settings.dtc_retention_days == 180


class TestDiagnosticHandler:
    """Test diagnostic handler functionality."""

    def test_handler_initialization(self, diagnostic_handler):
        """Test handler initializes correctly."""
        assert diagnostic_handler is not None
        assert diagnostic_handler._active_dtcs == {}
        assert len(diagnostic_handler._system_health) > 0

        # Check that all system types have health status initialized
        for system_type in SystemType:
            if system_type != SystemType.UNKNOWN:
                assert system_type in diagnostic_handler._system_health

    def test_process_dtc_new(self, diagnostic_handler):
        """Test processing a new DTC."""
        dtc = diagnostic_handler.process_dtc(
            code=1234,
            protocol=ProtocolType.RVC,
            system_type=SystemType.LIGHTING,
            source_address=23,
            dgn=130778,
            description="Test lighting fault",
        )

        assert dtc is not None
        assert dtc.code == 1234
        assert dtc.protocol == ProtocolType.RVC
        assert dtc.system_type == SystemType.LIGHTING
        assert dtc.source_address == 23
        assert dtc.dgn == 130778
        assert dtc.active is True
        assert dtc.occurrence_count == 1

        # Check it was stored
        dtc_key = (1234, ProtocolType.RVC, 23)
        assert dtc_key in diagnostic_handler._active_dtcs

    def test_process_dtc_existing(self, diagnostic_handler):
        """Test processing an existing DTC updates occurrence count."""
        # Process same DTC twice
        dtc1 = diagnostic_handler.process_dtc(
            code=1234, protocol=ProtocolType.RVC, system_type=SystemType.LIGHTING, source_address=23
        )

        dtc2 = diagnostic_handler.process_dtc(
            code=1234, protocol=ProtocolType.RVC, system_type=SystemType.LIGHTING, source_address=23
        )

        assert dtc1 is dtc2  # Should be the same object
        assert dtc2.occurrence_count == 2
        assert dtc2.intermittent is True

    def test_resolve_dtc(self, diagnostic_handler):
        """Test resolving a DTC."""
        # Create DTC
        diagnostic_handler.process_dtc(
            code=1234, protocol=ProtocolType.RVC, system_type=SystemType.LIGHTING, source_address=23
        )

        # Resolve it
        resolved = diagnostic_handler.resolve_dtc(1234, ProtocolType.RVC, 23)

        assert resolved is True

        # Should be moved to historical storage
        dtc_key = (1234, ProtocolType.RVC, 23)
        assert dtc_key not in diagnostic_handler._active_dtcs
        assert len(diagnostic_handler._historical_dtcs) == 1

        historical_dtc = diagnostic_handler._historical_dtcs[0]
        assert historical_dtc.resolved is True
        assert historical_dtc.active is False

    def test_get_active_dtcs_filtering(self, diagnostic_handler):
        """Test filtering active DTCs."""
        # Create DTCs for different systems and severities
        diagnostic_handler.process_dtc(
            code=1001,
            protocol=ProtocolType.RVC,
            system_type=SystemType.LIGHTING,
            severity=DTCSeverity.HIGH,
        )
        diagnostic_handler.process_dtc(
            code=1002,
            protocol=ProtocolType.J1939,
            system_type=SystemType.ENGINE,
            severity=DTCSeverity.CRITICAL,
        )
        diagnostic_handler.process_dtc(
            code=1003,
            protocol=ProtocolType.RVC,
            system_type=SystemType.LIGHTING,
            severity=DTCSeverity.LOW,
        )

        # Test system filtering
        lighting_dtcs = diagnostic_handler.get_active_dtcs(system_type=SystemType.LIGHTING)
        assert len(lighting_dtcs) == 2
        assert all(dtc.system_type == SystemType.LIGHTING for dtc in lighting_dtcs)

        # Test severity filtering
        critical_dtcs = diagnostic_handler.get_active_dtcs(severity=DTCSeverity.CRITICAL)
        assert len(critical_dtcs) == 1
        assert critical_dtcs[0].severity == DTCSeverity.CRITICAL

        # Test protocol filtering
        rvc_dtcs = diagnostic_handler.get_active_dtcs(protocol=ProtocolType.RVC)
        assert len(rvc_dtcs) == 2
        assert all(dtc.protocol == ProtocolType.RVC for dtc in rvc_dtcs)

    def test_system_health_tracking(self, diagnostic_handler):
        """Test system health score calculation."""
        # Initial health should be perfect
        health = diagnostic_handler.get_system_health(SystemType.ENGINE)
        assert health["health_score"] == 1.0
        assert health["status"] == "excellent"

        # Add a critical DTC
        diagnostic_handler.process_dtc(
            code=2001,
            protocol=ProtocolType.J1939,
            system_type=SystemType.ENGINE,
            severity=DTCSeverity.CRITICAL,
        )

        # Health should decrease
        health = diagnostic_handler.get_system_health(SystemType.ENGINE)
        assert health["health_score"] < 1.0
        assert len(health["active_dtcs"]) == 1

    def test_diagnostic_statistics(self, diagnostic_handler):
        """Test diagnostic statistics collection."""
        # Add some DTCs
        diagnostic_handler.process_dtc(1001, ProtocolType.RVC, SystemType.LIGHTING)
        diagnostic_handler.process_dtc(1002, ProtocolType.J1939, SystemType.ENGINE)

        stats = diagnostic_handler.get_diagnostic_statistics()

        assert stats["active_dtcs"] == 2
        assert stats["historical_dtcs"] == 0
        assert stats["processing_stats"]["dtcs_processed"] == 2
        assert "system_health_scores" in stats


class TestPredictiveMaintenanceEngine:
    """Test predictive maintenance functionality."""

    def test_engine_initialization(self, predictive_engine):
        """Test engine initializes correctly."""
        assert predictive_engine is not None
        assert len(predictive_engine._performance_history) == 0
        assert len(predictive_engine._component_health) == 0

    def test_record_performance_data(self, predictive_engine):
        """Test recording performance data."""
        metrics = {"temperature": 85.0, "pressure": 35.0, "vibration": 2.1}

        predictive_engine.record_performance_data(SystemType.ENGINE, "oil_pump", metrics)

        assert len(predictive_engine._performance_history[SystemType.ENGINE]) == 1
        assert "engine_oil_pump" in predictive_engine._component_health

        health_data = predictive_engine._component_health["engine_oil_pump"]
        assert health_data["total_measurements"] == 1
        assert "temperature" in health_data["baseline_metrics"]

    def test_component_wear_analysis_insufficient_data(self, predictive_engine):
        """Test wear analysis with insufficient data."""
        # Record only 1 data point
        predictive_engine.record_performance_data(
            SystemType.ENGINE, "oil_pump", {"temperature": 85.0}
        )

        analysis = predictive_engine.analyze_component_wear(SystemType.ENGINE, "oil_pump")

        assert analysis["status"] == "insufficient_data"
        assert analysis["measurements"] == 1

    def test_component_wear_analysis_with_data(self, predictive_engine):
        """Test wear analysis with sufficient data."""
        # Record baseline data
        for i in range(5):
            predictive_engine.record_performance_data(
                SystemType.ENGINE, "oil_pump", {"temperature": 80.0 + i}
            )

        # Record more data showing degradation
        for i in range(10):
            predictive_engine.record_performance_data(
                SystemType.ENGINE, "oil_pump", {"temperature": 90.0 + i * 0.5}
            )

        analysis = predictive_engine.analyze_component_wear(SystemType.ENGINE, "oil_pump")

        assert "status" not in analysis or analysis["status"] != "insufficient_data"
        assert analysis["component"] == "oil_pump"
        assert analysis["data_points"] >= 15
        assert "trends" in analysis
        assert "temperature" in analysis["trends"]

    def test_failure_probability_prediction(self, predictive_engine):
        """Test failure probability prediction."""
        # Set up component with degrading performance
        for i in range(10):
            # Simulate increasing temperature trend
            temp = 80.0 + i * 2.0  # Temperature rising from 80 to 98
            predictive_engine.record_performance_data(
                SystemType.ENGINE, "coolant_pump", {"temperature": temp}
            )

        prediction = predictive_engine.predict_failure_probability(
            SystemType.ENGINE, "coolant_pump", 30
        )

        assert prediction.system_type == SystemType.ENGINE
        assert prediction.component_name == "coolant_pump"
        assert prediction.confidence >= 0.0
        assert prediction.urgency in list(MaintenanceUrgency)

    def test_maintenance_schedule_generation(self, predictive_engine):
        """Test maintenance schedule generation."""
        # Set up multiple components
        components = ["oil_pump", "coolant_pump", "fuel_pump"]

        for component in components:
            for i in range(10):
                # Simulate different degradation rates
                degradation = i * (1.0 if component == "oil_pump" else 2.0)
                temp = 80.0 + degradation

                predictive_engine.record_performance_data(
                    SystemType.ENGINE, component, {"temperature": temp}
                )

        schedule = predictive_engine.get_maintenance_schedule(90)

        # Should return predictions for components with sufficient confidence
        assert isinstance(schedule, list)
        # All predictions should be sorted by urgency
        if len(schedule) > 1:
            urgency_order = [pred.urgency for pred in schedule]
            # Check that it's sorted (IMMEDIATE < URGENT < SOON < SCHEDULED < MONITOR)
            urgency_values = {
                MaintenanceUrgency.IMMEDIATE: 0,
                MaintenanceUrgency.URGENT: 1,
                MaintenanceUrgency.SOON: 2,
                MaintenanceUrgency.SCHEDULED: 3,
                MaintenanceUrgency.MONITOR: 4,
            }
            values = [urgency_values[urgency] for urgency in urgency_order]
            assert values == sorted(values)

    def test_prediction_statistics(self, predictive_engine):
        """Test prediction statistics collection."""
        # Add some data
        predictive_engine.record_performance_data(
            SystemType.ENGINE, "test_component", {"temperature": 85.0}
        )

        stats = predictive_engine.get_prediction_statistics()

        assert stats["total_components_tracked"] == 1
        assert stats["components_with_sufficient_data"] == 0  # Not enough data yet
        assert stats["performance_data_points"] == 1


class TestAdvancedDiagnosticsFeature:
    """Test advanced diagnostics feature integration."""

    @pytest.mark.asyncio
    async def test_feature_startup_disabled(self, mock_settings):
        """Test feature startup when disabled."""
        mock_settings.advanced_diagnostics.enabled = False
        feature = AdvancedDiagnosticsFeature(mock_settings)

        await feature.startup()

        assert feature.handler is None
        assert feature.predictive_engine is None
        assert feature.is_healthy() is True  # Should be healthy when disabled

    @pytest.mark.asyncio
    async def test_feature_startup_enabled(self, mock_settings):
        """Test feature startup when enabled."""
        mock_settings.advanced_diagnostics.enabled = True
        feature = AdvancedDiagnosticsFeature(mock_settings)

        await feature.startup()

        assert feature.handler is not None
        assert feature.predictive_engine is not None
        assert feature.is_healthy() is True

        # Cleanup
        await feature.shutdown()

    def test_process_protocol_dtc(self, advanced_diagnostics_feature):
        """Test processing DTC through feature API."""
        # Mock the handler
        advanced_diagnostics_feature.handler = Mock()
        advanced_diagnostics_feature.diag_settings.enable_dtc_processing = True

        mock_dtc = Mock()
        mock_dtc.to_dict.return_value = {"code": 1234, "protocol": "rvc"}
        advanced_diagnostics_feature.handler.process_dtc.return_value = mock_dtc

        result = advanced_diagnostics_feature.process_protocol_dtc(
            protocol="rvc", code=1234, system_type="lighting", description="Test fault"
        )

        assert result is not None
        assert result["code"] == 1234
        assert result["protocol"] == "rvc"

        # Verify handler was called correctly
        advanced_diagnostics_feature.handler.process_dtc.assert_called_once()

    def test_record_performance_data_api(self, advanced_diagnostics_feature):
        """Test recording performance data through feature API."""
        # Mock the predictive engine
        advanced_diagnostics_feature.predictive_engine = Mock()

        result = advanced_diagnostics_feature.record_performance_data(
            system_type="engine", component_name="oil_pump", metrics={"temperature": 85.0}
        )

        assert result is True
        advanced_diagnostics_feature.predictive_engine.record_performance_data.assert_called_once()

    def test_get_system_health_api(self, advanced_diagnostics_feature):
        """Test getting system health through feature API."""
        # Mock the handler
        advanced_diagnostics_feature.handler = Mock()
        advanced_diagnostics_feature.handler.get_system_health.return_value = {
            "health_score": 0.95,
            "status": "excellent",
        }

        result = advanced_diagnostics_feature.get_system_health("engine")

        assert result["health_score"] == 0.95
        assert result["status"] == "excellent"

    def test_get_maintenance_predictions_api(self, advanced_diagnostics_feature):
        """Test getting maintenance predictions through feature API."""
        # Mock the predictive engine
        advanced_diagnostics_feature.predictive_engine = Mock()

        mock_prediction = Mock()
        mock_prediction.to_dict.return_value = {
            "component_name": "oil_pump",
            "urgency": "soon",
            "confidence": 0.75,
        }
        advanced_diagnostics_feature.predictive_engine.get_maintenance_schedule.return_value = [
            mock_prediction
        ]

        result = advanced_diagnostics_feature.get_maintenance_predictions(30)

        assert len(result) == 1
        assert result[0]["component_name"] == "oil_pump"
        assert result[0]["urgency"] == "soon"

    def test_feature_status(self, advanced_diagnostics_feature):
        """Test feature status reporting."""
        # Mock components
        advanced_diagnostics_feature.handler = Mock()
        advanced_diagnostics_feature.predictive_engine = Mock()
        advanced_diagnostics_feature.handler.get_diagnostic_statistics.return_value = {
            "active_dtcs": 5,
            "processing_stats": {"dtcs_processed": 100},
        }
        advanced_diagnostics_feature.predictive_engine.get_prediction_statistics.return_value = {
            "total_components_tracked": 10,
            "active_predictions": 3,
        }

        status = advanced_diagnostics_feature.get_status()

        assert status["enabled"] is True
        assert status["healthy"] is True
        assert status["components"]["diagnostic_handler"] is True
        assert status["components"]["predictive_engine"] is True
        assert "diagnostic_statistics" in status
        assert "predictive_statistics" in status


class TestDiagnosticModels:
    """Test diagnostic data models."""

    def test_dtc_creation(self):
        """Test DTC creation and methods."""
        dtc = DiagnosticTroubleCode(
            code=1234,
            protocol=ProtocolType.RVC,
            system_type=SystemType.LIGHTING,
            severity=DTCSeverity.HIGH,
            description="Test lighting fault",
        )

        assert dtc.code == 1234
        assert dtc.protocol == ProtocolType.RVC
        assert dtc.system_type == SystemType.LIGHTING
        assert dtc.severity == DTCSeverity.HIGH
        assert dtc.active is True
        assert dtc.occurrence_count == 1

    def test_dtc_update_occurrence(self):
        """Test DTC occurrence tracking."""
        dtc = DiagnosticTroubleCode(
            code=1234,
            protocol=ProtocolType.RVC,
            system_type=SystemType.LIGHTING,
            severity=DTCSeverity.HIGH,
        )

        original_time = dtc.last_occurrence
        time.sleep(0.01)  # Small delay

        dtc.update_occurrence()

        assert dtc.occurrence_count == 2
        assert dtc.intermittent is True
        assert dtc.last_occurrence > original_time

    def test_dtc_resolve(self):
        """Test DTC resolution."""
        dtc = DiagnosticTroubleCode(
            code=1234,
            protocol=ProtocolType.RVC,
            system_type=SystemType.LIGHTING,
            severity=DTCSeverity.HIGH,
        )

        dtc.resolve()

        assert dtc.resolved is True
        assert dtc.active is False

    def test_dtc_serialization(self):
        """Test DTC serialization to dictionary."""
        dtc = DiagnosticTroubleCode(
            code=1234,
            protocol=ProtocolType.RVC,
            system_type=SystemType.LIGHTING,
            severity=DTCSeverity.HIGH,
            description="Test fault",
            source_address=23,
            dgn=130778,
        )

        data = dtc.to_dict()

        assert data["code"] == 1234
        assert data["protocol"] == "rvc"
        assert data["system_type"] == "lighting"
        assert data["severity"] == "high"
        assert data["description"] == "Test fault"
        assert data["source_address"] == 23
        assert data["dgn"] == 130778
        assert data["active"] is True
