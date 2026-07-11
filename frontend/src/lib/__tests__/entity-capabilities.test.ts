import { describe, expect, it } from "vitest";

import type { EntitySchema } from "@/api/types/domains";
import {
  entitySupportsBrightnessControl,
  entitySupportsPowerControl,
  getEntityCapabilityPolicy
} from "@/lib/entity-capabilities";

function makeEntity(overrides: Partial<EntitySchema> = {}): EntitySchema {
  return {
    entity_id: "light_1",
    name: "Light",
    device_type: "light",
    protocol: "rvc",
    state: { operating_status: 100 },
    area: null,
    last_updated: "2026-07-11T00:00:00Z",
    available: true,
    ...overrides
  };
}

describe("entity capability policy", () => {
  it("marks the compatibility policy explicitly when both server fields are absent", () => {
    const entity = makeEntity();
    const policy = getEntityCapabilityPolicy(entity);

    expect(policy.source).toBe("compatibility-fallback");
    expect(policy.isCompatibilityFallback).toBe(true);
    expect(entitySupportsPowerControl(entity)).toBe(true);
    expect(entitySupportsBrightnessControl(entity)).toBe(true);
  });

  it("treats explicitly empty server metadata as authoritative", () => {
    const entity = makeEntity({ capabilities: [], supported_commands: [] });
    const policy = getEntityCapabilityPolicy(entity);

    expect(policy.source).toBe("server");
    expect(policy.isCompatibilityFallback).toBe(false);
    expect(entitySupportsPowerControl(entity)).toBe(false);
    expect(entitySupportsBrightnessControl(entity)).toBe(false);
  });

  it("uses server capabilities and commands instead of device type or observed state", () => {
    const entity = makeEntity({
      device_type: "sensor",
      state: {},
      capabilities: ["on_off", "dimmable"],
      supported_commands: ["set", "toggle"]
    });

    expect(entitySupportsPowerControl(entity)).toBe(true);
    expect(entitySupportsBrightnessControl(entity)).toBe(true);
  });
});
