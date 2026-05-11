"""
CAN-TX rate limiter (CoachIQ outbound bus politeness).

CoachIQ does NOT directly control RV hardware. It emits RV-C / J1939 frames
that a downstream OEM controller (e.g. Firefly MIRA) decides whether to act
on. A buggy loop or malicious request that hot-loops entity-control commands
could flood the shared bus and degrade the OEM controller's ability to
service legitimate traffic. This is the realistic "safety" concern: not
"the brakes release", but "we are an antisocial neighbor on the bus."

This module implements a token-bucket rate limiter that the CAN writer task
applies to every outbound frame, plus optional per-arbitration-id buckets
so a runaway loop on one DGN can't crowd out unrelated frames.

Usage:

    limiter = CANTxRateLimiter(
        global_rate_per_sec=200.0,
        global_burst=400,
        per_id_rate_per_sec=20.0,
        per_id_burst=40,
    )
    await limiter.acquire(arbitration_id=msg.arbitration_id)
    bus.send(msg)

The limiter blocks (does not drop) when over budget. RV-C control commands
are typically idempotent and re-sent every few hundred ms by the spec, so
adding latency is preferable to dropping frames.

For a deeper-dive justification see README.md > "System role and architecture"
and docs/SECURITY_BEST_PRACTICES.md > "Threat model".
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# Sensible defaults for an RV-C bus shared with an OEM multiplex panel.
# RV-C nodes typically broadcast at 10-100 ms intervals per DGN. CoachIQ's
# normal traffic is bursts of a handful of frames in response to a UI click.
# Anything sustained above ~200 frames/s from CoachIQ alone is almost
# certainly a bug.
DEFAULT_GLOBAL_RATE_PER_SEC = 200.0
DEFAULT_GLOBAL_BURST = 400  # ~2 seconds of headroom
DEFAULT_PER_ID_RATE_PER_SEC = 20.0
DEFAULT_PER_ID_BURST = 40
# Cap on the per-ID bucket cache so a malicious caller can't OOM us by
# probing many distinct arbitration IDs.
MAX_TRACKED_ARBITRATION_IDS = 4096


@dataclass
class _Bucket:
    """Mutable token-bucket state. Not thread-safe; protected by the limiter's lock."""

    capacity: float
    tokens: float
    refill_per_sec: float
    last_refill: float = field(default_factory=time.monotonic)

    def refill(self, now: float) -> None:
        elapsed = max(0.0, now - self.last_refill)
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_sec)
        self.last_refill = now

    def take_or_wait(self, now: float) -> float:
        """Consume one token; return seconds to wait if not enough.

        Returns 0.0 when a token was consumed immediately.
        """
        self.refill(now)
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return 0.0
        deficit = 1.0 - self.tokens
        return deficit / self.refill_per_sec if self.refill_per_sec > 0 else float("inf")


@dataclass
class CANTxRateLimiterMetrics:
    """Lightweight counters for observability / dashboards."""

    total_acquires: int = 0
    total_waits: int = 0
    total_wait_seconds: float = 0.0
    last_burst_logged_at: float = 0.0
    tracked_arbitration_ids: int = 0


