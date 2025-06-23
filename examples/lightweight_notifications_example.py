#!/usr/bin/env python3
"""
Example usage of the lightweight notification system.

This demonstrates how to use the optimized notification manager
in a Raspberry Pi RV environment.
"""

import asyncio
import logging
from datetime import datetime

from backend.core.config import NotificationSettings
from backend.services.notification_lightweight import LightweightNotificationManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def basic_example():
    """Basic notification sending example."""
    print("\n=== Basic Notification Example ===")

    # Create minimal configuration
    config = NotificationSettings(
        enabled=True,
        webhook={
            "enabled": True,
            "targets": {"default": {"url": "http://localhost:8080/webhook", "enabled": True}},
        },
    )

    # Create manager
    manager = LightweightNotificationManager(config)
    await manager.initialize()

    try:
        # Send a simple notification
        success = await manager.send_notification(
            message="System started successfully",
            title="RV System Status",
            level="info",
            channels=["webhook"],
        )

        print(f"Notification sent: {success}")

        # Check health
        health = await manager.get_health()
        print(f"System health: {health['status']}")
        print(f"Memory usage: {health['metrics']['memory'].get('current_mb', 'N/A')} MB")

    finally:
        await manager.close()


async def batching_example():
    """Example showing efficient batching."""
    print("\n=== Batching Example ===")

    config = NotificationSettings(
        enabled=True,
        webhook={
            "enabled": True,
            "targets": {"default": {"url": "http://localhost:8080/webhook", "enabled": True}},
        },
    )

    manager = LightweightNotificationManager(config)
    await manager.initialize()

    try:
        # Send multiple notifications that will be batched
        print("Sending 10 notifications with batching...")

        for i in range(10):
            await manager.send_notification(
                message=f"Sensor reading #{i}: Temperature normal",
                title="Sensor Update",
                level="info",
                channels=["webhook"],
                batch=True,  # Enable batching
            )

            # Small delay to show batching
            await asyncio.sleep(0.1)

        # Wait for batch to process
        await asyncio.sleep(6)

        # Check batching stats
        health = await manager.get_health()
        batcher_stats = health["batcher"]
        print(f"Batching efficiency: {batcher_stats['efficiency']:.1%}")
        print(f"Total batched: {batcher_stats['total_batched']}")
        print(f"Total sent: {batcher_stats['total_sent']}")

    finally:
        await manager.close()


async def multi_channel_example():
    """Example with multiple notification channels."""
    print("\n=== Multi-Channel Example ===")

    config = NotificationSettings(
        enabled=True,
        webhook={
            "enabled": True,
            "url": "http://localhost:8080/webhook",
        },
        smtp={
            "enabled": True,
            "host": "smtp.gmail.com",
            "port": 587,
            "username": "your-email@gmail.com",
            "password": "your-app-password",
            "from_email": "your-email@gmail.com",
            "use_tls": True,
        },
    )

    manager = LightweightNotificationManager(config)
    await manager.initialize()

    try:
        # Critical alert to multiple channels
        success = await manager.send_notification(
            message="Battery voltage critically low: 10.5V",
            title="CRITICAL: RV System Alert",
            level="critical",
            channels=["webhook", "smtp"],
            recipient="owner@example.com",
            batch=False,  # Don't batch critical alerts
        )

        print(f"Critical alert sent: {success}")

        # Check circuit breaker status
        health = await manager.get_health()
        print("\nCircuit breaker status:")
        for channel, status in health["circuit_breakers"].items():
            print(f"  {channel}: {status['state']} (failures: {status['failures']})")

    finally:
        await manager.close()


