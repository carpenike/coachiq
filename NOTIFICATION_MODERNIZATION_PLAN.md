# Notification System Modernization Plan

## Executive Summary

This document outlines a phased approach to modernize the CoachIQ notification system from a synchronous, blocking implementation to an asynchronous, queue-based architecture suitable for safety-critical RV-C vehicle environments. The plan prioritizes system reliability, safety boundaries, and operational resilience while maintaining compatibility with existing features.

## Current State Assessment

### Existing Implementation Strengths
- ✅ **Multi-channel support** via Apprise (email, Slack, Discord, 80+ services)
- ✅ **Template system** with Jinja2 for magic link authentication
- ✅ **Feature management integration** with proper dependency resolution
- ✅ **Configuration management** via environment variables
- ✅ **Health monitoring** with background tasks
- ✅ **Production-ready** error handling and logging

### Critical Issues Identified
- 🚨 **Synchronous blocking operations** can impact vehicle control systems
- 🚨 **No persistence** - notifications lost during system restarts
- 🚨 **Rate limiting gaps** vulnerable to CAN bus message flooding attacks
- 🚨 **Template injection risks** from unsanitized vehicle data
- 🚨 **Magic link security** needs scope reduction for safety

## Phased Modernization Strategy

### Phase 1: Foundation & Safety (Weeks 1-2)
**Goal**: Establish persistent queue and safety boundaries without breaking existing functionality

#### 1.1 Persistent Queue Implementation
```python
# New SQLite-based notification queue
class NotificationQueue:
    """Persistent SQLite queue for notification reliability"""

    def __init__(self, db_path: str = "data/notifications.db"):
        self.db_path = db_path
        self._init_tables()

    async def enqueue(self, notification: NotificationPayload) -> str:
        """Add notification to persistent queue"""

    async def dequeue_batch(self, size: int = 10) -> List[NotificationPayload]:
        """Get batch of notifications for processing"""

    async def move_to_dlq(self, notification_id: str, error: str) -> None:
        """Move failed notification to dead letter queue"""
```

#### 1.2 Rate Limiting & Input Sanitization
```python
class SafeNotificationManager(NotificationManager):
    """Enhanced manager with safety-critical protections"""

    def __init__(self):
        super().__init__()
        self.rate_limiter = TokenBucketRateLimiter(
            max_tokens=100,  # Max 100 notifications
            refill_rate=10,  # 10 per minute
            window_minutes=1
        )
        self.debouncer = NotificationDebouncer(
            suppress_window_minutes=15  # Same notification type suppressed for 15 min
        )
        self.template_sandbox = SandboxedEnvironment()  # Jinja2 security

    async def notify(self, message: str, **kwargs) -> bool:
        """Safe notification entry point with rate limiting"""
        # 1. Rate limit and debounce
        if not self.rate_limiter.allow(message):
            logger.warning("Notification rate limited", extra={"message": message})
            return False

        if not self.debouncer.allow(message, kwargs.get('level', 'info')):
            logger.debug("Notification debounced", extra={"message": message})
            return False

        # 2. Sanitize all inputs
        sanitized_data = self._sanitize_template_data(kwargs)

        # 3. Queue immediately (non-blocking)
        notification_id = await self.queue.enqueue(
            NotificationPayload(
                id=str(uuid4()),
                message=message,
                data=sanitized_data,
                created_at=datetime.utcnow(),
                retry_count=0
            )
        )

        return True
```

#### 1.3 Background Async Dispatcher
```python
class AsyncNotificationDispatcher:
    """Background service for processing notification queue"""

    async def start_worker(self):
        """Main worker loop - runs as background task"""
        while True:
            try:
                batch = await self.queue.dequeue_batch(size=10)
                if batch:
                    await self._process_batch(batch)
                else:
                    await asyncio.sleep(5)  # No work, wait 5 seconds
            except Exception as e:
                logger.error("Dispatcher error", exc_info=e)
                await asyncio.sleep(30)  # Error recovery delay

    async def _process_batch(self, notifications: List[NotificationPayload]):
        """Process batch with concurrent sends and retry logic"""
        tasks = [
            self._send_with_retry(notification)
            for notification in notifications
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for notification, result in zip(notifications, results):
            if isinstance(result, Exception):
                await self._handle_failure(notification, result)
            else:
                await self.queue.mark_complete(notification.id)
```

