import type { EntitySchema } from "@/api/types/domains";
import { describe, expect, it } from "vitest";

import { entitySupportsHomeToggle } from "./home";

function entity(deviceType: string): EntitySchema {
  return {
    entity_id: `test-${deviceType}`,
    name: `Test ${deviceType}`,
    device_type: deviceType,
    protocol: "rvc",
    state: {},
    last_updated: "2026-07-11T12:00:00Z",
    available: true
  };
}

describe("Home toggle capability policy", () => {
  it("allows only explicit light controls", () => {
    expect(entitySupportsHomeToggle(entity("light"))).toBe(true);
    expect(entitySupportsHomeToggle(entity("lock"))).toBe(false);
  });

  it.each(["climate", "tank", "temperature", "water_heater", "ac_load"])(
    "keeps %s telemetry read only",
    (deviceType) => {
      expect(entitySupportsHomeToggle(entity(deviceType))).toBe(false);
    }
  );
});
