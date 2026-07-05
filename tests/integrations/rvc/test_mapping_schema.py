"""Entity-first coach mapping schema: compiler output + validation.

The entity-first format exists because RX sources and command targets can
use different instance namespaces (climate ambient = G6 sensor channels vs
thermostat zone numbers). These tests pin the compiled runtime structures
and the loud-failure validation that replaced the legacy format's silent
last-write-wins behavior.
"""

import pytest

from backend.integrations.rvc.mapping_schema import (
    compile_entity_mapping,
    is_entity_first_mapping,
)

pytestmark = [pytest.mark.unit]


def _mapping(entities: dict) -> dict:
    return {"defaults": {"interface": "house", "protocol": "rvc"}, "entities": entities}


ZONE = {
    "name": "Mid Zone",
    "type": "climate",
    "area": "interior.living_main",
    "capabilities": ["temperature", "setpoint"],
    "sources": [
        {"dgn": "1FFE2", "instance": 1},
        {"dgn": "1FF9C", "instance": 5},  # sensor channel != zone instance
    ],
    "command": {"dgn": "1FEF9", "instances": [1]},
}


def test_detection() -> None:
    assert is_entity_first_mapping(_mapping({}))
    assert not is_entity_first_mapping({"1FEDA": {25: [{"entity_id": "x"}]}})


def test_sources_and_command_instances_are_independent() -> None:
    """The bug class that motivated the schema: ambient channel 5 feeds the
    zone commanded on instance 1, with no section-ordering dependency."""
    mapping_dict, entity_map, entity_ids, inst_map, unique = compile_entity_mapping(
        _mapping({"climate_mid": ZONE})
    )
    assert entity_ids == {"climate_mid"}
    assert entity_map[("1FFE2", "1")]["entity_id"] == "climate_mid"
    assert entity_map[("1FF9C", "5")]["entity_id"] == "climate_mid"
    # inst_map carries COMMAND addressing, regardless of source declaration order
    assert inst_map["climate_mid"] == {"dgn_hex": "1FEF9", "instance": 1}


def test_command_instances_register_for_rx_and_fan_out() -> None:
    light = {
        "name": "Bedroom Ceiling Light",
        "type": "light",
        "sources": [{"dgn": "1FEDA", "instance": 25}],
        "command": {"dgn": "1FEDB", "instances": [25, 26]},
    }
    _, entity_map, _, inst_map, _ = compile_entity_mapping(_mapping({"bedroom": light}))
    # The G6's own command re-broadcasts must still route to the entity
    assert entity_map[("1FEDB", "25")]["entity_id"] == "bedroom"
    assert entity_map[("1FEDB", "26")]["entity_id"] == "bedroom"
    assert inst_map["bedroom"]["instance"] == 25
    assert inst_map["bedroom"]["command_instances"] == [25, 26]


def test_read_only_entity_without_command() -> None:
    ac = {
        "name": "AC Unit 1",
        "type": "air_conditioner",
        "read_only": True,
        "sources": [{"dgn": "1FFE1", "instance": 1}],
    }
    _, entity_map, _, inst_map, _ = compile_entity_mapping(_mapping({"ac_unit_1": ac}))
    assert entity_map[("1FFE1", "1")]["read_only"] is True
    # Falls back to the first source; control paths never use it for read-only types
    assert inst_map["ac_unit_1"] == {"dgn_hex": "1FFE1", "instance": 1}


def test_defaults_merge_and_override() -> None:
    entities = {
        "plain": {"name": "P", "type": "light", "sources": [{"dgn": "1FEDA", "instance": 1}]},
        "firefly": {
            "name": "F",
            "type": "light",
            "protocol": "firefly",
            "sources": [{"dgn": "1FEDA", "instance": 2}],
        },
    }
    _, entity_map, _, _, _ = compile_entity_mapping(_mapping(entities))
    assert entity_map[("1FEDA", "1")]["protocol"] == "rvc"
    assert entity_map[("1FEDA", "1")]["interface"] == "house"
    assert entity_map[("1FEDA", "2")]["protocol"] == "firefly"


def test_duplicate_source_claim_fails_loudly() -> None:
    entities = {
        "one": {"name": "A", "type": "light", "sources": [{"dgn": "1FEDA", "instance": 7}]},
        "two": {"name": "B", "type": "light", "sources": [{"dgn": "1FEDA", "instance": 7}]},
    }
    with pytest.raises(ValueError, match="Duplicate source claim"):
        compile_entity_mapping(_mapping(entities))


@pytest.mark.parametrize(
    ("entity", "match"),
    [
        ({"name": "X", "type": "light", "sources": []}, "at least 1"),
        (
            {"name": "X", "type": "light", "sources": [{"dgn": "0x1FEDA", "instance": 1}]},
            "plain hex",
        ),
        (
            {
                "name": "X",
                "type": "light",
                "sources": [{"dgn": "1FEDA", "instance": 1}],
                "command": {"dgn": "1FEDB", "instances": []},
            },
            "at least 1",
        ),
        (
            {
                "name": "X",
                "type": "light",
                "sources": [{"dgn": "1FEDA", "instance": 1}],
                "bogus": 1,
            },
            "bogus",
        ),
    ],
)
def test_malformed_entities_rejected(entity: dict, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        compile_entity_mapping(_mapping({"bad_entity": entity}))


def test_invalid_entity_id_rejected() -> None:
    with pytest.raises(ValueError, match="Invalid entity id"):
        compile_entity_mapping(
            _mapping(
                {
                    "Bad-Id": {
                        "name": "X",
                        "type": "light",
                        "sources": [{"dgn": "1FEDA", "instance": 1}],
                    }
                }
            )
        )
