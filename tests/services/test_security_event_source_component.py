"""Regression tests for SecurityEvent source_component readers."""

from pathlib import Path

import pytest

from backend.core.performance import PerformanceMonitor
from backend.models.security_events import SecurityEvent, SecurityEventType, SecuritySeverity
from backend.repositories.security_event_repository import (
    SecurityEventRepository,
    SecurityListenerRepository,
)
from backend.services.security.security_event_service import SecurityEventService


def _event() -> SecurityEvent:
    """Build a security event with only source_component, not component."""
    return SecurityEvent(
        source_component="auth_middleware",
        event_type=SecurityEventType.AUTH_LOGIN_FAILURE,
        severity=SecuritySeverity.MEDIUM,
        title="Authentication failed",
        description="Missing bearer token",
    )


@pytest.mark.asyncio
async def test_security_event_repository_indexes_source_component() -> None:
    """SecurityEventRepository reads source_component when storing/statting events."""
    repository = SecurityEventRepository(database_manager=None, performance_monitor=None)

    event_id = await repository.store_event(_event())
    by_component = await repository.get_events_by_component("auth_middleware")
    stats = await repository.get_event_statistics()

    assert event_id.startswith("sec_")
    assert by_component[0].source_component == "auth_middleware"
    assert stats["events_by_component"] == {"auth_middleware": 1}


@pytest.mark.asyncio
async def test_security_event_service_publishes_without_component_attribute() -> None:
    """SecurityEventService publishes a source_component event without AttributeError."""
    event_repository = SecurityEventRepository(database_manager=None, performance_monitor=None)
    listener_repository = SecurityListenerRepository(database_manager=None, performance_monitor=None)
    service = SecurityEventService(
        event_repository=event_repository,
        listener_repository=listener_repository,
        performance_monitor=PerformanceMonitor(),
    )

    await service.publish_event(_event())

    stats = await event_repository.get_event_statistics()
    assert stats["events_by_component"] == {"auth_middleware": 1}


def test_security_event_readers_do_not_reference_event_component() -> None:
    """Ratchet: SecurityEvent readers use source_component, not event.component."""
    paths = [
        "backend/repositories/security_event_repository.py",
        "backend/services/security/security_event_service.py",
    ]
    for path in paths:
        source = Path(path).read_text(encoding="utf-8")
        assert "event.component" not in source
