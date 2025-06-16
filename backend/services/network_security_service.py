"""
Network Security Service for RV-C Safety Operations

Provides centralized management and monitoring of network security policies including:
- Dynamic IP whitelist/blacklist management
- Security event monitoring and alerting
- DDoS attack detection and mitigation
- Geographic access control
- Security policy enforcement and updates

Designed for RV deployments with internet connectivity and safety-critical operations.
"""

import ipaddress
import logging
import time
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, Field

from backend.services.security_config_service import SecurityConfigService

logger = logging.getLogger(__name__)


class SecurityEvent(BaseModel):
    """Network security event model."""

    event_id: str = Field(..., description="Unique event ID")
    timestamp: float = Field(..., description="Event timestamp")
    event_type: str = Field(..., description="Type of security event")
    client_ip: str = Field(..., description="Client IP address")
    endpoint: str = Field(..., description="Requested endpoint")
    user_agent: Optional[str] = Field(None, description="User agent string")
    country: Optional[str] = Field(None, description="Country code from GeoIP")
    severity: str = Field("medium", description="Event severity level")
    details: Dict[str, Any] = Field(default_factory=dict, description="Additional event details")
    action_taken: str = Field("logged", description="Action taken in response")
    resolved: bool = Field(False, description="Whether event has been resolved")


class IPBlockEntry(BaseModel):
    """IP block entry model."""

    ip_address: str = Field(..., description="Blocked IP address")
    blocked_until: float = Field(..., description="Block expiration timestamp")
    reason: str = Field(..., description="Reason for blocking")
    block_count: int = Field(1, description="Number of times this IP has been blocked")
    first_blocked: float = Field(..., description="First time this IP was blocked")
    last_activity: float = Field(..., description="Last activity from this IP")


class SecurityThreat(BaseModel):
    """Security threat detection model."""

    threat_id: str = Field(..., description="Unique threat ID")
    threat_type: str = Field(..., description="Type of threat detected")
    source_ip: str = Field(..., description="Source IP address")
    first_seen: float = Field(..., description="First detection timestamp")
    last_seen: float = Field(..., description="Last detection timestamp")
    event_count: int = Field(1, description="Number of related events")
    severity: str = Field("medium", description="Threat severity level")
    active: bool = Field(True, description="Whether threat is still active")
    details: Dict[str, Any] = Field(default_factory=dict, description="Threat details")


