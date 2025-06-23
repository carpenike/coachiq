"""
Simple load tests for lightweight notification system.

These tests simulate realistic RV scenarios with 1-5 users and verify
the system can handle the load on a Raspberry Pi.
"""

import asyncio
import logging
import random
import statistics
import time
from datetime import datetime
from typing import Any, Dict, List

import pytest

from backend.core.config import NotificationSettings
from backend.models.notification import NotificationType
from backend.services.notification_lightweight import LightweightNotificationManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LoadTestScenario:
    """Base class for load test scenarios."""

    def __init__(self, name: str, duration_seconds: int = 60):
        self.name = name
        self.duration_seconds = duration_seconds
        self.results = {
            "total_sent": 0,
            "total_failed": 0,
            "response_times": [],
            "memory_usage": [],
            "errors": [],
        }

    async def run(self, manager: LightweightNotificationManager) -> dict[str, Any]:
        """Run the scenario and collect metrics."""
        raise NotImplementedError

    def get_summary(self) -> dict[str, Any]:
        """Get test summary statistics."""
        response_times = self.results["response_times"]

        return {
            "scenario": self.name,
            "duration_seconds": self.duration_seconds,
            "total_requests": self.results["total_sent"] + self.results["total_failed"],
            "successful": self.results["total_sent"],
            "failed": self.results["total_failed"],
            "success_rate": self.results["total_sent"]
            / (self.results["total_sent"] + self.results["total_failed"])
            if (self.results["total_sent"] + self.results["total_failed"]) > 0
            else 0,
            "response_time_ms": {
                "min": min(response_times) if response_times else 0,
                "max": max(response_times) if response_times else 0,
                "avg": statistics.mean(response_times) if response_times else 0,
                "p50": statistics.median(response_times) if response_times else 0,
                "p95": statistics.quantiles(response_times, n=20)[18]
                if len(response_times) > 20
                else 0,
                "p99": statistics.quantiles(response_times, n=100)[98]
                if len(response_times) > 100
                else 0,
            },
            "requests_per_second": (self.results["total_sent"] + self.results["total_failed"])
            / self.duration_seconds,
            "memory_mb": {
                "avg": statistics.mean(self.results["memory_usage"])
                if self.results["memory_usage"]
                else 0,
                "max": max(self.results["memory_usage"]) if self.results["memory_usage"] else 0,
            },
            "errors": len(self.results["errors"]),
        }


class SingleUserScenario(LoadTestScenario):
    """Simulate a single user sending notifications at regular intervals."""

    def __init__(self):
        super().__init__("Single User", duration_seconds=60)

    async def run(self, manager: LightweightNotificationManager) -> dict[str, Any]:
        """Single user sending notifications every 5 seconds."""
        start_time = time.time()

        while time.time() - start_time < self.duration_seconds:
            try:
                send_start = time.time()

                success = await manager.send_notification(
                    message=f"System status update at {datetime.now()}",
                    title="Status Update",
                    level="info",
                    channels=["webhook"],
                )

                response_time = (time.time() - send_start) * 1000
                self.results["response_times"].append(response_time)

                if success:
                    self.results["total_sent"] += 1
                else:
                    self.results["total_failed"] += 1

                # Check memory usage
                health = await manager.get_health()
                if "memory" in health["metrics"] and health["metrics"]["memory"]:
                    self.results["memory_usage"].append(health["metrics"]["memory"]["current_mb"])

                # Wait 5 seconds between notifications
                await asyncio.sleep(5)

            except Exception as e:
                self.results["errors"].append(str(e))
                logger.error(f"Error in single user scenario: {e}")

        return self.get_summary()