async def performance_monitoring_example():
    """Example showing performance monitoring."""
    print("\n=== Performance Monitoring Example ===")

    config = NotificationSettings(
        enabled=True,
        webhook={
            "enabled": True,
            "targets": {"default": {"url": "http://localhost:8080/webhook", "enabled": True}},
        },
    )

    manager = LightweightNotificationManager(config)
    await manager.initialize()

    try:
        # Send notifications and monitor performance
        print("Sending notifications and monitoring performance...")

        for i in range(5):
            # Different notification types
            if i % 3 == 0:
                level = "warning"
                message = f"Temperature above normal: {75 + i}°F"
            else:
                level = "info"
                message = f"System check #{i}: All systems normal"

            success = await manager.send_notification(
                message=message,
                title="System Monitor",
                level=level,
                channels=["webhook"],
            )

            # Get current metrics
            health = await manager.get_health()
            metrics = health["metrics"]

            print(f"\nNotification {i + 1}:")
            print(f"  Success: {success}")
            print(f"  Total sent: {metrics['total_sent']}")
            print(f"  Success rate: {metrics['success_rate']:.1%}")
            print(f"  Avg response time: {metrics['delivery_time_ms']['avg']:.1f} ms")

            await asyncio.sleep(1)

        # Final health report
        print("\n--- Final Health Report ---")
        health = await manager.get_health()

        print(f"Uptime: {health['metrics']['uptime_seconds']:.1f} seconds")
        print(f"Cache hit rate: {health['cache']['hit_rate']:.1%}")
        print("Connection pools:")
        for pool_name, pool_stats in health["pools"].items():
            if pool_stats:
                print(f"  {pool_name}: {pool_stats['reuse_rate']:.1%} reuse rate")

    finally:
        await manager.close()


async def rv_scenario_example():
    """Realistic RV monitoring scenario."""
    print("\n=== RV Monitoring Scenario ===")

    config = NotificationSettings(
        enabled=True,
        webhook={
            "enabled": True,
            "url": "http://localhost:8080/webhook",
        },
        smtp={
            "enabled": True,
            "host": "smtp.gmail.com",
            "port": 587,
            "username": "rv-monitor@example.com",
            "password": "app-password",
            "from_email": "rv-monitor@example.com",
            "use_tls": True,
        },
    )

    manager = LightweightNotificationManager(config)
    await manager.initialize()

    try:
        print("Starting RV monitoring simulation...")

        # Simulate various RV events
        events = [
            ("info", "Shore power connected", ["webhook"], None),
            ("info", "Water tank at 75%", ["webhook"], None),
            ("warning", "Battery voltage low: 11.8V", ["webhook"], None),
            ("info", "Solar charging active: 14.2V", ["webhook"], None),
            ("error", "Propane level critical: 5%", ["webhook", "smtp"], "owner@example.com"),
            ("info", "Generator started", ["webhook"], None),
            ("warning", "High temperature in living area: 85°F", ["webhook"], None),
            ("critical", "Smoke detector activated!", ["webhook", "smtp"], "owner@example.com"),
        ]

        for level, message, channels, recipient in events:
            print(f"\nEvent: {message}")

            success = await manager.send_notification(
                message=f"{datetime.now().strftime('%H:%M:%S')} - {message}",
                title="RV Monitor Alert",
                level=level,
                channels=channels,
                recipient=recipient,
                batch=(level not in ["error", "critical"]),  # Batch non-critical
            )

            print(f"  Sent: {success}")

            # Simulate time between events
            await asyncio.sleep(2)

        # Wait for any batched notifications
        await asyncio.sleep(6)

        # Final system report
        health = await manager.get_health()
        print("\n--- RV Monitor System Report ---")
        print(f"Total notifications sent: {health['metrics']['total_sent']}")
        print(f"Success rate: {health['metrics']['success_rate']:.1%}")
        print(f"Memory usage: {health['metrics']['memory'].get('current_mb', 'N/A')} MB")
        print(f"Batching efficiency: {health['batcher']['efficiency']:.1%}")

        # Check if suitable for Pi
        memory = health["metrics"]["memory"].get("current_mb", 0)
        if memory and memory < 100:
            print("\n✓ Memory usage is EXCELLENT for Raspberry Pi deployment")
        elif memory and memory < 200:
            print("\n✓ Memory usage is GOOD for Raspberry Pi deployment")
        else:
            print("\n⚠ Memory usage may be high for Raspberry Pi")

    finally:
        await manager.close()


async def main():
    """Run all examples."""
    examples = [
        basic_example,
        batching_example,
        multi_channel_example,
        performance_monitoring_example,
        rv_scenario_example,
    ]

    for example in examples:
        try:
            await example()
        except Exception as e:
            print(f"Error in {example.__name__}: {e}")

        # Brief pause between examples
        await asyncio.sleep(2)


if __name__ == "__main__":
    print("Lightweight Notification System Examples")
    print("========================================")
    print("Optimized for Raspberry Pi in RV environments")
    print()

    asyncio.run(main())
