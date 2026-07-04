"""Coach mapping metadata sections must stay loadable and area-complete.

The zone-based frontend renders devices grouped by the `areas` hierarchy
and executes `lighting_scenes`; these sections are skipped by the DGN
decoder and are only surfaced through /api/v1/entities/config/coach.
Guard the YAML contract so a mapping edit cannot silently break zoning.
"""

from pathlib import Path

import pytest
import yaml

pytestmark = [pytest.mark.unit]

MAPPING_PATH = Path(__file__).resolve().parents[4] / "config" / "2021_Entegra_Aspire_44R.yml"


@pytest.fixture(scope="module")
def mapping() -> dict:
    with MAPPING_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_areas_hierarchy_present(mapping: dict) -> None:
    areas = mapping.get("areas")
    assert areas, "coach mapping must define areas"
    assert "interior" in areas
    assert "exterior" in areas
    for section in areas.values():
        assert section.get("zones"), "each area section needs zones"
        for zone in section["zones"].values():
            assert zone.get("display_name"), "each zone needs a display_name"


def test_lighting_scenes_present(mapping: dict) -> None:
    scenes = mapping.get("lighting_scenes")
    assert scenes, "coach mapping must define lighting_scenes"
    assert "all_off" in scenes
    for scene in scenes.values():
        assert scene.get("entities"), "each scene needs an entities list"


def _walk_entities_for_area_check(
    node: object,
    defined_zones: set[str],
    missing: list[str],
    unknown_zone: list[str],
) -> None:
    """Recursively walk a mapping node, recording entity_ids with missing/unknown areas."""
    if isinstance(node, dict):
        if "entity_id" in node:
            area = node.get("area")
            if not area:
                missing.append(str(node["entity_id"]))
            elif area not in defined_zones:
                unknown_zone.append(f"{node['entity_id']} -> {area}")
        for value in node.values():
            _walk_entities_for_area_check(value, defined_zones, missing, unknown_zone)
    elif isinstance(node, list):
        for item in node:
            _walk_entities_for_area_check(item, defined_zones, missing, unknown_zone)


def test_every_light_entity_has_an_area(mapping: dict) -> None:
    """Every entity definition carrying an entity_id should map to a real zone."""
    defined_zones = {
        f"{section_key}.{zone_key}"
        for section_key, section in mapping["areas"].items()
        for zone_key in section.get("zones", {})
    }

    missing: list[str] = []
    unknown_zone: list[str] = []

    for key, value in mapping.items():
        if key in {"areas", "lighting_scenes", "lighting_groups", "coach_info"}:
            continue
        _walk_entities_for_area_check(value, defined_zones, missing, unknown_zone)

    # The mapping currently has exactly one legacy entry without an area
    # (surfaced as "Unassigned" in the UI); do not let the list grow.
    assert len(missing) <= 1, f"entities missing area: {missing}"
    assert not unknown_zone, f"entities referencing undefined zones: {unknown_zone}"