class MultiUserScenario(LoadTestScenario):
    """Simulate multiple users sending notifications concurrently."""

    def __init__(self, num_users: int = 3):
        super().__init__(f"{num_users} Users", duration_seconds=60)
        self.num_users = num_users

    async def user_task(self, user_id: int, manager: LightweightNotificationManager) -> None:
        """Simulate a single user's notification pattern."""
        notification_types = [
            ("info", "System running normally", 0.7),
            ("warning", "Temperature above normal", 0.2),
            ("error", "Sensor disconnected", 0.08),
            ("critical", "System failure detected", 0.02),
        ]

        while True:
            try:
                # Random notification type based on probability
                rand = random.random()
                cumulative = 0
                level = "info"
                message = "Status update"

                for notif_level, notif_message, probability in notification_types:
                    cumulative += probability
                    if rand <= cumulative:
                        level = notif_level
                        message = notif_message
                        break

                send_start = time.time()

                success = await manager.send_notification(
                    message=f"User {user_id}: {message}",
                    title=f"Alert from User {user_id}",
                    level=level,
                    channels=["webhook", "smtp"] if level in ["error", "critical"] else ["webhook"],
                    recipient=f"user{user_id}@example.com"
                    if level in ["error", "critical"]
                    else None,
                )

                response_time = (time.time() - send_start) * 1000
                self.results["response_times"].append(response_time)

                if success:
                    self.results["total_sent"] += 1
                else:
                    self.results["total_failed"] += 1

                # Variable wait time based on notification level
                if level == "critical":
                    await asyncio.sleep(0.1)  # Immediate follow-up possible
                elif level == "error":
                    await asyncio.sleep(2)
                elif level == "warning":
                    await asyncio.sleep(5)
                else:
                    await asyncio.sleep(10 + random.randint(0, 10))

            except Exception as e:
                self.results["errors"].append(f"User {user_id}: {e!s}")

    async def run(self, manager: LightweightNotificationManager) -> dict[str, Any]:
        """Run multi-user scenario."""
        start_time = time.time()

        # Create user tasks
        tasks = []
        for i in range(self.num_users):
            task = asyncio.create_task(self.user_task(i + 1, manager))
            tasks.append(task)

        # Monitor for duration
        while time.time() - start_time < self.duration_seconds:
            # Check memory usage periodically
            health = await manager.get_health()
            if "memory" in health["metrics"] and health["metrics"]["memory"]:
                self.results["memory_usage"].append(health["metrics"]["memory"]["current_mb"])

            await asyncio.sleep(5)

        # Cancel all user tasks
        for task in tasks:
            task.cancel()

        # Wait for tasks to complete
        await asyncio.gather(*tasks, return_exceptions=True)

        return self.get_summary()


class BurstScenario(LoadTestScenario):
    """Simulate burst notification patterns (e.g., multiple alerts at once)."""

    def __init__(self):
        super().__init__("Burst Pattern", duration_seconds=60)

    async def run(self, manager: LightweightNotificationManager) -> dict[str, Any]:
        """Run burst scenario with periodic high-volume sends."""
        start_time = time.time()
        burst_count = 0

        while time.time() - start_time < self.duration_seconds:
            try:
                # Normal operation for 20 seconds
                for _ in range(4):
                    send_start = time.time()

                    success = await manager.send_notification(
                        message="Normal operation",
                        title="Status",
                        level="info",
                        channels=["webhook"],
                    )

                    response_time = (time.time() - send_start) * 1000
                    self.results["response_times"].append(response_time)

                    if success:
                        self.results["total_sent"] += 1
                    else:
                        self.results["total_failed"] += 1

                    await asyncio.sleep(5)

                # Burst: 10 notifications rapidly
                burst_count += 1
                logger.info(f"Starting burst #{burst_count}")

                burst_tasks = []
                for i in range(10):
                    task = asyncio.create_task(
                        self._send_burst_notification(manager, f"Burst notification {i + 1}")
                    )
                    burst_tasks.append(task)

                # Wait for burst to complete
                await asyncio.gather(*burst_tasks)

                # Check memory after burst
                health = await manager.get_health()
                if "memory" in health["metrics"] and health["metrics"]["memory"]:
                    self.results["memory_usage"].append(health["metrics"]["memory"]["current_mb"])

            except Exception as e:
                self.results["errors"].append(str(e))
                logger.error(f"Error in burst scenario: {e}")

        return self.get_summary()

    async def _send_burst_notification(
        self, manager: LightweightNotificationManager, message: str
    ) -> None:
        """Send a single burst notification."""
        try:
            send_start = time.time()

            success = await manager.send_notification(
                message=message,
                title="Burst Alert",
                level="warning",
                channels=["webhook"],
            )

            response_time = (time.time() - send_start) * 1000
            self.results["response_times"].append(response_time)

            if success:
                self.results["total_sent"] += 1
            else:
                self.results["total_failed"] += 1

        except Exception as e:
            self.results["errors"].append(str(e))


