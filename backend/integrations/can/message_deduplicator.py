"""
CAN Message Deduplication for Bridged Interfaces

Prevents duplicate processing when using cangw or similar bridges.
"""

import hashlib
import time
from collections import deque
from dataclasses import dataclass
from typing import Dict, Optional, Set


@dataclass
class MessageSignature:
    """Unique signature for a CAN message."""

    can_id: int
    data: bytes
    timestamp: float

    def hash(self) -> str:
        """Generate hash for message comparison."""
        # Include CAN ID and data, but not timestamp or interface
        content = f"{self.can_id:08X}{self.data.hex()}"
        return hashlib.md5(content.encode(), usedforsecurity=False).hexdigest()[:16]


class CANMessageDeduplicator:
    """
    Deduplicates CAN messages when multiple interfaces are bridged.

    Uses a sliding time window to detect and filter duplicate messages
    that appear on multiple interfaces due to bridging.
    """

    def __init__(self, window_ms: int = 50, max_cache_size: int = 10000):
        """
        Initialize deduplicator.

        Args:
            window_ms: Time window in milliseconds to consider messages as duplicates
            max_cache_size: Maximum number of message hashes to cache
        """
        self.window_ms = window_ms
        self.max_cache_size = max_cache_size
        self.message_cache: dict[str, float] = {}
        self.cache_order: deque = deque()

    def is_duplicate(self, can_id: int, data: bytes) -> bool:
        """
        Check if a message is a duplicate.

        Args:
            can_id: CAN identifier
            data: Message data bytes

        Returns:
            True if message is a duplicate within the time window
        """
        current_time = time.time() * 1000  # Convert to milliseconds

        # Create message signature
        sig = MessageSignature(can_id, data, current_time)
        msg_hash = sig.hash()

        # Clean old entries
        self._clean_expired_entries(current_time)

        # Check if we've seen this message recently
        if msg_hash in self.message_cache:
            last_seen = self.message_cache[msg_hash]
            if (current_time - last_seen) < self.window_ms:
                return True

        # Add to cache
        self.message_cache[msg_hash] = current_time
        self.cache_order.append((msg_hash, current_time))

        # Maintain cache size limit
        if len(self.cache_order) > self.max_cache_size:
            oldest_hash, _ = self.cache_order.popleft()
            self.message_cache.pop(oldest_hash, None)

        return False

    def _clean_expired_entries(self, current_time: float) -> None:
        """Remove entries older than the time window."""
        cutoff_time = current_time - self.window_ms

        while self.cache_order and self.cache_order[0][1] < cutoff_time:
            expired_hash, _ = self.cache_order.popleft()
            self.message_cache.pop(expired_hash, None)


# Usage example for your application:
"""
from backend.integrations.can.message_deduplicator import CANMessageDeduplicator

class YourCANHandler:
    def __init__(self):
        # 50ms window should catch most duplicates from bridging
        self.dedup = CANMessageDeduplicator(window_ms=50)

    async def process_message(self, msg: can.Message, interface: str):
        # Check for duplicate
        if self.dedup.is_duplicate(msg.arbitration_id, msg.data):
            logger.debug(f"Ignoring duplicate message {msg.arbitration_id:08X} on {interface}")
            return

        # Process the message normally
        await self.handle_message(msg, interface)
"""