**Deliverables Phase 1:**
- [ ] SQLite queue implementation with WAL mode for durability
- [ ] Rate limiting with token bucket algorithm
- [ ] Notification debouncing to prevent spam
- [ ] Template input sanitization with Jinja2 SandboxedEnvironment
- [ ] Background async dispatcher with retry logic
- [ ] Dead letter queue for persistent failures
- [ ] Comprehensive unit tests for queue operations
- [ ] Integration tests with mocked Apprise services

**Success Criteria:**
- All existing notification functionality preserved
- No blocking operations in main application thread
- Notifications survive system restarts
- Rate limiting prevents notification storms
- Security scanning passes with template sanitization

---

### Phase 2: Service Integration & Monitoring (Weeks 3-4)
**Goal**: Integrate with existing service architecture and enhance observability

#### 2.1 Service Architecture Integration
```python
# Enhanced feature integration
class NotificationFeature(FeatureBase):
    """Updated feature with queue-based architecture"""

    async def start(self):
        """Start notification services"""
        self.manager = SafeNotificationManager()
        self.dispatcher = AsyncNotificationDispatcher(
            queue=self.manager.queue,
            apprise_manager=self.manager.apprise_manager
        )

        # Start background dispatcher
        self.dispatcher_task = asyncio.create_task(
            self.dispatcher.start_worker()
        )

    async def stop(self):
        """Graceful shutdown"""
        if hasattr(self, 'dispatcher_task'):
            self.dispatcher_task.cancel()
            try:
                await self.dispatcher_task
            except asyncio.CancelledError:
                pass

        # Ensure queue is flushed
        await self.manager.queue.close()
```

#### 2.2 Enhanced Health Monitoring
```python
class NotificationHealthMonitor:
    """Advanced health monitoring for notification system"""

    async def get_health_status(self) -> Dict[str, Any]:
        """Comprehensive health check"""
        queue_stats = await self.queue.get_statistics()

        return {
            "status": "healthy" if self._is_healthy(queue_stats) else "degraded",
            "queue_depth": queue_stats["pending_count"],
            "dlq_depth": queue_stats["dlq_count"],
            "success_rate_24h": await self._get_success_rate(),
            "channel_status": await self._check_all_channels(),
            "last_successful_send": queue_stats["last_success"],
            "rate_limiter_status": self.rate_limiter.get_status(),
            "dispatcher_uptime": self.dispatcher.get_uptime()
        }

    def _is_healthy(self, stats: Dict) -> bool:
        """Health assessment logic"""
        return (
            stats["pending_count"] < 1000 and  # Queue not backed up
            stats["dlq_count"] < 100 and       # DLQ not growing
            stats["last_success"] > datetime.utcnow() - timedelta(hours=1)
        )
```

#### 2.3 Pushover Integration
```python
# Add Pushover configuration to existing setup
class PushoverSettings(BaseSettings):
    enabled: bool = False
    user_key: str = ""
    token: str = ""
    device: str = ""
    priority_mapping: Dict[str, int] = {
        "critical": 1,    # High priority, bypass quiet hours
        "warning": 0,     # Normal priority
        "info": -1,       # Low priority
        "debug": -2       # Lowest priority
    }

# Enhanced notification with priority support
async def send_notification(
    self,
    message: str,
    level: str = "info",
    channels: Optional[List[str]] = None,
    **kwargs
) -> bool:
    """Send notification with channel-specific optimizations"""

    # Map severity levels to Pushover priorities
    pushover_priority = self.config.pushover.priority_mapping.get(level, 0)

    notification_data = {
        "message": message,
        "level": level,
        "pushover_priority": pushover_priority,
        "channels": channels or self._get_default_channels(),
        **kwargs
    }

    return await self.notify(**notification_data)
```

**Deliverables Phase 2:**
- [ ] Service lifecycle integration with graceful startup/shutdown
- [ ] Enhanced health monitoring with queue depth tracking
- [ ] Pushover integration with priority mapping
- [ ] Metrics collection for success rates and latency
- [ ] Updated configuration management for new settings
- [ ] Performance benchmarking suite
- [ ] Alerting for system health degradation