class MemoryStressScenario(LoadTestScenario):
    """Test memory efficiency with sustained load."""

    def __init__(self):
        super().__init__("Memory Stress", duration_seconds=120)

    async def run(self, manager: LightweightNotificationManager) -> dict[str, Any]:
        """Run memory stress test with large messages."""
        start_time = time.time()
        message_count = 0

        # Generate some large template data
        large_context = {
            "sensors": [f"sensor_{i}" for i in range(50)],
            "readings": {f"sensor_{i}": random.random() * 100 for i in range(50)},
            "timestamp": datetime.now().isoformat(),
        }

        while time.time() - start_time < self.duration_seconds:
            try:
                # Create a large message
                message = (
                    f"System report with {len(large_context['sensors'])} sensors: "
                    + ", ".join(
                        [f"{k}={v:.2f}" for k, v in list(large_context["readings"].items())[:10]]
                    )
                )

                send_start = time.time()

                success = await manager.send_notification(
                    message=message,
                    title=f"Report #{message_count}",
                    level="info",
                    channels=["webhook", "smtp"],
                    recipient="admin@example.com",
                )

                response_time = (time.time() - send_start) * 1000
                self.results["response_times"].append(response_time)

                if success:
                    self.results["total_sent"] += 1
                else:
                    self.results["total_failed"] += 1

                message_count += 1

                # Check memory every 10 messages
                if message_count % 10 == 0:
                    health = await manager.get_health()
                    if "memory" in health["metrics"] and health["metrics"]["memory"]:
                        memory_mb = health["metrics"]["memory"]["current_mb"]
                        self.results["memory_usage"].append(memory_mb)
                        logger.info(
                            f"Memory usage after {message_count} messages: {memory_mb:.1f} MB"
                        )

                # Small delay
                await asyncio.sleep(0.5)

            except Exception as e:
                self.results["errors"].append(str(e))
                logger.error(f"Error in memory stress scenario: {e}")

        return self.get_summary()


async def run_load_tests(config: NotificationSettings) -> dict[str, Any]:
    """Run all load test scenarios."""
    results = {}

    # Test scenarios
    scenarios = [
        SingleUserScenario(),
        MultiUserScenario(num_users=3),
        MultiUserScenario(num_users=5),
        BurstScenario(),
        MemoryStressScenario(),
    ]

    for scenario in scenarios:
        logger.info(f"\n{'=' * 60}")
        logger.info(f"Running scenario: {scenario.name}")
        logger.info(f"Duration: {scenario.duration_seconds} seconds")
        logger.info(f"{'=' * 60}")

        # Create fresh manager for each scenario
        manager = LightweightNotificationManager(config)
        await manager.initialize()

        try:
            # Run scenario
            result = await scenario.run(manager)
            results[scenario.name] = result

            # Print summary
            logger.info(f"\nScenario: {result['scenario']}")
            logger.info(f"Total requests: {result['total_requests']}")
            logger.info(f"Success rate: {result['success_rate']:.2%}")
            logger.info(f"Requests/second: {result['requests_per_second']:.2f}")
            logger.info(f"Response time (avg): {result['response_time_ms']['avg']:.2f} ms")
            logger.info(f"Response time (p95): {result['response_time_ms']['p95']:.2f} ms")
            logger.info(f"Memory usage (max): {result['memory_mb']['max']:.1f} MB")

            # Get final health check
            health = await manager.get_health()
            logger.info("\nFinal health check:")
            logger.info(f"- Circuit breakers: {len(health['circuit_breakers'])} channels")
            logger.info(f"- Cache hit rate: {health['cache']['hit_rate']:.2%}")
            logger.info(f"- Batching efficiency: {health['batcher']['efficiency']:.2%}")

        finally:
            await manager.close()

        # Brief pause between scenarios
        await asyncio.sleep(5)

    return results