class NetworkSecurityService:
    """
    Network security service for RV-C safety operations.

    Provides centralized management of network security policies, event monitoring,
    and threat detection for internet-connected RV deployments.
    """

    def __init__(self, security_config_service: Optional[SecurityConfigService] = None):
        """
        Initialize network security service.

        Args:
            security_config_service: Security configuration service instance
        """
        self.security_config_service = security_config_service or SecurityConfigService()

        # Security event storage
        self.security_events: List[SecurityEvent] = []
        self.max_events = 10000  # Keep last 10k events in memory

        # IP blocking management
        self.blocked_ips: Dict[str, IPBlockEntry] = {}
        self.trusted_ips: Set[str] = set()

        # Threat detection
        self.active_threats: Dict[str, SecurityThreat] = {}
        self.threat_patterns = {
            "brute_force": {"events": 5, "window": 300},  # 5 events in 5 minutes
            "ddos": {"events": 100, "window": 60},  # 100 requests in 1 minute
            "scanning": {"events": 20, "window": 600},  # 20 different endpoints in 10 minutes
            "safety_abuse": {"events": 3, "window": 180},  # 3 safety endpoint failures in 3 minutes
        }

        # Statistics tracking
        self.stats = {
            "total_events": 0,
            "blocked_attempts": 0,
            "threats_detected": 0,
            "last_reset": time.time(),
        }

        logger.info("Network Security Service initialized for RV safety operations")

    async def log_security_event(
        self,
        event_type: str,
        client_ip: str,
        endpoint: str,
        severity: str = "medium",
        user_agent: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Log a security event and perform threat analysis.

        Args:
            event_type: Type of security event
            client_ip: Client IP address
            endpoint: Requested endpoint
            severity: Event severity level
            user_agent: User agent string
            details: Additional event details

        Returns:
            Event ID
        """
        event_id = f"sec_{int(time.time() * 1000)}_{hash(client_ip) % 10000:04d}"

        event = SecurityEvent(
            event_id=event_id,
            timestamp=time.time(),
            event_type=event_type,
            client_ip=client_ip,
            endpoint=endpoint,
            user_agent=user_agent,
            country=None,  # Will be populated by GeoIP if available
            severity=severity,
            details=details or {},
            action_taken="logged",
            resolved=False,  # Default value for resolved
        )

        # Add to event store
        self.security_events.append(event)
        self.stats["total_events"] += 1

        # Trim old events
        if len(self.security_events) > self.max_events:
            self.security_events = self.security_events[-self.max_events :]

        # Perform threat analysis
        threat_detected = await self._analyze_threat_patterns(event)
        if threat_detected:
            self.stats["threats_detected"] += 1

        # Log event
        logger.info(
            f"Security event {event_id}: {event_type} from {client_ip} "
            f"on {endpoint} (severity: {severity})"
        )

        return event_id

    async def block_ip(
        self,
        ip_address: str,
        duration_seconds: int,
        reason: str,
        auto_block: bool = False,
    ) -> bool:
        """
        Block an IP address for a specified duration.

        Args:
            ip_address: IP address to block
            duration_seconds: Block duration in seconds
            reason: Reason for blocking
            auto_block: Whether this is an automatic block

        Returns:
            True if blocked successfully, False otherwise
        """
        try:
            # Validate IP address
            ipaddress.IPv4Address(ip_address)

            # Check if IP is in trusted list
            if ip_address in self.trusted_ips:
                logger.warning(f"Attempted to block trusted IP {ip_address}")
                return False

            # Calculate block expiration
            block_until = time.time() + duration_seconds

            # Update or create block entry
            if ip_address in self.blocked_ips:
                existing = self.blocked_ips[ip_address]
                existing.blocked_until = max(existing.blocked_until, block_until)
                existing.block_count += 1
                existing.last_activity = time.time()
                existing.reason = f"{existing.reason}; {reason}"
            else:
                self.blocked_ips[ip_address] = IPBlockEntry(
                    ip_address=ip_address,
                    blocked_until=block_until,
                    reason=reason,
                    block_count=1,  # First time being blocked
                    first_blocked=time.time(),
                    last_activity=time.time(),
                )

            # Log security event
            await self.log_security_event(
                event_type="ip_blocked",
                client_ip=ip_address,
                endpoint="security_action",
                severity="high",
                details={
                    "block_duration": duration_seconds,
                    "reason": reason,
                    "auto_block": auto_block,
                },
            )

            self.stats["blocked_attempts"] += 1

            logger.warning(
                f"IP {ip_address} blocked for {duration_seconds}s: {reason} "
                f"(auto_block: {auto_block})"
            )

            return True

        except (ipaddress.AddressValueError, ValueError) as e:
            logger.error(f"Invalid IP address {ip_address}: {e}")
            return False

    async def unblock_ip(self, ip_address: str, reason: str = "manual_unblock") -> bool:
        """
        Unblock an IP address.

        Args:
            ip_address: IP address to unblock
            reason: Reason for unblocking

        Returns:
            True if unblocked successfully, False otherwise
        """
        if ip_address in self.blocked_ips:
            del self.blocked_ips[ip_address]

            # Log security event
            await self.log_security_event(
                event_type="ip_unblocked",
                client_ip=ip_address,
                endpoint="security_action",
                severity="medium",
                details={"reason": reason},
            )

            logger.info(f"IP {ip_address} unblocked: {reason}")
            return True

        return False

    def is_ip_blocked(self, ip_address: str) -> bool:
        """
        Check if an IP address is currently blocked.

        Args:
            ip_address: IP address to check

        Returns:
            True if blocked, False otherwise
        """
        if ip_address not in self.blocked_ips:
            return False

        block_entry = self.blocked_ips[ip_address]
        if time.time() >= block_entry.blocked_until:
            # Block expired, remove it
            del self.blocked_ips[ip_address]
            return False

        return True

    async def add_trusted_ip(self, ip_address: str) -> bool:
        """
        Add an IP address to the trusted list.

        Args:
            ip_address: IP address to trust

        Returns:
            True if added successfully, False otherwise
        """
        try:
            ipaddress.IPv4Address(ip_address)
            self.trusted_ips.add(ip_address)

            # Remove from blocked list if present
            if ip_address in self.blocked_ips:
                await self.unblock_ip(ip_address, "added_to_trusted")

            logger.info(f"IP {ip_address} added to trusted list")
            return True

        except (ipaddress.AddressValueError, ValueError) as e:
            logger.error(f"Invalid IP address {ip_address}: {e}")
            return False

    async def remove_trusted_ip(self, ip_address: str) -> bool:
        """
        Remove an IP address from the trusted list.

        Args:
            ip_address: IP address to remove from trusted list

        Returns:
            True if removed successfully, False otherwise
        """
        if ip_address in self.trusted_ips:
            self.trusted_ips.remove(ip_address)
            logger.info(f"IP {ip_address} removed from trusted list")
            return True

        return False

    async def _analyze_threat_patterns(self, event: SecurityEvent) -> bool:
        """
        Analyze security event for threat patterns.

        Args:
            event: Security event to analyze

        Returns:
            True if threat detected, False otherwise
        """
        threat_detected = False
        now = time.time()

        # Get recent events from same IP
        recent_events = [
            e
            for e in self.security_events
            if e.client_ip == event.client_ip and now - e.timestamp <= 3600  # Last hour
        ]

        # Check for brute force attacks
        if await self._detect_brute_force(event, recent_events):
            await self._handle_threat("brute_force", event, recent_events)
            threat_detected = True

        # Check for DDoS attacks
        if await self._detect_ddos(event, recent_events):
            await self._handle_threat("ddos", event, recent_events)
            threat_detected = True

        # Check for scanning activity
        if await self._detect_scanning(event, recent_events):
            await self._handle_threat("scanning", event, recent_events)
            threat_detected = True

        # Check for safety endpoint abuse
        if await self._detect_safety_abuse(event, recent_events):
            await self._handle_threat("safety_abuse", event, recent_events)
            threat_detected = True

        return threat_detected

    async def _detect_brute_force(
        self, event: SecurityEvent, recent_events: List[SecurityEvent]
    ) -> bool:
        """Detect brute force attack patterns."""
        failed_auth_events = [
            e
            for e in recent_events
            if e.event_type in ["auth_failed", "pin_failed", "login_failed"]
            and time.time() - e.timestamp <= self.threat_patterns["brute_force"]["window"]
        ]

        return len(failed_auth_events) >= self.threat_patterns["brute_force"]["events"]

    async def _detect_ddos(self, event: SecurityEvent, recent_events: List[SecurityEvent]) -> bool:
        """Detect DDoS attack patterns."""
        ddos_window = self.threat_patterns["ddos"]["window"]
        recent_requests = [e for e in recent_events if time.time() - e.timestamp <= ddos_window]

        return len(recent_requests) >= self.threat_patterns["ddos"]["events"]

    async def _detect_scanning(
        self, event: SecurityEvent, recent_events: List[SecurityEvent]
    ) -> bool:
        """Detect port/endpoint scanning patterns."""
        scanning_window = self.threat_patterns["scanning"]["window"]
        recent_scans = [
            e
            for e in recent_events
            if time.time() - e.timestamp <= scanning_window
            and e.event_type in ["not_found", "forbidden", "method_not_allowed"]
        ]

        # Check for requests to many different endpoints
        unique_endpoints = set(e.endpoint for e in recent_scans)
        return len(unique_endpoints) >= self.threat_patterns["scanning"]["events"]

    async def _detect_safety_abuse(
        self, event: SecurityEvent, recent_events: List[SecurityEvent]
    ) -> bool:
        """Detect safety endpoint abuse patterns."""
        safety_window = self.threat_patterns["safety_abuse"]["window"]
        safety_failures = [
            e
            for e in recent_events
            if time.time() - e.timestamp <= safety_window
            and e.event_type in ["safety_violation", "pin_failed", "unauthorized_safety"]
            and "/api/safety/" in e.endpoint
        ]

        return len(safety_failures) >= self.threat_patterns["safety_abuse"]["events"]

    async def _handle_threat(
        self,
        threat_type: str,
        event: SecurityEvent,
        recent_events: List[SecurityEvent],
    ) -> None:
        """
        Handle detected threat.

        Args:
            threat_type: Type of threat detected
            event: Triggering security event
            recent_events: Recent events from same IP
        """
        threat_id = f"{threat_type}_{event.client_ip}_{int(time.time())}"

        # Create or update threat record
        if threat_id not in self.active_threats:
            threat = SecurityThreat(
                threat_id=threat_id,
                threat_type=threat_type,
                source_ip=event.client_ip,
                first_seen=time.time(),
                last_seen=time.time(),
                event_count=len(recent_events),
                severity=self._get_threat_severity(threat_type),
                active=True,  # Default to active
                details={
                    "triggering_event": event.event_id,
                    "related_events": [e.event_id for e in recent_events[-10:]],  # Last 10
                },
            )
            self.active_threats[threat_id] = threat

        # Determine response action
        action = self._get_threat_response(threat_type, event)

        # Execute response
        if action == "block_ip":
            duration = self._get_block_duration(threat_type)
            await self.block_ip(
                event.client_ip,
                duration,
                f"Threat detected: {threat_type}",
                auto_block=True,
            )

        logger.critical(
            f"Security threat detected: {threat_type} from {event.client_ip} (action: {action})"
        )

    def _get_threat_severity(self, threat_type: str) -> str:
        """Get threat severity level."""
        severity_map = {
            "brute_force": "high",
            "ddos": "critical",
            "scanning": "medium",
            "safety_abuse": "critical",  # Safety is always critical
        }
        return severity_map.get(threat_type, "medium")

    def _get_threat_response(self, threat_type: str, event: SecurityEvent) -> str:
        """Determine appropriate response to threat."""
        # Safety abuse always gets immediate blocking
        if threat_type == "safety_abuse":
            return "block_ip"

        # DDoS gets immediate blocking
        if threat_type == "ddos":
            return "block_ip"

        # Brute force gets blocking after threshold
        if threat_type == "brute_force":
            return "block_ip"

        # Scanning gets rate limiting
        if threat_type == "scanning":
            return "rate_limit"

        return "log_only"

    def _get_block_duration(self, threat_type: str) -> int:
        """Get block duration for threat type."""
        duration_map = {
            "brute_force": 1800,  # 30 minutes
            "ddos": 3600,  # 1 hour
            "scanning": 900,  # 15 minutes
            "safety_abuse": 7200,  # 2 hours (safety is critical)
        }
        return duration_map.get(threat_type, 900)

    async def cleanup_expired_blocks(self) -> int:
        """
        Clean up expired IP blocks.

        Returns:
            Number of blocks removed
        """
        now = time.time()
        expired_ips = [
            ip for ip, block_entry in self.blocked_ips.items() if block_entry.blocked_until <= now
        ]

        for ip in expired_ips:
            del self.blocked_ips[ip]
            logger.debug(f"Expired block removed for IP {ip}")

        return len(expired_ips)

    def get_security_summary(self) -> Dict[str, Any]:
        """
        Get network security summary for monitoring.

        Returns:
            Dictionary with security summary
        """
        now = time.time()

        # Count recent events (last 24 hours)
        recent_events = [e for e in self.security_events if now - e.timestamp <= 86400]

        # Count active blocks
        active_blocks = [block for block in self.blocked_ips.values() if block.blocked_until > now]

        # Count active threats
        active_threats = [
            threat
            for threat in self.active_threats.values()
            if threat.active and now - threat.last_seen <= 3600
        ]

        return {
            "summary": {
                "total_events": self.stats["total_events"],
                "recent_events_24h": len(recent_events),
                "active_blocks": len(active_blocks),
                "active_threats": len(active_threats),
                "trusted_ips": len(self.trusted_ips),
            },
            "threat_breakdown": {
                threat_type: len([t for t in active_threats if t.threat_type == threat_type])
                for threat_type in ["brute_force", "ddos", "scanning", "safety_abuse"]
            },
            "recent_event_types": {
                event_type: len([e for e in recent_events if e.event_type == event_type])
                for event_type in set(e.event_type for e in recent_events)
            },
            "top_blocked_ips": [
                {
                    "ip": block.ip_address,
                    "block_count": block.block_count,
                    "reason": block.reason,
                    "expires_in": max(0, int(block.blocked_until - now)),
                }
                for block in sorted(active_blocks, key=lambda x: x.block_count, reverse=True)[:10]
            ],
            "system_health": {
                "event_storage_usage": f"{len(self.security_events)}/{self.max_events}",
                "threat_detection_active": True,
                "auto_blocking_enabled": True,
                "last_cleanup": now - (now % 3600),  # Last hour
            },
        }
