"""Tests for the TimeSyncService broadcast behavior (CAN facade is faked)."""

from typing import Any

from backend.core.config import TimeSyncSettings
from backend.services.time_sync.time_sync_service import TimeSyncService


class FakeCanFacade:
    def __init__(self) -> None:
        self.sent: list[tuple[int, bytes, str]] = []

    async def send_raw_message(
        self, arbitration_id: int, data: bytes, interface: str
    ) -> dict[str, Any]:
        self.sent.append((arbitration_id, data, interface))
        return {"success": True}


class FakePositionProvider:
    def __init__(self, fix: bool) -> None:
        self._fix = fix
        self.speed_mps: float | None = 25.0
        self.course_deg: float | None = 180.0

    def get_current_position(self) -> dict[str, Any]:
        if not self._fix:
            return {"fix": False, "latitude": None, "longitude": None}
        return {
            "fix": True,
            "latitude": 35.578453,
            "longitude": -75.465530,
            "speed_mps": self.speed_mps,
            "course_deg": self.course_deg,
            "altitude_m": 2.0,
        }


def make_service(
    *, fix: bool | None = True, send_gps: bool = True, set_interval: float = 0.0
) -> tuple[TimeSyncService, FakeCanFacade, FakePositionProvider | None]:
    settings = TimeSyncSettings(
        enabled=True, send_gps=send_gps, set_command_interval_seconds=set_interval
    )
    facade = FakeCanFacade()
    provider = FakePositionProvider(fix) if fix is not None else None
    service = TimeSyncService(
        settings=settings,
        can_facade=facade,
        source_address=0xF9,
        position_provider=provider,
    )
    return service, facade, provider


def dgns(facade: FakeCanFacade) -> list[int]:
    return [(arb >> 8) & 0x3FFFF for arb, _, _ in facade.sent]


class TestBroadcast:
    async def test_with_fix_sends_time_and_gps(self):
        service, facade, _ = make_service(fix=True)
        await service._broadcast_once()
        sent = dgns(facade)
        assert sent[0] == 0x1FFFF  # DATE_TIME_STATUS first
        assert 0x1FEA0 in sent  # GPS_DATE_TIME announced on first broadcast
        assert 0x0FEF3 in sent
        assert 0x1FED3 in sent
        assert 0x1FDDF in sent
        # All from our source address on the house interface.
        assert all(arb & 0xFF == 0xF9 for arb, _, _ in facade.sent)
        assert all(interface == "house" for _, _, interface in facade.sent)

    async def test_gps_announce_only_once(self):
        service, facade, _ = make_service(fix=True)
        await service._broadcast_once()
        await service._broadcast_once()
        assert dgns(facade).count(0x1FEA0) == 1
        assert dgns(facade).count(0x1FFFF) == 2

    async def test_no_fix_sends_nothing(self):
        # Chrony gets its time from this GPS; without a fix, stay silent.
        service, facade, _ = make_service(fix=False)
        await service._broadcast_once()
        assert facade.sent == []

    async def test_gps_disabled_sends_time_only(self):
        service, facade, _ = make_service(fix=False, send_gps=False)
        await service._broadcast_once()
        sent = dgns(facade)
        assert 0x1FFFF in sent
        assert 0x0FEF3 not in sent

    async def test_no_provider_sends_time_only(self):
        service, facade, _ = make_service(fix=None)
        await service._broadcast_once()
        sent = dgns(facade)
        assert 0x1FFFF in sent
        assert 0x0FEF3 not in sent

    async def test_set_command_nudge_rate_limited(self):
        service, facade, _ = make_service(fix=True, set_interval=300.0)
        await service._broadcast_once()
        await service._broadcast_once()
        # One SET on the first broadcast, then suppressed until the interval.
        assert dgns(facade).count(0x1FFFE) == 1

    async def test_set_command_disabled_at_zero(self):
        service, facade, _ = make_service(fix=True, set_interval=0.0)
        await service._broadcast_once()
        assert 0x1FFFE not in dgns(facade)

    async def test_compass_follows_course_while_moving(self):
        service, facade, provider = make_service(fix=True)
        assert provider is not None
        await service._broadcast_once()
        compass = [data for arb, data, _ in facade.sent if (arb >> 8) & 0x3FFFF == 0x1FFA0]
        assert int.from_bytes(compass[-1][0:2], "little") == 180 * 128

    async def test_compass_holds_last_bearing_while_parked(self):
        service, facade, provider = make_service(fix=True)
        assert provider is not None
        await service._broadcast_once()  # moving south at 25 m/s

        # Parked: GPS course becomes noise; the bearing must hold at 180°.
        provider.speed_mps = 0.0
        provider.course_deg = 37.0
        await service._broadcast_once()
        compass = [data for arb, data, _ in facade.sent if (arb >> 8) & 0x3FFFF == 0x1FFA0]
        assert int.from_bytes(compass[-1][0:2], "little") == 180 * 128

    async def test_compass_not_available_before_first_movement(self):
        service, facade, provider = make_service(fix=True)
        assert provider is not None
        provider.speed_mps = 0.0
        await service._broadcast_once()
        compass = [data for arb, data, _ in facade.sent if (arb >> 8) & 0x3FFFF == 0x1FFA0]
        assert compass[-1][0:2] == b"\xff\xff"

    async def test_tx_errors_counted(self):
        service, facade, _ = make_service(fix=True)

        async def failing_send(**kwargs: Any) -> dict[str, Any]:
            return {"success": False, "error": "bus off"}

        facade.send_raw_message = failing_send  # type: ignore[assignment]
        await service._broadcast_once()
        health = service.get_health_status()
        assert health["tx_errors"] > 0
