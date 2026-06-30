"""Regression tests for canonical service-key lookups during root migration."""

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import WebSocketDisconnect

from backend.services.can.can_bus_service import CANBusService
from backend.services.system import websocket_service as websocket_service_module
from backend.services.system.websocket_service import WebSocketService


class _FakeRegistry:
    """Small service-registry double that records lookup keys."""

    def __init__(self, services: dict[str, Any]) -> None:
        self.services = services
        self.requested_keys: list[str] = []

    def get_service(self, name: str) -> Any | None:
        self.requested_keys.append(name)
        return self.services.get(name)


class _FakeWebSocket:
    """Minimal WebSocket double for connection-handler tests."""

    def __init__(self) -> None:
        self.client = SimpleNamespace(host="127.0.0.1", port=12345)
        self.sent_json: list[dict[str, Any]] = []

    async def send_json(self, data: dict[str, Any]) -> None:
        self.sent_json.append(data)

    async def receive_text(self) -> str:
        raise WebSocketDisconnect

    async def close(self, code: int | None = None) -> None:
        self.close_code = code


class _AllowingAuthHandler:
    """Auth-handler double that allows the WebSocket connection."""

    async def authenticate_connection(
        self, websocket: _FakeWebSocket, *, require_auth: bool
    ) -> dict[str, str]:
        return {"username": "pytest"}

    async def require_permission(
        self, websocket: _FakeWebSocket, user_info: dict[str, str], permission: str
    ) -> bool:
        return True

    def remove_connection(self, websocket: _FakeWebSocket) -> None:
        return None


class _FakeEntity:
    def to_dict(self) -> dict[str, str]:
        return {"id": "tank_fresh"}


class _FakeEntityManager:
    def __init__(self) -> None:
        self.updated_payloads: list[dict[str, Any]] = []

    def get_entity(self, entity_id: str) -> _FakeEntity:
        return _FakeEntity()

    def update_entity_state(self, entity_id: str, payload: dict[str, Any]) -> _FakeEntity:
        self.updated_payloads.append(payload)
        return _FakeEntity()


class _FakeEntityManagerService:
    def __init__(self, entity_manager: _FakeEntityManager) -> None:
        self._entity_manager = entity_manager

    def get_entity_manager(self) -> _FakeEntityManager:
        return self._entity_manager


class _FakeBroadcastService:
    def __init__(self) -> None:
        self.broadcasts: list[dict[str, Any]] = []

    async def broadcast_data(self, data: dict[str, Any]) -> None:
        self.broadcasts.append(data)


@pytest.mark.asyncio
async def test_can_entity_updates_use_canonical_entity_and_websocket_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CAN entity updates resolve canonical root service keys."""
    entity_manager = _FakeEntityManager()
    websocket_manager = _FakeBroadcastService()
    registry = _FakeRegistry(
        {
            "entity_manager_service": _FakeEntityManagerService(entity_manager),
            "websocket_manager": websocket_manager,
        }
    )
    monkeypatch.setattr(
        "backend.core.dependencies.get_service_registry",
        lambda: registry,
    )

    service = CANBusService(
        can_tracking_repository=SimpleNamespace(_pending_commands=[]),
        system_state_repository=SimpleNamespace(),
    )

    await service._update_entity_from_can_message(
        entity_id="tank_fresh",
        device_config={"device_type": "tank", "friendly_name": "Fresh Tank"},
        decoded_data={"level": 50},
        raw_data={"level": 128},
        msg={"timestamp": 123.0},
    )

    assert registry.requested_keys == ["entity_manager_service", "websocket_manager"]
    assert entity_manager.updated_payloads
    assert websocket_manager.broadcasts == [
        {"type": "entity_update", "entity_id": "tank_fresh", "data": {"id": "tank_fresh"}}
    ]


class _FakeRecorder:
    def get_status(self) -> dict[str, bool]:
        return {"recording": False}


class _FakeAnalyzer:
    def get_statistics(self) -> dict[str, int]:
        return {"messages": 0}


class _FakeFilter:
    def get_status(self) -> dict[str, int]:
        return {"rules": 0}


@pytest.mark.parametrize(
    ("handler_name", "canonical_key", "legacy_key", "service", "message_type"),
    [
        (
            "handle_can_recorder_connection",
            "can_bus_recorder",
            "can_recorder",
            _FakeRecorder(),
            "status",
        ),
        (
            "handle_can_analyzer_connection",
            "can_protocol_analyzer",
            "can_analyzer",
            _FakeAnalyzer(),
            "statistics",
        ),
        (
            "handle_can_filter_connection",
            "can_message_filter",
            "can_filter",
            _FakeFilter(),
            "status",
        ),
    ],
)
@pytest.mark.asyncio
async def test_can_tool_websocket_handlers_use_canonical_service_keys(
    monkeypatch: pytest.MonkeyPatch,
    handler_name: str,
    canonical_key: str,
    legacy_key: str,
    service: object,
    message_type: str,
) -> None:
    """CAN-tool websocket handlers resolve canonical root service keys."""
    monkeypatch.setattr(
        websocket_service_module,
        "get_websocket_auth_handler",
        lambda: _AllowingAuthHandler(),
    )
    registry = _FakeRegistry({canonical_key: service})
    websocket_service = WebSocketService(service_registry=registry)
    websocket = _FakeWebSocket()

    handler = getattr(websocket_service, handler_name)
    await handler(websocket)

    assert canonical_key in registry.requested_keys
    assert legacy_key not in registry.requested_keys
    assert websocket.sent_json[0]["type"] == message_type