class CANTxRateLimiter:
    """Token-bucket rate limiter for the CAN writer task.

    Applies a single global bucket plus per-arbitration-id buckets. Both must
    have tokens for an acquire() to succeed; if either is empty the call
    blocks until the longer of the two waits has elapsed.
    """

    def __init__(  # noqa: PLR0913 - token-bucket needs global+per-id rate/burst pair, intentional API
        self,
        global_rate_per_sec: float = DEFAULT_GLOBAL_RATE_PER_SEC,
        global_burst: int = DEFAULT_GLOBAL_BURST,
        per_id_rate_per_sec: float = DEFAULT_PER_ID_RATE_PER_SEC,
        per_id_burst: int = DEFAULT_PER_ID_BURST,
        max_tracked_ids: int = MAX_TRACKED_ARBITRATION_IDS,
        burst_warn_interval_sec: float = 10.0,
    ) -> None:
        if global_rate_per_sec <= 0:
            msg = "global_rate_per_sec must be > 0"
            raise ValueError(msg)
        if per_id_rate_per_sec <= 0:
            msg = "per_id_rate_per_sec must be > 0"
            raise ValueError(msg)

        self._global = _Bucket(
            capacity=float(global_burst),
            tokens=float(global_burst),
            refill_per_sec=global_rate_per_sec,
        )
        self._per_id_rate = per_id_rate_per_sec
        self._per_id_capacity = float(per_id_burst)
        self._max_tracked_ids = max_tracked_ids
        self._burst_warn_interval = burst_warn_interval_sec

        # OrderedDict gives us LRU eviction for the per-id cache cap.
        self._buckets: OrderedDict[int, _Bucket] = OrderedDict()

        self._lock = asyncio.Lock()
        self.metrics = CANTxRateLimiterMetrics()

    def _get_bucket_locked(self, arbitration_id: int, now: float) -> _Bucket:
        bucket = self._buckets.get(arbitration_id)
        if bucket is None:
            bucket = _Bucket(
                capacity=self._per_id_capacity,
                tokens=self._per_id_capacity,
                refill_per_sec=self._per_id_rate,
                last_refill=now,
            )
            self._buckets[arbitration_id] = bucket
            # Evict LRU if we're tracking too many distinct IDs.
            while len(self._buckets) > self._max_tracked_ids:
                self._buckets.popitem(last=False)
        else:
            self._buckets.move_to_end(arbitration_id)
        self.metrics.tracked_arbitration_ids = len(self._buckets)
        return bucket

    async def acquire(self, arbitration_id: int) -> None:
        """Block until both the global and per-id buckets allow one frame.

        Always consumes exactly one token from each bucket on success.
        Will not raise on contention; will always eventually return.
        """
        # Loop because a sleep can be racy if many callers are queued: after
        # we wake, the bucket may have already been drained again by another
        # acquire that won the lock first. Re-check until we actually get
        # both tokens.
        while True:
            wait_seconds = 0.0
            async with self._lock:
                now = time.monotonic()
                global_wait = self._global.take_or_wait(now)
                per_id_bucket = self._get_bucket_locked(arbitration_id, now)
                per_id_wait = per_id_bucket.take_or_wait(now)

                if global_wait == 0.0 and per_id_wait == 0.0:
                    self.metrics.total_acquires += 1
                    return

                # We didn't actually take both tokens. take_or_wait already
                # consumed from whichever bucket had >= 1 token and returned
                # 0; but take_or_wait only returns 0 when it consumed, so if
                # we're here at least one bucket returned >0. Refund any
                # token we DID consume so the counters stay correct.
                if global_wait == 0.0:
                    self._global.tokens += 1.0
                if per_id_wait == 0.0:
                    per_id_bucket.tokens += 1.0

                wait_seconds = max(global_wait, per_id_wait)
                self.metrics.total_waits += 1
                self.metrics.total_wait_seconds += wait_seconds

                if (now - self.metrics.last_burst_logged_at) > self._burst_warn_interval:
                    self.metrics.last_burst_logged_at = now
                    logger.warning(
                        "CAN TX rate limit reached (global=%s/s, per-id=%s/s); "
                        "delaying frame for arbitration_id=0x%X by %.3fs",
                        self._global.refill_per_sec,
                        self._per_id_rate,
                        arbitration_id,
                        wait_seconds,
                    )

            # Sleep OUTSIDE the lock so other producers can still update the
            # bucket while we wait.
            await asyncio.sleep(wait_seconds)


# Module-level default limiter so producers / writers share state without
# having to thread an instance through every call site. Tests construct
# their own CANTxRateLimiter and bypass this.
_default_limiter: CANTxRateLimiter | None = None


def get_default_can_tx_rate_limiter() -> CANTxRateLimiter:
    """Return the process-wide CAN TX rate limiter (lazy-initialized)."""
    global _default_limiter  # noqa: PLW0603 - intentional module-level singleton
    if _default_limiter is None:
        _default_limiter = CANTxRateLimiter()
    return _default_limiter


def reset_default_can_tx_rate_limiter() -> None:
    """Reset the module-level limiter (intended for tests)."""
    global _default_limiter  # noqa: PLW0603 - test helper
    _default_limiter = None
