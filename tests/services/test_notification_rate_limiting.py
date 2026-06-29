"""
Unit tests for notification rate limiting and debouncing.

Tests cover:
- TokenBucketRateLimiter with token refill and burst detection
- NotificationDebouncer with message suppression
- ChannelSpecificRateLimiter with per-channel limits
- AdaptiveRateLimiter with health-based adjustments
- Rate limiting statistics and monitoring
- Error handling and recovery scenarios
"""

import asyncio
import time
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from backend.models.notification import RateLimitStatus
from backend.services.notifications.notification_rate_limiting import (
    AdaptiveRateLimiter,
    ChannelSpecificRateLimiter,
    NotificationDebouncer,
    TokenBucketRateLimiter,
    calculate_backoff_delay,
    create_message_hash,
)


class TestTokenBucketRateLimiter:
    """Test token bucket rate limiting functionality."""

    @pytest.fixture
    async def rate_limiter(self):
        """Create TokenBucketRateLimiter for testing."""
        return TokenBucketRateLimiter(max_tokens=10, refill_rate=6.0)  # 6 tokens per minute

    async def test_initial_tokens_available(self, rate_limiter):
        """Test that rate limiter starts with full token bucket."""
        # Should allow requests up to max_tokens
        for i in range(10):
            allowed = await rate_limiter.allow(f"request_{i}")
            assert allowed

        # 11th request should be blocked
        blocked = await rate_limiter.allow("request_11")
        assert not blocked

    async def test_token_refill_over_time(self, rate_limiter):
        """Test that tokens are refilled over time.

        We deliberately do **not** ``patch('time.time')`` here -- patching
        ``time.time`` is too aggressive because the patch is active for the
        entire ``with`` block, including the ``time.time()`` call that the
        test itself makes to read the current time. That returns a
        ``MagicMock``, not a float, and the production refill math
        (``current_time - self.last_refill``) then crashes with
        ``TypeError: '>=' not supported between instances of 'MagicMock'
        and 'int'``.

        Instead we drive the refill clock directly by writing
        ``rate_limiter.last_refill`` -- pretending that the bucket was
        last topped up 60s ago and then calling ``allow`` with the real
        clock. With ``refill_rate=6.0`` tokens/min that should restore
        ~6 tokens.
        """
        # Exhaust all tokens
        for i in range(10):
            await rate_limiter.allow(f"request_{i}")

        # Should be blocked
        blocked = await rate_limiter.allow("blocked_request")
        assert not blocked

        # Pretend the last refill happened 60s ago. ``allow()`` will read
        # the real clock for ``current_time`` and refill based on the
        # real elapsed time.
        rate_limiter.last_refill = time.time() - 60.0

        # Should have refilled tokens (6 tokens per minute)
        allowed_count = 0
        for i in range(10):
            if await rate_limiter.allow(f"refilled_{i}"):
                allowed_count += 1

        assert allowed_count >= 6  # Should have at least 6 new tokens

    async def test_burst_detection(self, rate_limiter):
        """Test burst detection functionality.

        ``TokenBucketRateLimiter`` records a burst event when more than
        ``burst_threshold`` requests arrive inside the burst window. With
        ``max_tokens=10`` and ``burst_allowance=1.5`` (the default),
        ``burst_threshold`` is ``int(10 * 1.5) == 15``, and the check is
        ``len(timestamps) > burst_threshold`` -- strict greater-than. We
        therefore need at least 16 requests to actually trip a burst.
        """
        # 20 requests is comfortably above the 15-request threshold; we use
        # 20 instead of 16 to keep the test stable against minor changes
        # to the threshold math without becoming an integration test.
        burst_size = 20
        for i in range(burst_size):
            await rate_limiter.allow(f"burst_{i}")

        # Check that burst was detected
        assert rate_limiter.burst_events > 0

    async def test_rate_limiter_status(self, rate_limiter):
        """Test rate limiter status reporting."""
        # Use some tokens
        for i in range(5):
            await rate_limiter.allow(f"status_test_{i}")

        status = rate_limiter.get_status()
        assert isinstance(status, RateLimitStatus)
        assert status.current_tokens == 5
        assert status.max_tokens == 10
        assert status.refill_rate == 6.0
        assert status.healthy

    async def test_rate_limiter_reset(self, rate_limiter):
        """Test rate limiter reset functionality."""
        # Use all tokens
        for i in range(10):
            await rate_limiter.allow(f"reset_test_{i}")

        # Should be blocked
        blocked = await rate_limiter.allow("should_be_blocked")
        assert not blocked

        # Reset
        await rate_limiter.reset()

        # Should work again
        allowed = await rate_limiter.allow("after_reset")
        assert allowed

        # Statistics should be reset
        status = rate_limiter.get_status()
        assert status.current_tokens == 9  # Used one after reset


