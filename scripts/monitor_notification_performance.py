#!/usr/bin/env python3
"""
Simple performance monitor for the lightweight notification system.

This script monitors the notification system in real-time and logs
performance metrics suitable for Raspberry Pi environments.
"""

import asyncio
import logging
import signal
import sys
import time
from datetime import datetime
from typing import Optional

try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    print("Warning: psutil not available. Install with 'pip install psutil' for memory monitoring.")


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("notification_performance.log")],
)
logger = logging.getLogger(__name__)


class PerformanceMonitor:
    """Monitor notification system performance."""

    def __init__(self, check_interval: int = 30):
        self.check_interval = check_interval
        self.running = False
        self.start_time = time.time()
        self.checks_performed = 0

        # Performance thresholds for alerts
        self.thresholds = {
            "memory_mb": 200,  # Alert if memory > 200 MB
            "response_time_ms": 1000,  # Alert if response > 1s
            "error_rate": 0.1,  # Alert if error rate > 10%
            "circuit_breaker_open": 1,  # Alert if any circuit breaker is open
        }

        # Historical data (keep last hour)
        self.history = {
            "memory": [],
            "response_times": [],
            "success_rate": [],
            "timestamps": [],
        }
        self.max_history_size = 120  # 30s interval * 120 = 1 hour

    async def start(self, health_check_url: str) -> None:
        """Start monitoring the notification system."""
        self.running = True
        self.health_check_url = health_check_url

        logger.info("Starting notification performance monitor")
        logger.info(f"Health check URL: {health_check_url}")
        logger.info(f"Check interval: {self.check_interval} seconds")
        logger.info("Performance thresholds:")
        for key, value in self.thresholds.items():
            logger.info(f"  - {key}: {value}")

        # Set up signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        # Start monitoring loop
        await self._monitor_loop()

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info("Received shutdown signal, stopping monitor...")
        self.running = False

    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        import aiohttp

        async with aiohttp.ClientSession() as session:
            while self.running:
                try:
                    await self._perform_check(session)
                    await asyncio.sleep(self.check_interval)
                except Exception as e:
                    logger.error(f"Monitor loop error: {e}")
                    await asyncio.sleep(self.check_interval)

        logger.info("Performance monitor stopped")
        self._print_final_report()

    async def _perform_check(self, session) -> None:
        """Perform a single health check."""
        self.checks_performed += 1
        timestamp = datetime.now()

        try:
            # Get health status from notification system
            start_time = time.time()
            async with session.get(self.health_check_url, timeout=10) as response:
                response_time = (time.time() - start_time) * 1000

                if response.status == 200:
                    health_data = await response.json()
                    await self._process_health_data(health_data, response_time, timestamp)
                else:
                    logger.error(f"Health check failed with status {response.status}")

        except TimeoutError:
            logger.error("Health check timed out")
        except Exception as e:
            logger.error(f"Health check error: {e}")

    async def _process_health_data(
        self, health_data: dict, response_time: float, timestamp: datetime
    ) -> None:
        """Process and analyze health check data."""
        # Extract metrics
        metrics = health_data.get("metrics", {})
        circuit_breakers = health_data.get("circuit_breakers", {})
        pools = health_data.get("pools", {})
        cache = health_data.get("cache", {})
        batcher = health_data.get("batcher", {})

        # Current performance metrics
        current_metrics = {
            "timestamp": timestamp,
            "response_time_ms": response_time,
            "uptime_hours": health_data.get("uptime", 0) / 3600,
            "memory_mb": metrics.get("memory", {}).get("current_mb", 0),
            "total_sent": metrics.get("total_sent", 0),
            "total_failed": metrics.get("total_failed", 0),
            "success_rate": metrics.get("success_rate", 0),
            "cache_hit_rate": cache.get("hit_rate", 0),
            "batching_efficiency": batcher.get("efficiency", 0),
            "active_batches": batcher.get("active_batches", 0),
            "circuit_breakers_open": sum(
                1 for cb in circuit_breakers.values() if cb.get("state") == "open"
            ),
        }

        # Add to history
        self._add_to_history(current_metrics)

        # Log current status
        logger.info(f"Check #{self.checks_performed} at {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"  Response time: {response_time:.1f} ms")
        logger.info(f"  Memory usage: {current_metrics['memory_mb']:.1f} MB")
        logger.info(f"  Success rate: {current_metrics['success_rate']:.1%}")
        logger.info(f"  Active batches: {current_metrics['active_batches']}")
        logger.info(f"  Cache hit rate: {current_metrics['cache_hit_rate']:.1%}")

        # Check for issues
        issues = self._check_thresholds(current_metrics)
        if issues:
            logger.warning("Performance issues detected:")
            for issue in issues:
                logger.warning(f"  - {issue}")

        # Log pool statistics
        if pools:
            logger.debug("Connection pools:")
            for pool_name, pool_stats in pools.items():
                if pool_stats:
                    logger.debug(
                        f"  {pool_name}: {pool_stats.get('active', 0)}/{pool_stats.get('max_connections', 0)} active, "
                        f"reuse rate: {pool_stats.get('reuse_rate', 0):.1%}"
                    )

        # System resources (if psutil available)
        if PSUTIL_AVAILABLE:
            self._log_system_resources()

    def _add_to_history(self, metrics: dict) -> None:
        """Add metrics to history, maintaining size limit."""
        self.history["timestamps"].append(metrics["timestamp"])
        self.history["memory"].append(metrics["memory_mb"])
        self.history["response_times"].append(metrics["response_time_ms"])
        self.history["success_rate"].append(metrics["success_rate"])

        # Trim history if needed
        if len(self.history["timestamps"]) > self.max_history_size:
            for key in self.history:
                self.history[key] = self.history[key][-self.max_history_size :]

    def _check_thresholds(self, metrics: dict) -> list[str]:
        """Check if any metrics exceed thresholds."""
        issues = []

        if metrics["memory_mb"] > self.thresholds["memory_mb"]:
            issues.append(
                f"Memory usage ({metrics['memory_mb']:.1f} MB) exceeds threshold ({self.thresholds['memory_mb']} MB)"
            )

        if metrics["response_time_ms"] > self.thresholds["response_time_ms"]:
            issues.append(
                f"Response time ({metrics['response_time_ms']:.1f} ms) exceeds threshold ({self.thresholds['response_time_ms']} ms)"
            )

        if metrics["success_rate"] < (1 - self.thresholds["error_rate"]):
            issues.append(
                f"Success rate ({metrics['success_rate']:.1%}) below threshold ({(1 - self.thresholds['error_rate']):.1%})"
            )

        if metrics["circuit_breakers_open"] >= self.thresholds["circuit_breaker_open"]:
            issues.append(f"{metrics['circuit_breakers_open']} circuit breakers are open")

        return issues

    def _log_system_resources(self) -> None:
        """Log system resource usage."""
        if not PSUTIL_AVAILABLE:
            return

        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)

            # Memory usage
            memory = psutil.virtual_memory()

            # Disk usage
            disk = psutil.disk_usage("/")

            # Network (if available)
            net_io = psutil.net_io_counters()

            logger.debug("System resources:")
            logger.debug(f"  CPU: {cpu_percent:.1f}%")
            logger.debug(
                f"  Memory: {memory.percent:.1f}% ({memory.used / 1024 / 1024:.1f} MB used)"
            )
            logger.debug(f"  Disk: {disk.percent:.1f}% used")
            logger.debug(
                f"  Network: {net_io.bytes_sent / 1024 / 1024:.1f} MB sent, "
                f"{net_io.bytes_recv / 1024 / 1024:.1f} MB received"
            )

            # Temperature (Raspberry Pi specific)
            try:
                with open("/sys/class/thermal/thermal_zone0/temp") as f:
                    temp = float(f.read()) / 1000
                    logger.debug(f"  CPU Temperature: {temp:.1f}°C")
            except:
                pass

        except Exception as e:
            logger.debug(f"Failed to get system resources: {e}")

    def _print_final_report(self) -> None:
        """Print final monitoring report."""
        if not self.history["timestamps"]:
            return

        runtime = time.time() - self.start_time

        print("\n" + "=" * 60)
        print("NOTIFICATION SYSTEM PERFORMANCE REPORT")
        print("=" * 60)
        print(f"\nMonitoring Duration: {runtime / 3600:.1f} hours")
        print(f"Total Health Checks: {self.checks_performed}")

        # Memory statistics
        if self.history["memory"]:
            avg_memory = sum(self.history["memory"]) / len(self.history["memory"])
            max_memory = max(self.history["memory"])
            min_memory = min(self.history["memory"])

            print("\nMemory Usage:")
            print(f"  Average: {avg_memory:.1f} MB")
            print(f"  Maximum: {max_memory:.1f} MB")
            print(f"  Minimum: {min_memory:.1f} MB")

        # Response time statistics
        if self.history["response_times"]:
            avg_response = sum(self.history["response_times"]) / len(self.history["response_times"])
            max_response = max(self.history["response_times"])
            min_response = min(self.history["response_times"])

            print("\nResponse Times:")
            print(f"  Average: {avg_response:.1f} ms")
            print(f"  Maximum: {max_response:.1f} ms")
            print(f"  Minimum: {min_response:.1f} ms")

        # Success rate
        if self.history["success_rate"]:
            avg_success = sum(self.history["success_rate"]) / len(self.history["success_rate"])
            min_success = min(self.history["success_rate"])

            print("\nReliability:")
            print(f"  Average Success Rate: {avg_success:.1%}")
            print(f"  Minimum Success Rate: {min_success:.1%}")

        # Summary
        print("\nSummary:")
        if max_memory < 100:
            print("  ✓ Memory usage: EXCELLENT for Raspberry Pi")
        elif max_memory < 200:
            print("  ✓ Memory usage: GOOD for Raspberry Pi")
        else:
            print("  ⚠ Memory usage: May be high for Raspberry Pi")

        if avg_response < 500:
            print("  ✓ Response time: GOOD")
        else:
            print("  ⚠ Response time: Could be improved")

        if avg_success > 0.99:
            print("  ✓ Reliability: EXCELLENT")
        elif avg_success > 0.95:
            print("  ✓ Reliability: GOOD")
        else:
            print("  ⚠ Reliability: Needs improvement")


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Monitor notification system performance")
    parser.add_argument(
        "--url",
        default="http://localhost:8080/api/notifications/health",
        help="Health check endpoint URL",
    )
    parser.add_argument(
        "--interval", type=int, default=30, help="Check interval in seconds (default: 30)"
    )
    parser.add_argument(
        "--memory-threshold",
        type=int,
        default=200,
        help="Memory usage threshold in MB (default: 200)",
    )
    parser.add_argument(
        "--response-threshold",
        type=int,
        default=1000,
        help="Response time threshold in ms (default: 1000)",
    )

    args = parser.parse_args()

    # Create and configure monitor
    monitor = PerformanceMonitor(check_interval=args.interval)
    monitor.thresholds["memory_mb"] = args.memory_threshold
    monitor.thresholds["response_time_ms"] = args.response_threshold

    # Start monitoring
    await monitor.start(args.url)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nMonitoring stopped by user")
        sys.exit(0)
