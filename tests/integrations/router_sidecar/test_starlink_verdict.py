"""Tests for RouterOS sidecar Starlink client and verdict evaluation."""

from datetime import UTC, datetime, timedelta
from google.protobuf import descriptor_pb2, descriptor_pool, json_format, message_factory
import time

import pytest
from fastapi.testclient import TestClient

from backend.core.config import RouterSidecarSettings
from backend.integrations.router_sidecar import RouterSidecarService
from backend.integrations.router_sidecar.starlink import StarlinkGrpcClient, StarlinkSnapshot
from backend.integrations.router_sidecar.verdict import (
    StarlinkVerdictConfig,
    StarlinkVerdictEvaluator,
    format_starlink_raw,
)

pytestmark = [pytest.mark.integration, pytest.mark.smoke]


def _config() -> StarlinkVerdictConfig:
    return StarlinkVerdictConfig(
        obstruction_fraction_degraded=0.03,
        obstruction_fraction_recovery=0.02,
        pop_ping_drop_rate_degraded=0.05,
        pop_ping_drop_rate_recovery=0.02,
        pop_ping_latency_ms_degraded=100.0,
        pop_ping_latency_ms_recovery=60.0,
        recent_outage_count_degraded=3,
        history_sample_window=5,
        degraded_debounce_seconds=60.0,
        down_recovery_dwell_seconds=60.0,
    )


def _healthy_snapshot(**status_overrides) -> StarlinkSnapshot:
    status = {
        "obstruction_stats": {"fraction_obstructed": 0.001, "currently_obstructed": False},
        "alerts": {},
        "pop_ping_drop_rate": 0.0,
        "pop_ping_latency_ms": 22.0,
        "downlink_throughput_bps": 1234.0,
        "uplink_throughput_bps": 456.0,
        "is_snr_above_noise_floor": True,
        "disablement_code": "OKAY",
        "software_update_state": "IDLE",
        "alignment_stats": {
            "tilt_angle_deg": 1.2,
            "attitude_uncertainty_deg": 0.4,
            "attitude_estimation_state": "FILTER_CONVERGED",
        },
        "ready_states": {
            "cady": False,
            "scp": True,
            "l1l2": True,
            "xphy": True,
            "aap": True,
            "rf": True,
        },
    }
    status.update(status_overrides)
    return StarlinkSnapshot(
        reachable=True,
        status=status,
        history={"pop_ping_drop_rate": [0.0] * 5, "pop_ping_latency_ms": [20.0] * 5},
        diagnostics={"alerts": []},
        device_info={"id": "ut-test"},
        fetched_at=time.time(),
    )


def test_starlink_unreachable_and_active_outage_verdicts() -> None:
    """Unreachable dishes are unknown; active outage is down."""
    evaluator = StarlinkVerdictEvaluator(_config())

    assert evaluator.evaluate(StarlinkSnapshot(reachable=False, error="timeout")) == "unknown"
    assert evaluator.evaluate(_healthy_snapshot(outage={"cause": "NO_PINGS"})) == "down"


def test_cady_false_does_not_mark_working_dish_down() -> None:
    """The dish-verified cady=false ready state is not used as a down signal."""
    evaluator = StarlinkVerdictEvaluator(_config())

    assert evaluator.evaluate(_healthy_snapshot()) == "healthy"


def test_false_non_cady_ready_state_contributes_to_degraded_gate() -> None:
    """Emitted false non-cady ready states are not missed by verdict logic."""
    evaluator = StarlinkVerdictEvaluator(_config())
    start = datetime(2026, 7, 2, 12, 0, tzinfo=UTC)
    not_ready = _healthy_snapshot(
        ready_states={
            "cady": False,
            "scp": False,
            "l1l2": True,
            "xphy": True,
            "aap": True,
            "rf": True,
        }
    )

    assert evaluator.evaluate(not_ready, now=start) == "healthy"
    assert evaluator.evaluate(not_ready, now=start + timedelta(seconds=61)) == "degraded"


def test_message_to_dict_emits_false_default_values() -> None:
    """Protobuf JSON serialization includes false/zero fields for stable sensors."""
    message_class = _default_value_test_message_class()
    message = message_class()
    message.alerts.SetInParent()
    message.obstruction_stats.SetInParent()
    message.ready_states.SetInParent()
    payload = json_format.MessageToDict(
        message,
        always_print_fields_with_no_presence=True,
        preserving_proto_field_name=True,
        use_integers_for_enums=False,
    )

    assert payload == {
        "alerts": {"mast_not_near_vertical": False, "motors_stuck": False},
        "obstruction_stats": {"currently_obstructed": False},
        "ready_states": {"cady": False, "scp": False},
    }