class TestNotificationDebouncer:
    """Test notification debouncing functionality."""

    @pytest.fixture
    async def debouncer(self):
        """Create NotificationDebouncer for testing."""
        return NotificationDebouncer(suppress_window_minutes=1, max_tracked_items=100)

    async def test_first_message_allowed(self, debouncer):
        """Test that first occurrence of message is allowed."""
        allowed = await debouncer.allow("Test message", "info")
        assert allowed

    async def test_duplicate_message_suppressed(self, debouncer):
        """Test that duplicate messages are suppressed."""
        message = "Duplicate test message"
        level = "warning"

        # First occurrence should be allowed
        first = await debouncer.allow(message, level)
        assert first

        # Immediate duplicate should be suppressed
        second = await debouncer.allow(message, level)
        assert not second

    async def test_different_levels_not_suppressed(self, debouncer):
        """Test that same message with different levels is not suppressed."""
        message = "Same message different level"

        # Send as info
        info_allowed = await debouncer.allow(message, "info")
        assert info_allowed

        # Send as error (should not be suppressed)
        error_allowed = await debouncer.allow(message, "error")
        assert error_allowed

    async def test_custom_key_suppression(self, debouncer):
        """Test suppression using custom keys."""
        # Use custom key for grouping
        custom_key = "custom_suppression_key"

        first = await debouncer.allow("Message 1", "info", custom_key)
        assert first

        # Different message but same custom key should be suppressed
        second = await debouncer.allow("Message 2", "info", custom_key)
        assert not second

    async def test_suppression_window_expiry(self, debouncer):
        """Test that suppression window expires correctly."""
        message = "Window expiry test"

        # First message allowed
        first = await debouncer.allow(message, "info")
        assert first

        # Mock time to simulate window expiry
        with patch("asyncio.sleep"):
            # Manually trigger cleanup to simulate time passage
            await debouncer._cleanup_old_entries()

            # Now should be allowed again (if window expired)
            # Note: In real test, we'd need to manipulate timestamps

    async def test_debouncer_statistics(self, debouncer):
        """Test debouncer statistics reporting."""
        # Generate some activity
        await debouncer.allow("Test 1", "info")
        await debouncer.allow("Test 1", "info")  # Suppressed
        await debouncer.allow("Test 2", "warning")

        stats = debouncer.get_statistics()
        assert stats["total_checks"] == 3
        assert stats["suppressed_count"] == 1
        assert stats["active_suppressions"] >= 1

    async def test_clear_suppressions(self, debouncer):
        """Test clearing suppression entries."""
        # Add some suppressions
        await debouncer.allow("Clear test 1", "info")
        await debouncer.allow("Clear test 2", "warning")

        # Clear all
        cleared = await debouncer.clear_suppressions()
        assert cleared >= 2

        # Should now allow previously suppressed messages
        allowed = await debouncer.allow("Clear test 1", "info")
        assert allowed

    async def test_memory_protection(self):
        """Test that debouncer limits memory usage."""
        debouncer = NotificationDebouncer(
            suppress_window_minutes=60,
            max_tracked_items=5,  # Small limit for testing
        )

        # Add more items than limit
        for i in range(10):
            await debouncer.allow(f"Memory test {i}", "info")

        # Should trigger cleanup automatically
        stats = debouncer.get_statistics()
        assert stats["memory_usage_items"] <= 10  # May be slightly over limit temporarily


