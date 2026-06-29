# Lightweight Notification System for Raspberry Pi

This document describes the optimized notification system designed specifically for resource-constrained environments like a Raspberry Pi running in an RV with fewer than 5 users.

## Key Features

### 1. Simple In-Memory Caching
- **LRU Cache**: Least Recently Used cache for templates and configurations
- **TTL Support**: Time-to-live expiration for cached items
- **No Redis Required**: Eliminates external dependencies
- **Configurable Size**: Default 100 items, suitable for Pi's memory constraints

### 2. Connection Pooling
- **SMTP Pool**: Reuses SMTP connections (max 2 connections)
- **HTTP Pool**: Reuses HTTP sessions for webhooks (max 3 connections)
- **Automatic Health Checks**: Validates connections before reuse
- **Idle Timeout**: Connections expire after 5 minutes of inactivity

### 3. Lightweight Batching
- **Time Windows**: Groups notifications within 5-second windows
- **Size Limits**: Maximum 20 notifications per batch
- **Smart Grouping**: Groups by channel and priority
- **Critical Bypass**: Critical notifications sent immediately

### 4. Simple Circuit Breaker
- **Failure Tracking**: Opens circuit after 3 consecutive failures
- **Recovery Timeout**: Attempts recovery after 60 seconds
- **Per-Channel Protection**: Independent circuit breakers for each channel
- **Graceful Degradation**: System continues working with available channels

### 5. Performance Monitoring
- **Memory Tracking**: Monitors current memory usage
- **Response Times**: Tracks delivery performance
- **Success Rates**: Monitors reliability metrics
- **No External Tools**: Self-contained monitoring

## Usage

### Basic Setup

```python
from backend.core.config import NotificationSettings
from backend.services.notifications.notification_lightweight import LightweightNotificationManager

# Minimal configuration
config = NotificationSettings(
    enabled=True,
    webhook={
        "enabled": True,
        "url": "http://your-webhook-url.com/notify"
    }
)

# Create and initialize manager
manager = LightweightNotificationManager(config)
await manager.initialize()

# Send notification
success = await manager.send_notification(
    message="Battery voltage low",
    title="RV Alert",
    level="warning",
    channels=["webhook"]
)

# Clean shutdown
await manager.close()
```

### With Email Support

```python
config = NotificationSettings(
    enabled=True,
    webhook={"enabled": True, "url": "http://webhook.url"},
    smtp={
        "enabled": True,
        "host": "smtp.gmail.com",
        "port": 587,
        "username": "your-email@gmail.com",
        "password": "your-app-password",
        "from_email": "your-email@gmail.com",
        "use_tls": True
    }
)
```

### Batching for Efficiency

```python
# Enable batching for non-critical notifications
for sensor_reading in readings:
    await manager.send_notification(
        message=f"Sensor: {sensor_reading}",
        level="info",
        channels=["webhook"],
        batch=True  # Groups notifications
    )
```

## Performance Characteristics

### Memory Usage
- **Baseline**: ~20-30 MB
- **Under Load**: <100 MB (1-5 users)
- **Peak Usage**: <200 MB (burst scenarios)

### Response Times
- **Single Notification**: <100ms (local webhook)
- **Batched Notifications**: ~5ms per notification
- **Email Delivery**: <500ms (SMTP connection pooled)

### Reliability
- **Success Rate**: >99% under normal conditions
- **Circuit Protection**: Prevents cascade failures
- **Graceful Degradation**: Continues with working channels

## Load Testing

Run the included load tests to verify performance:

```bash
# Run all test scenarios
poetry run pytest tests/performance/test_notification_load.py -v

# Run specific scenario
poetry run python -m pytest tests/performance/test_notification_load.py::test_notification_load -k "Single User" -v
```

Test scenarios include:
1. **Single User**: Regular notifications every 5 seconds
2. **Multi User (3-5)**: Concurrent users with varied patterns
3. **Burst Pattern**: Periodic high-volume sends
4. **Memory Stress**: Large messages and sustained load

## Performance Monitoring

Monitor the system in real-time:

```bash
# Start the performance monitor
poetry run python scripts/monitor_notification_performance.py \
    --url http://localhost:8080/api/notifications/health \
    --interval 30 \
    --memory-threshold 200
```

The monitor will:
- Check system health every 30 seconds
- Alert if memory exceeds 200 MB
- Log performance metrics to file
- Display real-time statistics

## Raspberry Pi Optimization Tips

### 1. System Configuration
```bash
# Increase swap (if needed)
sudo dphys-swapfile swapoff
sudo sed -i 's/CONF_SWAPSIZE=100/CONF_SWAPSIZE=512/' /etc/dphys-swapfile
sudo dphys-swapfile setup
sudo dphys-swapfile swapon

# Monitor temperature
vcgencmd measure_temp
```

### 2. Service Configuration
```ini
# /etc/systemd/system/coachiq-notifications.service
[Unit]
Description=CoachIQ Notification Service
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/coachiq
Environment="PYTHONUNBUFFERED=1"
ExecStart=/home/pi/coachiq/venv/bin/python notification_service.py
Restart=on-failure
RestartSec=10

# Memory limits
MemoryMax=256M
MemoryHigh=200M

[Install]
WantedBy=multi-user.target
```

### 3. Recommended Settings
```python
# For Raspberry Pi deployment
config = NotificationSettings(
    # Reduce connection pool sizes
    max_smtp_connections=1,
    max_http_connections=2,

    # Smaller batch sizes
    batch_size=10,
    batch_window_seconds=10,

    # Conservative circuit breaker
    circuit_failure_threshold=2,
    circuit_recovery_timeout=120,

    # Smaller cache
    cache_size=50,
    cache_ttl=1800,  # 30 minutes
)
```

## Troubleshooting

### High Memory Usage
1. Check cache size: `health['cache']['size']`
2. Reduce batch sizes
3. Check for memory leaks in custom templates
4. Enable more aggressive garbage collection

### Slow Response Times
1. Check circuit breaker status
2. Verify network connectivity
3. Check connection pool health
4. Reduce batch window for time-sensitive notifications

### Failed Notifications
1. Check circuit breaker states
2. Verify webhook/SMTP configuration
3. Check network connectivity
4. Review error logs

## API Integration

### Health Endpoint
```python
# Add to your FastAPI app
from backend.api.routers.notification_health import router
app.include_router(router)

# GET /api/notifications/health
# Returns system health and metrics
```

### Test Endpoint
```python
# POST /api/notifications/test
{
    "message": "Test notification",
    "level": "info",
    "channels": ["webhook"]
}
```

## Example Scenarios

See `examples/lightweight_notifications_example.py` for complete examples:
- Basic notification sending
- Efficient batching
- Multi-channel delivery
- Performance monitoring
- Realistic RV monitoring scenario

## Best Practices

1. **Batch Non-Critical Notifications**: Use `batch=True` for regular updates
2. **Immediate Critical Alerts**: Use `batch=False` for emergencies
3. **Monitor Memory Usage**: Check health endpoint regularly
4. **Handle Failures Gracefully**: Circuit breakers prevent cascade failures
5. **Clean Shutdown**: Always call `await manager.close()`
6. **Configure Appropriately**: Adjust settings for your Pi model and load

## Conclusion

This lightweight notification system provides reliable, efficient notification delivery suitable for Raspberry Pi deployments in RV environments. With proper configuration and monitoring, it can handle typical RV monitoring scenarios while maintaining low memory usage and good performance.