def test_degraded_requires_sustained_poor_signal() -> None:
    """Poor obstruction must persist through the debounce window before degraded."""
    evaluator = StarlinkVerdictEvaluator(_config())
    start = datetime(2026, 7, 2, 12, 0, tzinfo=UTC)
    poor = _healthy_snapshot(
        obstruction_stats={"fraction_obstructed": 0.2, "currently_obstructed": True}
    )

    assert evaluator.evaluate(poor, now=start) == "healthy"
    assert evaluator.evaluate(poor, now=start + timedelta(seconds=30)) == "healthy"
    assert evaluator.evaluate(poor, now=start + timedelta(seconds=61)) == "degraded"
    assert evaluator.evaluate(_healthy_snapshot(), now=start + timedelta(seconds=62)) == "degraded"


def test_low_fraction_obstruction_does_not_flap() -> None:
    """Normal 0.5-1% obstruction stays below the 3% enter threshold."""
    evaluator = StarlinkVerdictEvaluator(_config())
    start = datetime(2026, 7, 2, 12, 0, tzinfo=UTC)
    normal_obstruction = _healthy_snapshot(
        obstruction_stats={"fraction_obstructed": 0.0077, "currently_obstructed": False}
    )

    for offset in range(0, 180, 15):
        assert (
            evaluator.evaluate(normal_obstruction, now=start + timedelta(seconds=offset))
            == "healthy"
        )


def test_currently_obstructed_boolean_must_dwell() -> None:
    """Toggling currently_obstructed does not publish degraded until sustained."""
    evaluator = StarlinkVerdictEvaluator(_config())
    start = datetime(2026, 7, 2, 12, 0, tzinfo=UTC)
    toggled = _healthy_snapshot(
        obstruction_stats={"fraction_obstructed": 0.0077, "currently_obstructed": True}
    )

    assert evaluator.evaluate(toggled, now=start) == "healthy"
    assert evaluator.evaluate(_healthy_snapshot(), now=start + timedelta(seconds=15)) == "healthy"
    assert evaluator.evaluate(toggled, now=start + timedelta(seconds=30)) == "healthy"
    assert evaluator.evaluate(toggled, now=start + timedelta(seconds=91)) == "degraded"


def test_degraded_holds_until_sustained_recovery() -> None:
    """A single good sample does not immediately clear degraded."""
    evaluator = StarlinkVerdictEvaluator(_config())
    start = datetime(2026, 7, 2, 12, 0, tzinfo=UTC)
    poor = _healthy_snapshot(
        obstruction_stats={"fraction_obstructed": 0.2, "currently_obstructed": False}
    )

    assert evaluator.evaluate(poor, now=start) == "healthy"
    assert evaluator.evaluate(poor, now=start + timedelta(seconds=61)) == "degraded"
    assert evaluator.evaluate(_healthy_snapshot(), now=start + timedelta(seconds=62)) == "degraded"
    assert evaluator.evaluate(_healthy_snapshot(), now=start + timedelta(seconds=123)) == "healthy"


def test_outage_and_disablement_are_immediate_down_with_dwelled_recovery() -> None:
    """Current outage or non-OK disablement publishes down immediately."""
    evaluator = StarlinkVerdictEvaluator(_config())
    start = datetime(2026, 7, 2, 12, 0, tzinfo=UTC)

    assert evaluator.evaluate(_healthy_snapshot(outage={"cause": "NO_PINGS"}), now=start) == "down"
    assert evaluator.evaluate(_healthy_snapshot(), now=start + timedelta(seconds=1)) == "down"
    assert evaluator.evaluate(_healthy_snapshot(), now=start + timedelta(seconds=62)) == "healthy"

    evaluator = StarlinkVerdictEvaluator(_config())
    disabled = _healthy_snapshot(disablement_code="ACCOUNT_DISABLED")
    assert evaluator.evaluate(disabled, now=start) == "down"


def test_nan_invalid_obstruction_stats_are_no_signal() -> None:
    """Invalid NaN obstruction stats do not contribute to degraded."""
    evaluator = StarlinkVerdictEvaluator(_config())
    start = datetime(2026, 7, 2, 12, 0, tzinfo=UTC)
    invalid = _healthy_snapshot(
        obstruction_stats={
            "fraction_obstructed": "NaN",
            "currently_obstructed": False,
            "avg_prolonged_obstruction_valid": False,
            "avg_prolonged_obstruction_interval_s": "NaN",
        }
    )

    assert evaluator.evaluate(invalid, now=start) == "healthy"
    assert evaluator.evaluate(invalid, now=start + timedelta(seconds=120)) == "healthy"


def _default_value_test_message_class():
    file_descriptor = descriptor_pb2.FileDescriptorProto()
    file_descriptor.name = "router_sidecar_default_value_test.proto"
    file_descriptor.package = "coachiq.test"
    file_descriptor.syntax = "proto3"

    alerts = file_descriptor.message_type.add()
    alerts.name = "Alerts"
    _add_bool_field(alerts, "mast_not_near_vertical", 1)
    _add_bool_field(alerts, "motors_stuck", 2)

    obstruction = file_descriptor.message_type.add()
    obstruction.name = "ObstructionStats"
    _add_bool_field(obstruction, "currently_obstructed", 1)

    ready = file_descriptor.message_type.add()
    ready.name = "ReadyStates"
    _add_bool_field(ready, "cady", 1)
    _add_bool_field(ready, "scp", 2)

    status = file_descriptor.message_type.add()
    status.name = "DishStatus"
    _add_message_field(status, "alerts", 1, ".coachiq.test.Alerts")
    _add_message_field(status, "obstruction_stats", 2, ".coachiq.test.ObstructionStats")
    _add_message_field(status, "ready_states", 3, ".coachiq.test.ReadyStates")

    pool = descriptor_pool.DescriptorPool()
    pool.Add(file_descriptor)
    descriptor = pool.FindMessageTypeByName("coachiq.test.DishStatus")
    return message_factory.GetMessageClass(descriptor)