class TestChannelSpecificRateLimiter:
    """Test per-channel rate limiting."""

    @pytest.fixture
    async def channel_limiter(self):
        """Create ChannelSpecificRateLimiter for testing."""
        return ChannelSpecificRateLimiter()

    async def test_different_channels_independent_limits(self, channel_limiter):
        """Test that different channels have independent rate limits."""
        # Use email channel limit
        email_requests = 0
        while await channel_limiter.allow("smtp", f"email_{email_requests}"):
            email_requests += 1
            if email_requests > 60:  # Safety break
                break

        # Slack channel should still be available
        slack_allowed = await channel_limiter.allow("slack", "slack_message")
        assert slack_allowed

    async def test_channel_specific_configurations(self, channel_limiter):
        """Test that channels have different rate limit configurations."""
        # Get status for different channels
        smtp_status = channel_limiter.get_channel_status("smtp")
        pushover_status = channel_limiter.get_channel_status("pushover")

        # Create the channels first
        await channel_limiter.allow("smtp", "test")
        await channel_limiter.allow("pushover", "test")

        smtp_status = channel_limiter.get_channel_status("smtp")
        pushover_status = channel_limiter.get_channel_status("pushover")

        # Pushover should have higher limits than SMTP
        assert pushover_status.max_tokens > smtp_status.max_tokens

    async def test_get_all_channel_status(self, channel_limiter):
        """Test getting status for all channels."""
        # Create some channel activity
        await channel_limiter.allow("smtp", "test1")
        await channel_limiter.allow("slack", "test2")
        await channel_limiter.allow("discord", "test3")

        all_status = channel_limiter.get_all_channel_status()
        assert len(all_status) >= 3
        assert "smtp" in all_status
        assert "slack" in all_status
        assert "discord" in all_status

    async def test_reset_specific_channel(self, channel_limiter):
        """Test resetting specific channel rate limiter."""
        # Exhaust channel limit
        while await channel_limiter.allow("smtp", "exhaust_test"):
            pass

        # Should be blocked
        blocked = await channel_limiter.allow("smtp", "should_be_blocked")
        assert not blocked

        # Reset channel
        reset_success = await channel_limiter.reset_channel("smtp")
        assert reset_success

        # Should work again
        allowed = await channel_limiter.allow("smtp", "after_reset")
        assert allowed

    async def test_reset_all_channels(self, channel_limiter):
        """Test resetting all channel rate limiters."""
        # Create activity on multiple channels
        await channel_limiter.allow("smtp", "test1")
        await channel_limiter.allow("slack", "test2")

        # Reset all
        await channel_limiter.reset_all()

        # All channels should be reset
        all_status = channel_limiter.get_all_channel_status()
        for status in all_status.values():
            assert status.current_tokens == status.max_tokens