**Success Criteria:**
- Health endpoint reports accurate system status
- Pushover notifications work with priority levels
- Background services start/stop cleanly with main application
- Performance metrics show no degradation in core functions
- Queue processing maintains target latency (< 30 seconds)

---

### Phase 3: Security Hardening & Advanced Features (Weeks 5-6)
**Goal**: Implement security best practices and advanced operational features

#### 3.1 Magic Link Security Redesign
```python
class SecureMagicLinkManager:
    """Hardened magic link implementation"""

    def generate_magic_link(
        self,
        email: str,
        purpose: str = "notification_status"  # Read-only by default
    ) -> str:
        """Generate secure, scoped magic link"""

        # Generate cryptographically secure token
        token_bytes = secrets.token_bytes(32)
        token = base64.urlsafe_b64encode(token_bytes).decode('ascii')

        # Create limited-scope payload
        payload = {
            "email": email,
            "purpose": purpose,  # Limited to: notification_status, settings_view
            "exp": int(time.time()) + 900,  # 15 minute expiry
            "iat": int(time.time()),
            "scope": ["read:notifications"] if purpose == "notification_status" else []
        }

        # Sign with app secret
        signed_token = self.jwt_manager.encode(payload)

        # Store in cache for single-use validation
        await self.redis.setex(
            f"magic_link:{token}",
            900,  # 15 minutes
            signed_token
        )

        return f"{self.config.base_url}/auth/magic?token={token}"

    async def validate_magic_link(self, token: str) -> Optional[Dict]:
        """Validate and consume magic link (single use)"""

        # Check if token exists and remove it (single use)
        signed_token = await self.redis.getdel(f"magic_link:{token}")
        if not signed_token:
            return None

        try:
            payload = self.jwt_manager.decode(signed_token)
            return payload
        except JWTError:
            return None
```

#### 3.2 Advanced Queue Management
```python
class AdvancedQueueManager:
    """Advanced queue features for operational excellence"""

    async def get_queue_analytics(self) -> Dict[str, Any]:
        """Detailed queue analytics"""
        return {
            "queue_depth_trend": await self._get_depth_trend(hours=24),
            "success_rate_by_channel": await self._get_channel_success_rates(),
            "average_processing_time": await self._get_avg_processing_time(),
            "peak_usage_hours": await self._get_peak_usage_analysis(),
            "failure_categories": await self._get_failure_analysis()
        }

    async def replay_failed_notifications(
        self,
        from_time: datetime,
        to_time: datetime
    ) -> int:
        """Replay notifications from DLQ within time range"""

        failed_notifications = await self.queue.get_dlq_range(from_time, to_time)
        replayed_count = 0

        for notification in failed_notifications:
            # Reset retry count and move back to main queue
            notification.retry_count = 0
            notification.status = "pending"

            await self.queue.enqueue(notification)
            await self.queue.remove_from_dlq(notification.id)
            replayed_count += 1

        return replayed_count

    async def purge_old_notifications(self, days: int = 30) -> int:
        """Clean up old processed notifications"""
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        return await self.queue.purge_before(cutoff_date)
```

#### 3.3 Environmental Hardening
```python
class RVEnvironmentOptimizations:
    """Optimizations for RV/embedded environment"""

    def __init__(self):
        self.storage_monitor = StorageMonitor()
        self.connectivity_detector = ConnectivityDetector()

    async def configure_for_environment(self):
        """Apply environment-specific optimizations"""

        # Configure SQLite for durability and minimal wear
        await self.queue.configure_sqlite(
            journal_mode="WAL",           # Write-ahead logging for durability
            synchronous="NORMAL",         # Balance between safety and performance
            cache_size=-64000,           # 64MB cache
            wal_autocheckpoint=1000,     # Checkpoint every 1000 pages
            vacuum_auto=True             # Auto-vacuum for space management
        )

        # Set up storage monitoring
        self.storage_monitor.set_thresholds(
            warning_percent=80,   # Warn at 80% full
            critical_percent=90   # Critical at 90% full
        )

        # Configure for intermittent connectivity
        self.dispatcher.configure_connectivity_handling(
            offline_queue_max_size=10000,     # Queue up to 10k when offline
            reconnect_backoff_max=300,        # Max 5 minute backoff
            bulk_send_on_reconnect=True       # Send in batches when reconnected
        )
```

