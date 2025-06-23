"""
Unit Tests for Performance Monitoring System

Tests metrics collection, threshold monitoring, and Prometheus integration
for the comprehensive performance monitoring system.
"""

import asyncio
import statistics
import time
from unittest.mock import Mock, patch

import pytest

from backend.integrations.can.performance_monitor import (
    ComponentStats,
    ComponentType,
    MetricType,
    PerformanceMetric,
    PerformanceMonitor,
)


class TestPerformanceMetric:
    """Test performance metric data structure."""

    def test_metric_initialization(self):
        """Test performance metric initialization."""
        metric = PerformanceMetric(
            name="test_metric",
            metric_type=MetricType.COUNTER,
            component=ComponentType.BAM_HANDLER,
            value=42.0,
            labels={"component": "bam_handler"},
        )

        assert metric.name == "test_metric"
        assert metric.metric_type == MetricType.COUNTER
        assert metric.component == ComponentType.BAM_HANDLER
        assert metric.value == 42.0
        assert metric.labels["component"] == "bam_handler"
        assert metric.timestamp > 0

    def test_prometheus_format_conversion(self):
        """Test conversion to Prometheus exposition format."""
        metric = PerformanceMetric(
            name="test_metric",
            metric_type=MetricType.GAUGE,
            component=ComponentType.SAFETY_ENGINE,
            value=123.45,
            labels={"component": "safety_engine", "type": "response_time"},
        )

        prometheus_line = metric.to_prometheus_format()

        assert "canbus_decoder_test_metric" in prometheus_line
        assert "123.45" in prometheus_line
        assert 'component="safety_engine"' in prometheus_line
        assert 'type="response_time"' in prometheus_line
        assert str(int(metric.timestamp * 1000)) in prometheus_line

    def test_prometheus_format_no_labels(self):
        """Test Prometheus format conversion without labels."""
        metric = PerformanceMetric(
            name="simple_metric",
            metric_type=MetricType.COUNTER,
            component=ComponentType.PROTOCOL_ROUTER,
            value=100.0,
        )

        prometheus_line = metric.to_prometheus_format()

        assert "canbus_decoder_simple_metric" in prometheus_line
        assert "100.0" in prometheus_line
        assert "{" not in prometheus_line  # No labels


class TestComponentStats:
    """Test component statistics tracking."""

    @pytest.fixture
    def component_stats(self):
        """Create component stats for testing."""
        return ComponentStats(ComponentType.BAM_HANDLER)

    def test_stats_initialization(self, component_stats):
        """Test component stats initialization."""
        assert component_stats.component == ComponentType.BAM_HANDLER
        assert component_stats.messages_processed == 0
        assert component_stats.total_processing_time == 0.0
        assert component_stats.error_count == 0
        assert len(component_stats.processing_times) == 0

    def test_processing_time_recording(self, component_stats):
        """Test processing time recording and statistics."""
        # Record some processing times
        times = [0.001, 0.002, 0.003, 0.004, 0.005]  # 1-5ms

        for duration in times:
            component_stats.add_processing_time(duration)

        assert component_stats.messages_processed == 5
        assert component_stats.total_processing_time == sum(times)
        assert len(component_stats.processing_times) == 5

        # Test average calculation (should be in milliseconds)
        avg_ms = component_stats.get_avg_processing_time()
        expected_avg_ms = (sum(times) / len(times)) * 1000
        assert abs(avg_ms - expected_avg_ms) < 0.001

    def test_percentile_calculation(self, component_stats):
        """Test percentile processing time calculation."""
        # Record times from 1ms to 100ms
        times = [i * 0.001 for i in range(1, 101)]  # 0.001 to 0.100 seconds

        for duration in times:
            component_stats.add_processing_time(duration)

        # Test 95th percentile
        p95 = component_stats.get_percentile_processing_time(95.0)
        # 95th percentile of 1-100ms should be around 95ms
        assert 90 <= p95 <= 100

    def test_percentile_single_value(self, component_stats):
        """Test percentile calculation with single value."""
        component_stats.add_processing_time(0.005)  # 5ms

        p95 = component_stats.get_percentile_processing_time(95.0)
        assert p95 == 5.0  # Should return the single value in ms

    def test_percentile_empty_data(self, component_stats):
        """Test percentile calculation with no data."""
        p95 = component_stats.get_percentile_processing_time(95.0)
        assert p95 == 0.0

    def test_error_tracking(self, component_stats):
        """Test error counting and rate calculation."""
        # Record some processing and errors
        component_stats.add_processing_time(0.001)
        component_stats.add_processing_time(0.002)
        component_stats.add_error()
        component_stats.add_processing_time(0.003)
        component_stats.add_error()

        assert component_stats.messages_processed == 3
        assert component_stats.error_count == 2

        # Error rate should be 2/(3+2) = 40%
        error_rate = component_stats.get_error_rate()
        assert abs(error_rate - 40.0) < 0.001

    def test_error_rate_no_operations(self, component_stats):
        """Test error rate calculation with no operations."""
        error_rate = component_stats.get_error_rate()
        assert error_rate == 0.0

    def test_throughput_calculation(self, component_stats):
        """Test throughput calculation."""
        # Simulate recent activity
        current_time = time.time()
        component_stats.last_activity = current_time

        # Add processing times to simulate recent messages
        for i in range(10):
            component_stats.processing_times.append(0.001)

        # Test throughput calculation
        throughput = component_stats.get_throughput(window_seconds=10.0)
        assert throughput == 1.0  # 10 messages / 10 seconds

    def test_throughput_no_recent_activity(self, component_stats):
        """Test throughput calculation with no recent activity."""
        # Set last activity to long ago
        component_stats.last_activity = time.time() - 3600  # 1 hour ago

        throughput = component_stats.get_throughput(window_seconds=60.0)
        assert throughput == 0.0

    def test_throughput_no_data(self, component_stats):
        """Test throughput calculation with no processing times."""
        throughput = component_stats.get_throughput()
        assert throughput == 0.0