def _add_bool_field(message, name: str, number: int) -> None:
    field = message.field.add()
    field.name = name
    field.number = number
    field.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
    field.type = descriptor_pb2.FieldDescriptorProto.TYPE_BOOL


def _add_message_field(message, name: str, number: int, type_name: str) -> None:
    field = message.field.add()
    field.name = name
    field.number = number
    field.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
    field.type = descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE
    field.type_name = type_name


@pytest.mark.asyncio
async def test_starlink_client_uses_fake_handle_call() -> None:
    """Starlink client can be tested against a fake Device/Handle transport."""
    calls: list[str] = []

    def fake_handle(request_field: str) -> dict:
        calls.append(request_field)
        if request_field == "get_status":
            return {"dish_get_status": _healthy_snapshot().status}
        if request_field == "get_history":
            return {
                "dish_get_history": {"pop_ping_drop_rate": [0.0], "pop_ping_latency_ms": [21.0]}
            }
        if request_field == "get_diagnostics":
            return {"dish_get_diagnostics": {"ok": True}}
        if request_field == "get_device_info":
            return {"get_device_info": {"id": "ut-test"}}
        raise PermissionError("Disabled due to policy")

    client = StarlinkGrpcClient("dish", 9200, handle_call=fake_handle)
    snapshot = await __import__("asyncio").to_thread(client.fetch_snapshot_blocking)

    assert calls == [
        "get_status",
        "get_history",
        "get_diagnostics",
        "get_device_info",
        "get_location",
    ]
    assert snapshot.reachable is True
    assert snapshot.status["pop_ping_latency_ms"] == 22.0
    assert snapshot.history["pop_ping_latency_ms"] == [21.0]
    assert snapshot.diagnostics == {"ok": True}
    assert snapshot.device_info == {"id": "ut-test"}
    assert snapshot.location is None
    assert snapshot.location_error is not None


def test_raw_line_is_single_key_value_line() -> None:
    """Raw Starlink output is RouterOS-friendly key=value text."""
    raw = format_starlink_raw(_healthy_snapshot())

    assert raw == (
        "obstruct=0.10 outage=0 droprate=0.000 lat=22.0 thermal=0 ready=1 "
        "snr_ok=1 dl_bps=1234 ul_bps=456 drop_avg=0.000 lat_avg=20.0 "
        "tilt=1.2 att_uncert=0.4 align_ok=1 ready_scp=1 ready_l1l2=1 "
        "ready_xphy=1 ready_aap=1 ready_rf=1 disable_code=OKAY "
        "outages_recent=0 sw_update=IDLE"
    )
    assert "\n" not in raw


def test_telemetry_json_endpoints_include_staleness_metadata_and_windowing() -> None:
    """JSON telemetry endpoints wrap cached payloads and trim history windows."""
    service = RouterSidecarService(RouterSidecarSettings(enabled=False))
    client = TestClient(service.app)

    never_polled = client.get("/starlink/status")
    assert never_polled.status_code == 200
    assert never_polled.json()["stale"] is True
    assert never_polled.json()["data"] is None

    service._refresh_starlink(_healthy_snapshot())

    status_payload = client.get("/starlink/status").json()
    assert status_payload["stale"] is False
    assert status_payload["data"]["pop_ping_latency_ms"] == 22.0

    history_payload = client.get("/starlink/history?window=2").json()
    assert history_payload["data"]["pop_ping_latency_ms"] == [20.0, 20.0]
    assert len(history_payload["data"]["pop_ping_drop_rate"]) == 2

    assert client.get("/starlink/diagnostics").json()["data"] == {"alerts": []}
    assert client.get("/starlink/device-info").json()["data"] == {"id": "ut-test"}


def test_unreachable_starlink_keeps_last_good_stale_response() -> None:
    """Poll failures keep last-good telemetry but mark wrappers stale."""
    service = RouterSidecarService(RouterSidecarSettings(enabled=False))
    client = TestClient(service.app)
    service._refresh_starlink(_healthy_snapshot())
    service._refresh_starlink(StarlinkSnapshot(reachable=False, error="timeout"))

    payload = client.get("/starlink/status").json()

    assert payload["stale"] is True
    assert payload["error"] == "timeout"
    assert payload["data"]["pop_ping_latency_ms"] == 22.0
    assert client.get("/starlink/verdict").text == "unknown\n"
    assert client.get("/starlink/raw").text == "reachable=0\n"