**Deliverables Phase 3:**
- [ ] Hardened magic link implementation with single-use tokens
- [ ] Advanced queue analytics and management tools
- [ ] Environmental optimizations for RV deployment
- [ ] Storage monitoring and auto-cleanup
- [ ] Connectivity-aware queue processing
- [ ] Security audit and penetration testing
- [ ] Performance optimization for embedded hardware

**Success Criteria:**
- Security audit passes with no critical findings
- Magic links are single-use with minimal privilege scope
- System handles offline periods gracefully
- Storage usage remains bounded under all conditions
- Queue analytics provide actionable operational insights

---

### Phase 4: Migration & Rollout (Weeks 7-8)
**Goal**: Safe deployment with rollback capability and production validation

#### 4.1 Feature Flag Migration Strategy
```yaml
# Updated feature_flags.yaml
notifications:
  enabled: true
  core: false
  depends_on: [persistence]
  description: "Multi-channel notification system with persistent queue"
  settings:
    use_legacy_sync: false      # Phase 4: Switch to false
    queue_enabled: true         # New queue-based system
    max_queue_size: 10000      # Safety limit
    dispatcher_workers: 2       # Number of background workers
    rate_limit_per_minute: 100  # Rate limiting
    debounce_minutes: 15       # Debounce same notifications
  channels:
    email_enabled: true
    slack_enabled: false
    discord_enabled: false
    pushover_enabled: false    # Phase 4: Enable as needed
```

#### 4.2 Gradual Migration Process
```python
class NotificationMigrationManager:
    """Manages migration from legacy to modern system"""

    def __init__(self):
        self.legacy_manager = LegacyNotificationManager()
        self.modern_manager = SafeNotificationManager()
        self.migration_percentage = 0  # Start at 0%

    async def send_notification(self, message: str, **kwargs) -> bool:
        """Route notifications based on migration percentage"""

        # Determine routing based on hash of message for consistency
        message_hash = hash(message + str(kwargs.get('level', '')))
        use_modern = (message_hash % 100) < self.migration_percentage

        if use_modern:
            try:
                result = await self.modern_manager.notify(message, **kwargs)

                # Also send via legacy for comparison (shadow mode)
                if self.config.shadow_mode_enabled:
                    asyncio.create_task(
                        self.legacy_manager.notify(message, **kwargs)
                    )

                return result
            except Exception as e:
                logger.error("Modern notification failed, falling back", exc_info=e)
                # Fallback to legacy
                return await self.legacy_manager.notify(message, **kwargs)
        else:
            return await self.legacy_manager.notify(message, **kwargs)

    def set_migration_percentage(self, percentage: int):
        """Update migration percentage (0-100)"""
        self.migration_percentage = max(0, min(100, percentage))
        logger.info(f"Migration percentage set to {percentage}%")
```

#### 4.3 Production Rollout Plan

**Week 7: Shadow Deployment**
```bash
# Day 1: Deploy with 0% traffic to modern system
COACHIQ_NOTIFICATIONS__MIGRATION_PERCENTAGE=0
COACHIQ_NOTIFICATIONS__SHADOW_MODE_ENABLED=true

# Day 3: 10% traffic if no issues detected
COACHIQ_NOTIFICATIONS__MIGRATION_PERCENTAGE=10

# Day 5: 25% traffic if metrics look good
COACHIQ_NOTIFICATIONS__MIGRATION_PERCENTAGE=25

# Day 7: 50% traffic if system stable
COACHIQ_NOTIFICATIONS__MIGRATION_PERCENTAGE=50
```

**Week 8: Full Migration**
```bash
# Day 1: 75% traffic
COACHIQ_NOTIFICATIONS__MIGRATION_PERCENTAGE=75

# Day 3: 90% traffic
COACHIQ_NOTIFICATIONS__MIGRATION_PERCENTAGE=90

# Day 5: 100% traffic - full migration
COACHIQ_NOTIFICATIONS__MIGRATION_PERCENTAGE=100
COACHIQ_NOTIFICATIONS__SHADOW_MODE_ENABLED=false

# Day 7: Remove legacy system
COACHIQ_NOTIFICATIONS__USE_LEGACY_SYNC=false
```

