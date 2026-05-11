"""Tests for the CAN-TX rate limiter."""

import asyncio
import time

import pytest

from backend.integrations.can.tx_rate_limiter import (
    CANTxRateLimiter,
    get_default_can_tx_rate_limiter,
    reset_default_can_tx_rate_limiter,
)


class TestConstruction:
    def test_rejects_non_positive_global_rate(self):
        with pytest.raises(ValueError, match="global_rate"):
            CANTxRateLimiter(global_rate_per_sec=0)

    def test_rejects_non_positive_per_id_rate(self):
        with pytest.raises(ValueError, match="per_id_rate"):
            CANTxRateLimiter(per_id_rate_per_sec=-1)


class TestBurstCapacity:
    """A burst up to capacity should pass through immediately."""

    @pytest.mark.asyncio
    async def test_burst_within_capacity_does_not_wait(self):
        limiter = CANTxRateLimiter(
            global_rate_per_sec=1.0,  # very slow refill so wait would be obvious
            global_burst=10,
            per_id_rate_per_sec=1.0,
            per_id_burst=10,
        )

        start = time.monotonic()
        for _ in range(10):
            await limiter.acquire(arbitration_id=0x18EFFFFF)
        elapsed = time.monotonic() - start

        # 10 acquires from full bucket should be effectively instant.
        assert elapsed < 0.1
        assert limiter.metrics.total_acquires == 10
        assert limiter.metrics.total_waits == 0


class TestGlobalRateLimit:
    """Once the global bucket is empty, acquires must wait for refill."""

    @pytest.mark.asyncio
    async def test_acquire_beyond_burst_blocks(self):
        limiter = CANTxRateLimiter(
            global_rate_per_sec=10.0,  # one token every 100ms
            global_burst=2,
            per_id_rate_per_sec=1000.0,  # per-id is effectively unconstrained here
            per_id_burst=1000,
        )

        # Drain the global burst.
        await limiter.acquire(0x100)
        await limiter.acquire(0x101)

        # Third acquire should wait approximately one refill period (100ms).
        start = time.monotonic()
        await limiter.acquire(0x102)
        elapsed = time.monotonic() - start

        # Allow some slack on either side; refill time is 1/10s.
        assert 0.05 < elapsed < 0.5
        assert limiter.metrics.total_waits == 1


class TestPerIdRateLimit:
    """A flood on one ID must not consume budget from other IDs (and vice versa)."""

    @pytest.mark.asyncio
    async def test_per_id_bucket_is_independent(self):
        limiter = CANTxRateLimiter(
            global_rate_per_sec=1000.0,  # global is generous
            global_burst=1000,
            per_id_rate_per_sec=10.0,
            per_id_burst=2,
        )

        # Drain ID A's per-id bucket.
        await limiter.acquire(0xAAA)
        await limiter.acquire(0xAAA)

        # ID B should still be acquirable instantly.
        start = time.monotonic()
        await limiter.acquire(0xBBB)
        elapsed = time.monotonic() - start
        assert elapsed < 0.05
        assert limiter.metrics.total_waits == 0

        # ID A's third acquire must wait for refill.
        start = time.monotonic()
        await limiter.acquire(0xAAA)
        elapsed = time.monotonic() - start
        assert 0.05 < elapsed < 0.5
        assert limiter.metrics.total_waits == 1


class TestPerIdLruEviction:
    """The per-id cache must not grow unboundedly under attacker probing."""

    @pytest.mark.asyncio
    async def test_per_id_cache_evicts_lru_above_max_tracked(self):
        limiter = CANTxRateLimiter(
            global_rate_per_sec=10000.0,
            global_burst=10000,
            per_id_rate_per_sec=1000.0,
            per_id_burst=10,
            max_tracked_ids=4,
        )

        for arb_id in range(10):
            await limiter.acquire(arb_id)

        # The cache should hold no more than max_tracked_ids buckets.
        assert limiter.metrics.tracked_arbitration_ids == 4


class TestModuleLevelDefault:
    def teardown_method(self):
        reset_default_can_tx_rate_limiter()

    def test_default_limiter_is_singleton(self):
        first = get_default_can_tx_rate_limiter()
        second = get_default_can_tx_rate_limiter()
        assert first is second

    def test_reset_returns_fresh_instance(self):
        first = get_default_can_tx_rate_limiter()
        reset_default_can_tx_rate_limiter()
        second = get_default_can_tx_rate_limiter()
        assert first is not second


class TestConcurrency:
    """Multiple producers contending must all succeed; no double-acquires."""

    @pytest.mark.asyncio
    async def test_concurrent_acquires_are_serialized_correctly(self):
        limiter = CANTxRateLimiter(
            global_rate_per_sec=1000.0,
            global_burst=20,
            per_id_rate_per_sec=1000.0,
            per_id_burst=20,
        )

        async def producer(arb_id: int) -> None:
            for _ in range(5):
                await limiter.acquire(arb_id)

        await asyncio.gather(
            producer(0x100),
            producer(0x101),
            producer(0x102),
            producer(0x103),
        )

        # Every producer's 5 acquires must have been counted.
        assert limiter.metrics.total_acquires == 20