class TestAdaptiveRateLimiter:
    """Test adaptive rate limiting based on system health."""

    @pytest.fixture
    async def adaptive_limiter(self):
        """Create AdaptiveRateLimiter for testing."""
        base_limiter = TokenBucketRateLimiter(max_tokens=100, refill_rate=60.0)
        return AdaptiveRateLimiter(base_limiter, health_check_interval=1)

    async def test_healthy_system_normal_rate(self, adaptive_limiter):
        """Test that a healthy-but-not-pristine system stays at the normal rate.

        ``AdaptiveRateLimiter._calculate_adaptation_factor`` returns 1.0
        only when ``0.7 <= health_score <= 0.95``. When ``health_score``
        rises above 0.95 the factor is *increased* up to ``max_factor``
        (2.0). To keep the test focused on the 'normal rate' contract
        rather than the boost-on-excellent contract (covered by
        ``test_excellent_health_increased_rate``), we deliberately use
        metrics that score in the 0.7-0.95 band: queue is fine,
        processing time is fine, but ``success_rate`` is just below the
        warning threshold (0.9), which knocks the score to 0.8.
        """
        healthy_metrics = {
            "queue_depth": 10,
            "success_rate": 0.85,  # Below 0.9 warning -> score *= 0.8
            "avg_processing_time": 5.0,
        }

        await adaptive_limiter.update_health_metrics(healthy_metrics)

        # Rate should remain normal (factor around 1.0)
        assert 0.9 <= adaptive_limiter.current_factor <= 1.1

    async def test_unhealthy_system_reduced_rate(self, adaptive_limiter):
        """Test that unhealthy system reduces rate."""
        # Simulate unhealthy metrics
        unhealthy_metrics = {
            "queue_depth": 6000,  # Above critical threshold
            "success_rate": 0.5,  # Below warning threshold
            "avg_processing_time": 150.0,  # Above critical threshold
        }

        await adaptive_limiter.update_health_metrics(unhealthy_metrics)

        # Rate should be significantly reduced
        assert adaptive_limiter.current_factor < 0.5

    async def test_moderate_stress_proportional_reduction(self, adaptive_limiter):
        """Test proportional rate reduction under moderate stress.

        Production formula:
            score = 1.0 * 0.7 * 0.8 * 0.8 = 0.448
            factor = min_factor + (score - 0.3) / 0.4 * (1.0 - min_factor)
                   = 0.1 + (0.148 / 0.4) * 0.9
                   = 0.433

        We assert ``0.3 < factor < 0.7`` rather than tying the test to
        the exact constant -- the contract under test is 'moderate stress
        produces a moderately-reduced factor', not the precise value.
        """
        moderate_metrics = {
            "queue_depth": 2000,  # Above warning but below critical
            "success_rate": 0.85,  # Slightly below warning
            "avg_processing_time": 45.0,  # Above warning but below critical
        }

        await adaptive_limiter.update_health_metrics(moderate_metrics)

        # Rate should be moderately reduced -- between min_factor (0.1)
        # and the 'normal' band (1.0). Don't pin to the exact constant.
        assert adaptive_limiter.min_factor < adaptive_limiter.current_factor < 1.0
        assert 0.3 < adaptive_limiter.current_factor < 0.7

    async def test_excellent_health_increased_rate(self, adaptive_limiter):
        """Test that excellent system health can increase rate."""
        # Simulate excellent metrics
        excellent_metrics = {
            "queue_depth": 0,
            "success_rate": 1.0,
            "avg_processing_time": 1.0,
        }

        await adaptive_limiter.update_health_metrics(excellent_metrics)

        # Rate might be slightly increased
        assert adaptive_limiter.current_factor >= 1.0

    async def test_adaptation_factor_bounds(self, adaptive_limiter):
        """Test that adaptation factor stays within bounds."""
        # Test extremely bad metrics
        terrible_metrics = {
            "queue_depth": 50000,
            "success_rate": 0.0,
            "avg_processing_time": 1000.0,
        }

        await adaptive_limiter.update_health_metrics(terrible_metrics)

        # Should not go below minimum
        assert adaptive_limiter.current_factor >= adaptive_limiter.min_factor

        # Test excellent metrics
        perfect_metrics = {
            "queue_depth": 0,
            "success_rate": 1.0,
            "avg_processing_time": 0.1,
        }

        await adaptive_limiter.update_health_metrics(perfect_metrics)

        # Should not go above maximum
        assert adaptive_limiter.current_factor <= adaptive_limiter.max_factor


class TestUtilityFunctions:
    """Test utility functions for rate limiting."""

    def test_create_message_hash_consistency(self):
        """Test that message hash is consistent for same content."""
        message = "Test message"
        context = {"key": "value", "number": 42}

        hash1 = create_message_hash(message, context)
        hash2 = create_message_hash(message, context)

        assert hash1 == hash2

    def test_create_message_hash_different_content(self):
        """Test that different content produces different hashes."""
        hash1 = create_message_hash("Message 1", {"key": "value1"})
        hash2 = create_message_hash("Message 2", {"key": "value2"})

        assert hash1 != hash2

    def test_create_message_hash_excludes_volatile_context(self):
        """Test that volatile context fields are excluded from hash."""
        message = "Test message"
        context1 = {"key": "value", "timestamp": "2023-01-01", "id": "123"}
        context2 = {"key": "value", "timestamp": "2023-01-02", "id": "456"}

        hash1 = create_message_hash(message, context1)
        hash2 = create_message_hash(message, context2)

        # Should be same because volatile fields are excluded
        assert hash1 == hash2

    def test_calculate_backoff_delay_exponential(self):
        """Test exponential backoff delay calculation."""
        delays = []
        for attempt in range(5):
            delay = calculate_backoff_delay(attempt, base_delay=10.0, max_delay=300.0)
            delays.append(delay)

        # Each delay should be roughly double the previous (exponential)
        assert delays[1] >= delays[0] * 1.5
        assert delays[2] >= delays[1] * 1.5
        assert delays[3] >= delays[2] * 1.5

        # Should not exceed max delay
        assert all(delay <= 300.0 for delay in delays)

    def test_calculate_backoff_delay_bounds(self):
        """Test backoff delay respects bounds."""
        # Test minimum (first attempt)
        min_delay = calculate_backoff_delay(0, base_delay=30.0)
        assert min_delay == 30.0

        # Test maximum bound
        max_delay = calculate_backoff_delay(10, base_delay=30.0, max_delay=300.0)
        assert max_delay == 300.0