#### 4.4 Monitoring & Rollback Plan
```python
class MigrationMonitor:
    """Automated monitoring during migration"""

    async def check_migration_health(self) -> bool:
        """Automated health check for migration"""

        metrics = await self.get_migration_metrics()

        # Rollback triggers
        if (
            metrics["error_rate"] > 0.05 or          # > 5% error rate
            metrics["latency_p95"] > 30000 or        # > 30s latency
            metrics["queue_depth"] > 5000 or         # Queue backing up
            metrics["dlq_growth_rate"] > 100         # DLQ growing fast
        ):
            logger.critical("Migration health check failed", extra=metrics)
            await self.trigger_rollback()
            return False

        return True

    async def trigger_rollback(self):
        """Emergency rollback to legacy system"""

        # Immediately switch back to legacy
        await self.config_manager.update_setting(
            "notifications.migration_percentage", 0
        )

        # Alert operations team
        await self.alert_manager.send_critical_alert(
            "Notification system rolled back to legacy due to health check failure"
        )

        # Drain modern queue through legacy system
        await self.drain_modern_queue_to_legacy()
```

**Deliverables Phase 4:**
- [ ] Migration manager with percentage-based rollout
- [ ] Shadow mode for comparison testing
- [ ] Automated health monitoring during migration
- [ ] Emergency rollback procedures
- [ ] Production deployment scripts
- [ ] Monitoring dashboards for migration metrics
- [ ] Documentation for operations team

**Success Criteria:**
- Zero-downtime migration with gradual traffic shift
- Rollback capability tested and functional
- All legacy functionality preserved during migration
- Performance equals or exceeds legacy system
- Operations team trained on new system

---

## Risk Mitigation Strategies

### High-Risk Areas
1. **Database Corruption**: SQLite with WAL mode, regular backups
2. **Queue Growth**: Monitoring, alerting, and automatic cleanup
3. **Memory Leaks**: Comprehensive testing, memory profiling
4. **Network Failures**: Offline queue, reconnection logic
5. **Security Vulnerabilities**: Regular audits, input sanitization

### Rollback Procedures
- **Phase 1-2**: Feature flag to disable queue, fallback to original
- **Phase 3**: Config rollback to previous security settings
- **Phase 4**: Migration percentage to 0%, drain modern queue

### Testing Strategy
- **Unit Tests**: All queue operations, rate limiting, sanitization
- **Integration Tests**: End-to-end notification flows
- **Load Tests**: Queue performance under high volume
- **Chaos Engineering**: Simulated failures, network partitions
- **Security Tests**: Template injection, token validation

## Resource Requirements

### Development Team
- **1 Senior Backend Developer** (Phases 1-4): Queue implementation, service integration
- **1 DevOps Engineer** (Phases 2-4): Monitoring, deployment, migration
- **1 Security Engineer** (Phase 3): Security review, penetration testing

### Infrastructure
- **Development Environment**: Docker setup with SQLite
- **Staging Environment**: Production-like with real notification services
- **Monitoring**: Grafana dashboards, Prometheus metrics
- **Testing**: Load testing environment with simulated CAN traffic

### Timeline Summary
- **Phase 1**: 2 weeks - Foundation (Queue, Safety)
- **Phase 2**: 2 weeks - Integration (Service, Monitoring)
- **Phase 3**: 2 weeks - Security (Hardening, Features)
- **Phase 4**: 2 weeks - Migration (Rollout, Production)

**Total Duration**: 8 weeks with overlapping phases for acceleration

## Success Metrics

### Technical Metrics
- **Reliability**: 99.9% notification delivery rate
- **Performance**: <5 second average processing time
- **Safety**: Zero blocking operations on main thread
- **Security**: Zero critical vulnerabilities in security audit

### Operational Metrics
- **Uptime**: 99.95% system availability
- **Recovery**: <5 minute mean time to recovery
- **Storage**: Bounded growth with automatic cleanup
- **Monitoring**: Complete observability of all components

This modernization plan transforms the notification system into a production-ready, safety-critical component suitable for RV-C vehicle environments while maintaining all existing functionality and adding advanced operational capabilities.