def print_final_report(results: dict[str, Any]) -> None:
    """Print final test report."""
    print("\n" + "=" * 80)
    print("LOAD TEST FINAL REPORT")
    print("=" * 80)

    # Overall statistics
    total_requests = sum(r["total_requests"] for r in results.values())
    total_successful = sum(r["successful"] for r in results.values())
    overall_success_rate = total_successful / total_requests if total_requests > 0 else 0

    print("\nOverall Statistics:")
    print(f"- Total requests: {total_requests}")
    print(f"- Total successful: {total_successful}")
    print(f"- Overall success rate: {overall_success_rate:.2%}")

    # Memory usage
    max_memory = max(r["memory_mb"]["max"] for r in results.values() if r["memory_mb"]["max"] > 0)
    print(f"- Peak memory usage: {max_memory:.1f} MB")

    # Performance by scenario
    print("\nPerformance by Scenario:")
    print("-" * 80)
    print(
        f"{'Scenario':<20} {'Requests':<10} {'Success':<10} {'Avg RT (ms)':<12} {'P95 RT (ms)':<12} {'Errors':<8}"
    )
    print("-" * 80)

    for name, result in results.items():
        print(
            f"{name:<20} {result['total_requests']:<10} "
            f"{result['success_rate'] * 100:<9.1f}% "
            f"{result['response_time_ms']['avg']:<12.1f} "
            f"{result['response_time_ms']['p95']:<12.1f} "
            f"{result['errors']:<8}"
        )

    # Raspberry Pi suitability
    print("\nRaspberry Pi Suitability:")
    print("-" * 40)

    if max_memory < 100:
        print("✓ Memory usage: EXCELLENT (<100 MB)")
    elif max_memory < 200:
        print("✓ Memory usage: GOOD (<200 MB)")
    elif max_memory < 500:
        print("⚠ Memory usage: ACCEPTABLE (<500 MB)")
    else:
        print("✗ Memory usage: HIGH (>500 MB)")

    avg_response_times = [r["response_time_ms"]["avg"] for r in results.values()]
    overall_avg_rt = sum(avg_response_times) / len(avg_response_times)

    if overall_avg_rt < 100:
        print("✓ Response time: EXCELLENT (<100 ms)")
    elif overall_avg_rt < 500:
        print("✓ Response time: GOOD (<500 ms)")
    elif overall_avg_rt < 1000:
        print("⚠ Response time: ACCEPTABLE (<1s)")
    else:
        print("✗ Response time: SLOW (>1s)")

    if overall_success_rate > 0.99:
        print("✓ Reliability: EXCELLENT (>99%)")
    elif overall_success_rate > 0.95:
        print("✓ Reliability: GOOD (>95%)")
    elif overall_success_rate > 0.90:
        print("⚠ Reliability: ACCEPTABLE (>90%)")
    else:
        print("✗ Reliability: POOR (<90%)")


@pytest.mark.asyncio
async def test_notification_load():
    """Main test entry point."""
    # Create test configuration
    config = NotificationSettings(
        enabled=True,
        webhook={
            "enabled": True,
            "targets": {"default": {"url": "http://localhost:8080/webhook", "enabled": True}},
        },
        smtp={
            "enabled": True,
            "host": "localhost",
            "port": 1025,
            "from_email": "test@example.com",
        },
    )

    # Run load tests
    results = await run_load_tests(config)

    # Print final report
    print_final_report(results)

    # Assert basic performance requirements
    for name, result in results.items():
        assert result["success_rate"] > 0.9, f"{name} success rate too low"
        assert result["memory_mb"]["max"] < 500, f"{name} memory usage too high"
        assert result["response_time_ms"]["p95"] < 5000, f"{name} response time too slow"


if __name__ == "__main__":
    # Run directly for manual testing
    asyncio.run(test_notification_load())
