"""
Entity-first coach mapping schema and compiler.

The original coach mapping format is DGN-first (top-level DGN hex sections
mapping instance -> device list), which cannot express entities whose RX
sources, sensors, and command targets live on different DGNs *with different
instance numbers* — the climate zones' ambient temperatures come from the
G6's raw sensor channels (1FF9C), not the thermostat zone instances (1FFE2),
and the old format could only encode that through YAML anchor gymnastics and
a section-ordering dependency in the loader's last-write-wins ``inst_map``.

This module defines the replacement: an ``entities:`` mapping where each
entity declares its RX ``sources`` and its ``command`` target explicitly,
validated with pydantic at load time (duplicate source claims and malformed
entries fail loudly instead of silently shadowing each other). The compiler
emits the exact same runtime structures the legacy path produces
(``mapping_dict`` / ``entity_map`` / ``inst_map`` / ``unique_instances``),
so the RX hot path and control path are unchanged.

Format detection lives in ``decode.load_config_data``: a top-level
``entities`` key selects this compiler; otherwise the legacy DGN-first
iterator runs (``config/coach_mapping.default.yml`` still uses it).
"""

import logging
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

logger = logging.getLogger(__name__)

_ENTITY_ID_RE = re.compile(r"^[a-z][a-z0-9_]*[a-z0-9]$")
_DGN_HEX_RE = re.compile(r"^[0-9A-Fa-f]{3,5}$")


class MappingSource(BaseModel):
    """One RX feed for an entity: decoded frames of ``dgn`` at ``instance``."""

    model_config = ConfigDict(extra="forbid")

    dgn: str = Field(..., description="DGN hex, e.g. '1FFE2' (no 0x prefix)")
    instance: int | str = Field(
        ..., description="DGN instance number, or 'default' for instance-agnostic entries"
    )

    @field_validator("dgn")
    @classmethod
    def _dgn_hex(cls, value: str) -> str:
        if not _DGN_HEX_RE.match(value):
            msg = f"dgn must be plain hex like '1FFE2', got {value!r}"
            raise ValueError(msg)
        return value.upper()


class MappingCommand(BaseModel):
    """The TX target for an entity's control commands.

    ``instances`` expresses fan-out (e.g. the bedroom ceiling light is
    physically two dimmer channels, 25 and 26, and the Mira commands both).
    The first listed instance is the entity's primary command instance.
    """

    model_config = ConfigDict(extra="forbid")

    dgn: str = Field(..., description="Command DGN hex, e.g. '1FEF9'")
    instances: list[int] = Field(..., min_length=1, description="Instance(s) to command")

    @field_validator("dgn")
    @classmethod
    def _dgn_hex(cls, value: str) -> str:
        if not _DGN_HEX_RE.match(value):
            msg = f"dgn must be plain hex like '1FEF9', got {value!r}"
            raise ValueError(msg)
        return value.upper()