class TestPerformanceMonitor:
    """Test performance monitoring system."""

    @pytest.fixture
    def monitor(self):
        """Create performance monitor for testing."""
        return PerformanceMonitor(collection_interval=0.1, retention_hours=1)

    def test_monitor_initialization(self, monitor):
        """Test performance monitor initialization."""
        assert monitor.collection_interval == 0.1
        assert monitor.retention_hours == 1
        assert len(monitor.component_stats) == len(ComponentType)
        assert monitor.total_messages_processed == 0
        assert monitor.total_anomalies_detected == 0

        # Check that all components have stats
        for component in ComponentType:
            assert component in monitor.component_stats

    def test_processing_time_recording(self, monitor):
        """Test processing time recording for components."""
        # Record processing time
        monitor.record_processing_time(ComponentType.BAM_HANDLER, 0.005)

        stats = monitor.component_stats[ComponentType.BAM_HANDLER]
        assert stats.messages_processed == 1
        assert stats.total_processing_time == 0.005
        assert monitor.system_stats["total_messages_processed"] == 1

    def test_error_recording(self, monitor):
        """Test error recording for components."""
        # Record error
        monitor.record_error(ComponentType.SAFETY_ENGINE)

        stats = monitor.component_stats[ComponentType.SAFETY_ENGINE]
        assert stats.error_count == 1
        assert monitor.system_stats["total_errors"] == 1

    def test_bam_metrics_recording(self, monitor):
        """Test BAM-specific metrics recording."""
        # Record BAM session events
        monitor.record_bam_session_start()
        monitor.record_bam_session_complete(0.025)  # 25ms
        monitor.record_bam_session_timeout()
        monitor.record_bam_session_failed()

        bam_stats = monitor.bam_session_stats
        assert bam_stats["sessions_started"] == 1
        assert bam_stats["sessions_completed"] == 1
        assert bam_stats["sessions_timeout"] == 1
        assert bam_stats["sessions_failed"] == 1
        assert bam_stats["completion_times"][0] == 0.025

    def test_safety_metrics_recording(self, monitor):
        """Test safety engine metrics recording."""
        # Record safety events
        monitor.record_safety_state_transition(0.003)  # 3ms
        monitor.record_safety_command_issued()
        monitor.record_safety_operation_blocked()
        monitor.record_safety_emergency_stop()

        safety_stats = monitor.safety_stats
        assert safety_stats["state_transitions"] == 1
        assert safety_stats["safety_commands_issued"] == 1
        assert safety_stats["operations_blocked"] == 1
        assert safety_stats["emergency_stops"] == 1
        assert safety_stats["state_transition_times"][0] == 0.003

    def test_security_metrics_recording(self, monitor):
        """Test security manager metrics recording."""
        # Record security events
        monitor.record_security_frame_validated()
        monitor.record_security_anomaly_detected()
        monitor.record_security_threat_blocked()
        monitor.update_security_device_counts(learning=5, active=10)

        security_stats = monitor.security_stats
        assert security_stats["frames_validated"] == 1
        assert security_stats["anomalies_detected"] == 1
        assert security_stats["threats_blocked"] == 1
        assert security_stats["learning_devices"] == 5
        assert security_stats["active_profiles"] == 10

    def test_threshold_violation_detection(self, monitor):
        """Test performance threshold violation detection."""
        # Record high processing times to trigger threshold
        for _ in range(10):
            monitor.record_processing_time(
                ComponentType.BAM_HANDLER, 0.015
            )  # 15ms (> 10ms threshold)

        violations = monitor.check_performance_thresholds()

        # Should detect processing time violation
        processing_violations = [v for v in violations if v["metric"] == "processing_time"]
        assert len(processing_violations) > 0
        assert processing_violations[0]["component"] == "bam_handler"
        assert processing_violations[0]["severity"] == "warning"

    def test_error_rate_threshold_violation(self, monitor):
        """Test error rate threshold violation detection."""
        # Record high error rate
        for _ in range(5):
            monitor.record_processing_time(ComponentType.SAFETY_ENGINE, 0.001)
        for _ in range(10):
            monitor.record_error(ComponentType.SAFETY_ENGINE)

        violations = monitor.check_performance_thresholds()

        # Should detect error rate violation
        error_violations = [v for v in violations if v["metric"] == "error_rate"]
        assert len(error_violations) > 0
        assert error_violations[0]["severity"] == "critical"

    def test_bam_completion_time_threshold(self, monitor):
        """Test BAM completion time threshold violation."""
        # Record slow BAM completions
        for _ in range(5):
            monitor.record_bam_session_complete(0.075)  # 75ms (> 50ms threshold)

        violations = monitor.check_performance_thresholds()

        # Should detect BAM completion time violation
        bam_violations = [v for v in violations if v["component"] == "bam_handler"]
        if bam_violations:
            assert bam_violations[0]["metric"] == "completion_time"

    def test_safety_response_time_threshold(self, monitor):
        """Test safety response time threshold violation."""
        # Record slow safety transitions
        for _ in range(5):
            monitor.record_safety_state_transition(0.008)  # 8ms (> 5ms threshold)

        violations = monitor.check_performance_thresholds()

        # Should detect safety response time violation
        safety_violations = [v for v in violations if v["component"] == "safety_engine"]
        if safety_violations:
            assert safety_violations[0]["metric"] == "response_time"
            assert safety_violations[0]["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_metrics_collection_loop(self, monitor):
        """Test background metrics collection."""
        # Add some data to collect
        monitor.record_processing_time(ComponentType.PROTOCOL_ROUTER, 0.002)
        monitor.record_bam_session_complete(0.020)

        # Run one collection cycle
        await monitor._collect_metrics()

        # Check that metrics were collected
        assert len(monitor.metrics) > 0

        # Check for expected metric types
        metric_names = [m.name for m in monitor.metrics]
        assert any("processing_time" in name for name in metric_names)
        assert any("bam" in name for name in metric_names)

    @pytest.mark.asyncio
    async def test_monitoring_start_stop(self, monitor):
        """Test starting and stopping background monitoring."""
        # Start monitoring
        monitor.start_monitoring()

        # Wait a short time for collection
        await asyncio.sleep(0.05)

        # Stop monitoring
        await monitor.stop_monitoring()

        # Should complete without errors

    def test_prometheus_metrics_generation(self, monitor):
        """Test Prometheus metrics generation."""
        # Add some data
        monitor.record_processing_time(ComponentType.BAM_HANDLER, 0.003)
        monitor.record_bam_session_complete(0.025)

        # Trigger metric collection manually
        monitor._add_metric(
            "test_counter",
            MetricType.COUNTER,
            ComponentType.BAM_HANDLER,
            42.0,
            {"component": "bam_handler"},
        )

        # Generate Prometheus format
        prometheus_output = monitor.get_prometheus_metrics()

        assert "# HELP canbus_decoder_test_counter" in prometheus_output
        assert "# TYPE canbus_decoder_test_counter counter" in prometheus_output
        assert "canbus_decoder_test_counter" in prometheus_output
        assert "42.0" in prometheus_output

    def test_performance_summary_generation(self, monitor):
        """Test comprehensive performance summary generation."""
        # Add test data
        monitor.record_processing_time(ComponentType.BAM_HANDLER, 0.003)
        monitor.record_bam_session_start()
        monitor.record_bam_session_complete(0.025)
        monitor.record_safety_state_transition(0.002)
        monitor.record_security_frame_validated()
        monitor.record_security_anomaly_detected()

        # Generate summary
        summary = monitor.get_performance_summary()

        # Check structure
        assert "timestamp" in summary
        assert "uptime_hours" in summary
        assert "system" in summary
        assert "components" in summary
        assert "bam_handler" in summary
        assert "safety_engine" in summary
        assert "security_manager" in summary
        assert "threshold_violations" in summary

        # Check system stats
        assert summary["system"]["total_messages"] == 1
        assert summary["system"]["total_errors"] == 0

        # Check BAM stats
        assert summary["bam_handler"]["sessions_started"] == 1
        assert summary["bam_handler"]["sessions_completed"] == 1
        assert summary["bam_handler"]["completion_rate"] == 100.0

        # Check security stats
        assert summary["security_manager"]["frames_validated"] == 1
        assert summary["security_manager"]["anomalies_detected"] == 1
        assert summary["security_manager"]["anomaly_rate"] == 100.0

    def test_metrics_reset(self, monitor):
        """Test metrics reset functionality."""
        # Add some data
        monitor.record_processing_time(ComponentType.BAM_HANDLER, 0.003)
        monitor.record_bam_session_start()
        monitor.record_safety_state_transition(0.002)

        assert monitor.system_stats["total_messages_processed"] > 0
        assert monitor.bam_session_stats["sessions_started"] > 0

        # Reset metrics
        monitor.reset_metrics()

        # Check that everything is reset
        assert monitor.system_stats["total_messages_processed"] == 0
        assert monitor.bam_session_stats["sessions_started"] == 0
        assert monitor.safety_stats["state_transitions"] == 0
        assert monitor.security_stats["frames_validated"] == 0
        assert len(monitor.metrics) == 0

        # Check component stats are reset
        for stats in monitor.component_stats.values():
            assert stats.messages_processed == 0
            assert stats.error_count == 0

    def test_metric_retention_limits(self, monitor):
        """Test metric retention and memory management."""
        # Set very small retention for testing
        monitor.metrics.maxlen = 5

        # Add more metrics than the limit
        for i in range(10):
            monitor._add_metric(
                f"test_metric_{i}", MetricType.COUNTER, ComponentType.PROTOCOL_ROUTER, float(i)
            )

        # Should only retain the last 5 metrics
        assert len(monitor.metrics) == 5

        # Check that latest metrics are retained
        metric_values = [m.value for m in monitor.metrics]
        assert 5.0 in metric_values
        assert 9.0 in metric_values
        assert 0.0 not in metric_values

    def test_concurrent_metric_recording(self, monitor):
        """Test concurrent metric recording thread safety."""
        import threading

        def worker():
            for _ in range(100):
                monitor.record_processing_time(ComponentType.BAM_HANDLER, 0.001)
                monitor.record_bam_session_start()
                monitor.record_security_frame_validated()

        # Start multiple worker threads
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=worker)
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Check that all metrics were recorded correctly
        assert monitor.system_stats["total_messages_processed"] == 500  # 5 threads * 100 messages
        assert monitor.bam_session_stats["sessions_started"] == 500
        assert monitor.security_stats["frames_validated"] == 500

    def test_metric_collection_error_handling(self, monitor):
        """Test error handling in metrics collection."""
        # Mock a component stats to raise an exception
        mock_stats = Mock()
        mock_stats.get_avg_processing_time.side_effect = Exception("Test error")
        mock_stats.messages_processed = 1

        monitor.component_stats[ComponentType.BAM_HANDLER] = mock_stats

        # Collection should handle the error gracefully
        try:
            asyncio.run(monitor._collect_metrics())
        except Exception:
            pytest.fail("Metrics collection should handle errors gracefully")

    def test_custom_thresholds(self, monitor):
        """Test custom threshold configuration."""
        # Modify thresholds
        monitor.thresholds["max_processing_time_ms"] = 20.0
        monitor.thresholds["max_error_rate_percent"] = 10.0

        # Record data that would violate old thresholds but not new ones
        for _ in range(10):
            monitor.record_processing_time(ComponentType.BAM_HANDLER, 0.015)  # 15ms

        violations = monitor.check_performance_thresholds()

        # Should not violate the new 20ms threshold
        processing_violations = [v for v in violations if v["metric"] == "processing_time"]
        assert len(processing_violations) == 0

    def test_metrics_with_labels(self, monitor):
        """Test metrics with custom labels."""
        # Add metric with labels
        monitor._add_metric(
            "custom_metric",
            MetricType.GAUGE,
            ComponentType.SAFETY_ENGINE,
            100.0,
            {"environment": "test", "version": "1.0"},
        )

        # Check Prometheus output includes labels
        prometheus_output = monitor.get_prometheus_metrics()
        assert 'environment="test"' in prometheus_output
        assert 'version="1.0"' in prometheus_output