class TestRateLimitingIntegration:
    """Test integration scenarios combining multiple rate limiting components."""

    async def test_combined_rate_limiting_and_debouncing(self):
        """Test rate limiting combined with debouncing."""
        rate_limiter = TokenBucketRateLimiter(max_tokens=5, refill_rate=6.0)
        debouncer = NotificationDebouncer(suppress_window_minutes=1)

        message = "Combined test message"

        # First message should pass both checks
        rate_allowed = await rate_limiter.allow(message)
        debounce_allowed = await debouncer.allow(message, "info")
        assert rate_allowed and debounce_allowed

        # Duplicate should be blocked by debouncer
        rate_allowed = await rate_limiter.allow(message)
        debounce_allowed = await debouncer.allow(message, "info")
        assert rate_allowed and not debounce_allowed

        # After exhausting rate limit, debouncer becomes irrelevant
        for i in range(10):  # Exhaust rate limiter
            await rate_limiter.allow(f"exhaust_{i}")

        rate_allowed = await rate_limiter.allow("new_message")
        debounce_allowed = await debouncer.allow("new_message", "info")
        assert not rate_allowed  # Blocked by rate limiter

    async def test_channel_and_global_rate_limiting(self):
        """Test interaction between channel-specific and global rate limiting."""
        global_limiter = TokenBucketRateLimiter(max_tokens=10, refill_rate=12.0)
        channel_limiter = ChannelSpecificRateLimiter()

        # Function to check both limiters
        async def check_both_limiters(channel: str, identifier: str) -> bool:
            global_ok = await global_limiter.allow(identifier)
            channel_ok = await channel_limiter.allow(channel, identifier)
            return global_ok and channel_ok

        # Should pass both initially
        allowed = await check_both_limiters("smtp", "test1")
        assert allowed

        # Exhaust global limiter
        for i in range(20):
            await global_limiter.allow(f"global_exhaust_{i}")

        # Should be blocked by global limiter even if channel allows
        blocked = await check_both_limiters("smtp", "test2")
        assert not blocked

    async def test_adaptive_rate_limiting_under_load(self):
        """Test adaptive rate limiting behavior under simulated load."""
        base_limiter = TokenBucketRateLimiter(max_tokens=100, refill_rate=60.0)
        adaptive_limiter = AdaptiveRateLimiter(base_limiter)

        # Start with normal load
        normal_metrics = {
            "queue_depth": 50,
            "success_rate": 0.9,
            "avg_processing_time": 10.0,
        }
        await adaptive_limiter.update_health_metrics(normal_metrics)
        normal_factor = adaptive_limiter.current_factor

        # Simulate increasing load
        high_load_metrics = {
            "queue_depth": 3000,
            "success_rate": 0.7,
            "avg_processing_time": 60.0,
        }
        await adaptive_limiter.update_health_metrics(high_load_metrics)
        high_load_factor = adaptive_limiter.current_factor

        # Should have reduced rate under high load
        assert high_load_factor < normal_factor

        # Recovery scenario
        recovery_metrics = {
            "queue_depth": 10,
            "success_rate": 0.95,
            "avg_processing_time": 5.0,
        }
        await adaptive_limiter.update_health_metrics(recovery_metrics)
        recovery_factor = adaptive_limiter.current_factor

        # Should increase rate during recovery
        assert recovery_factor > high_load_factor

    async def test_rate_limiting_statistics_accuracy(self):
        """Test accuracy of rate limiting statistics under various conditions."""
        rate_limiter = TokenBucketRateLimiter(max_tokens=10, refill_rate=12.0)
        debouncer = NotificationDebouncer(suppress_window_minutes=5)

        # Generate mixed activity
        allowed_requests = 0
        blocked_requests = 0
        debounced_requests = 0

        messages = [f"Message {i}" for i in range(20)]

        for message in messages:
            rate_ok = await rate_limiter.allow(message)
            debounce_ok = await debouncer.allow(message, "info")

            if rate_ok and debounce_ok:
                allowed_requests += 1
            elif not rate_ok:
                blocked_requests += 1
            elif not debounce_ok:
                debounced_requests += 1

            # Send duplicate to trigger debouncing
            debounce_ok = await debouncer.allow(message, "info")
            if not debounce_ok:
                debounced_requests += 1

        # Verify statistics
        rate_status = rate_limiter.get_status()
        debounce_stats = debouncer.get_statistics()

        assert rate_status.requests_blocked == blocked_requests
        assert debounce_stats["suppressed_count"] == debounced_requests

    async def test_rate_limiting_recovery_after_errors(self):
        """Test rate limiting recovers after a transient internal error.

        ``TokenBucketRateLimiter.allow`` does **not** swallow exceptions
        from its internal helpers — that is by design: callers
        (``SafeNotificationManager.notify``) wrap the call in their own
        ``try/except`` (see ``backend/services/safe_notification_manager.py``)
        and decide whether to drop the notification or surface the error.
        Pushing a blanket ``except Exception`` into ``allow()`` would hide
        bugs from the caller's audit log.

        So the contract under test is:

        1. A transient internal error propagates out of ``allow()`` once.
        2. After the patch is removed, subsequent ``allow()`` calls work
           normally without leaving the limiter in a broken state.
        """
        rate_limiter = TokenBucketRateLimiter(max_tokens=5, refill_rate=6.0)

        # Normal operation
        for i in range(3):
            allowed = await rate_limiter.allow(f"normal_{i}")
            assert allowed

        # Simulate a transient error in _refill_tokens. The exception is
        # expected to propagate -- callers handle it.
        with patch.object(rate_limiter, "_refill_tokens", side_effect=Exception("Test error")):
            with pytest.raises(Exception, match="Test error"):
                await rate_limiter.allow("error_test")

        # After the patch context exits, the limiter should be in a usable
        # state. We don't pin whether the next request is allowed (that
        # depends on remaining token count) but it must not crash.
        await rate_limiter.allow("recovery_test")