class MappingEntity(BaseModel):
    """One logical device: RX sources, optional TX command, display metadata."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Human-readable name (friendly_name)")
    type: str = Field(..., description="device_type: light, climate, lock, ...")
    area: str | None = Field(None, description="Zone key, e.g. 'interior.bedroom'")
    capabilities: list[str] = Field(default_factory=list)
    groups: list[str] = Field(default_factory=list)
    read_only: bool = False
    protocol: str | None = Field(None, description="Overrides defaults.protocol")
    interface: str | None = Field(None, description="Overrides defaults.interface")
    sources: list[MappingSource] = Field(..., min_length=1)
    command: MappingCommand | None = None


class EntityMappingDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interface: str = "house"
    protocol: str = "rvc"


class EntityMappingConfig(BaseModel):
    """Validated view of the entity-first sections of a coach mapping file."""

    model_config = ConfigDict(extra="ignore")  # coach_info / areas / scenes live alongside

    defaults: EntityMappingDefaults = Field(default_factory=EntityMappingDefaults)
    entities: dict[str, MappingEntity]

    @model_validator(mode="after")
    def _validate_ids_and_claims(self) -> "EntityMappingConfig":
        claims: dict[tuple[str, str], str] = {}
        for entity_id, entity in self.entities.items():
            if not _ENTITY_ID_RE.match(entity_id):
                msg = f"Invalid entity id {entity_id!r} (want snake_case)"
                raise ValueError(msg)
            for source in entity.sources:
                key = (source.dgn, str(source.instance))
                if key in claims:
                    msg = (
                        f"Duplicate source claim: {entity_id} and {claims[key]} both "
                        f"map DGN {source.dgn} instance {source.instance}"
                    )
                    raise ValueError(msg)
                claims[key] = entity_id
        return self


def compile_entity_mapping(
    device_mapping: dict[str, Any],
) -> tuple[
    dict[tuple[str, str], list[dict[str, Any]]],  # mapping_dict
    dict[tuple[str, str], dict[str, Any]],  # entity_map
    set[str],  # entity_ids
    dict[str, dict[str, Any]],  # inst_map
    dict[str, dict[str, dict[str, Any]]],  # unique_instances
]:
    """Compile an entity-first mapping into the legacy runtime lookups.

    Only declared RX sources register an ``entity_map[(dgn, instance)]``
    entry. Command frames are intent, not authoritative device state; routing
    them back into entities allows delayed command processing to overwrite a
    newer status frame.

    ``inst_map[entity_id]`` always carries the entity's COMMAND addressing
    (primary instance + fan-out list); entities without a command fall back
    to their first source, which the control path never uses for
    non-controllable types. This removes the legacy format's section-order
    dependency where the last-parsed DGN section silently won.
    """
    config = EntityMappingConfig.model_validate(device_mapping)

    mapping_dict: dict[tuple[str, str], list[dict[str, Any]]] = {}
    entity_map: dict[tuple[str, str], dict[str, Any]] = {}
    entity_ids: set[str] = set()
    inst_map: dict[str, dict[str, Any]] = {}
    unique_instances: dict[str, dict[str, dict[str, Any]]] = {}

    for entity_id, entity in config.entities.items():
        entity_ids.add(entity_id)

        device: dict[str, Any] = {
            "entity_id": entity_id,
            "friendly_name": entity.name,
            "device_type": entity.type,
            "capabilities": list(entity.capabilities),
            "interface": entity.interface or config.defaults.interface,
            "protocol": entity.protocol or config.defaults.protocol,
        }
        if entity.area:
            device["area"] = entity.area
        if entity.groups:
            device["groups"] = list(entity.groups)
        if entity.read_only:
            device["read_only"] = True
        if entity.command:
            device["command_dgn"] = entity.command.dgn

        for key in ((source.dgn, str(source.instance)) for source in entity.sources):
            mapping_dict.setdefault(key, []).append(device)
            entity_map[key] = device
            unique_instances.setdefault(key[0], {})[key[1]] = device

        if entity.command:
            inst_entry: dict[str, Any] = {
                "dgn_hex": entity.command.dgn,
                "instance": entity.command.instances[0],
            }
            if len(entity.command.instances) > 1:
                inst_entry["command_instances"] = list(entity.command.instances)
            inst_map[entity_id] = inst_entry
        else:
            first = entity.sources[0]
            inst_map[entity_id] = {"dgn_hex": first.dgn, "instance": first.instance}

    logger.info(
        "Compiled entity-first coach mapping: %d entities, %d (dgn, instance) routes",
        len(entity_ids),
        len(entity_map),
    )
    return mapping_dict, entity_map, entity_ids, inst_map, unique_instances


def is_entity_first_mapping(device_mapping: dict[str, Any]) -> bool:
    """Whether a loaded coach mapping uses the entity-first schema."""
    return isinstance(device_mapping.get("entities"), dict)