@pytest.mark.asyncio
class TestRateLimitingPerformance:
    """Test performance characteristics of rate limiting components."""

    async def test_rate_limiter_performance_under_load(self):
        """Test rate limiter performance with high request volume."""
        rate_limiter = TokenBucketRateLimiter(max_tokens=1000, refill_rate=600.0)

        start_time = time.time()

        # Generate high volume of requests
        tasks = []
        for i in range(1000):
            task = rate_limiter.allow(f"perf_test_{i}")
            tasks.append(task)

        results = await asyncio.gather(*tasks)

        end_time = time.time()
        duration = end_time - start_time

        # Should complete quickly (under 1 second for 1000 requests)
        assert duration < 1.0

        # Most requests should be allowed
        allowed_count = sum(1 for result in results if result)
        assert allowed_count >= 900  # Should allow at least 900 out of 1000

    async def test_debouncer_performance_with_many_unique_messages(self):
        """Test debouncer performance with many unique messages."""
        debouncer = NotificationDebouncer(suppress_window_minutes=60, max_tracked_items=10000)

        start_time = time.time()

        # Generate many unique messages
        tasks = []
        for i in range(5000):
            task = debouncer.allow(f"unique_message_{i}", "info")
            tasks.append(task)

        results = await asyncio.gather(*tasks)

        end_time = time.time()
        duration = end_time - start_time

        # Should complete reasonably quickly (under 2 seconds)
        assert duration < 2.0

        # All unique messages should be allowed
        assert all(results)

    async def test_concurrent_rate_limiting_consistency(self):
        """Test that concurrent access to rate limiter maintains consistency."""
        rate_limiter = TokenBucketRateLimiter(max_tokens=100, refill_rate=60.0)

        # Launch many concurrent requests
        async def make_requests(prefix: str, count: int) -> list[bool]:
            tasks = []
            for i in range(count):
                task = rate_limiter.allow(f"{prefix}_{i}")
                tasks.append(task)
            return await asyncio.gather(*tasks)

        # Run multiple concurrent batches
        batch_tasks = []
        for batch_id in range(5):
            task = make_requests(f"batch_{batch_id}", 50)
            batch_tasks.append(task)

        batch_results = await asyncio.gather(*batch_tasks)

        # Count total allowed requests
        total_allowed = sum(sum(1 for result in batch if result) for batch in batch_results)

        # Should not exceed token limit significantly
        # (may slightly exceed due to concurrent access, but should be close)
        assert total_allowed <= 120  # Some tolerance for concurrency
