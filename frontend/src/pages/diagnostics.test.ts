import { describe, expect, it } from "vitest";

import { deriveDiagnosticsVerdict } from "./diagnostics";

const healthyStatus = {
  overall_health: "excellent",
  health_score: 98,
  active_systems: ["rvc"],
  degraded_systems: [],
  last_assessment: 1_783_776_000
};

const emptyCollection = {
  dtcs: [],
  total_count: 0,
  active_count: 0,
  by_severity: {},
  by_protocol: {}
};

const activeCriticalDtc = {
  code: 101,
  protocol: "rvc",
  system_type: "climate",
  severity: "critical",
  first_occurrence: 1_783_776_000,
  last_occurrence: 1_783_776_100,
  occurrence_count: 2,
  source_address: 12,
  pgn: 65_280,
  dgn: null,
  description: "Climate controller offline",
  active: true,
  intermittent: false,
  resolved: false,
  acknowledged: false
};

describe("deriveDiagnosticsVerdict", () => {
  it("uses the authoritative backend verdict when present", () => {
    const verdict = deriveDiagnosticsVerdict(
      "LIVE",
      {
        ...healthyStatus,
        verdict: {
          code: "degraded" as const,
          label: "Attention needed",
          severity: "warning" as const,
          reason_codes: ["command_emission_halted"],
          requires_attention: true,
          data_freshness: "current" as const
        }
      },
      emptyCollection
    );

    expect(verdict).toEqual({
      label: "Attention needed",
      detail: "CoachIQ command emission is halted",
      tone: "warning"
    });
  });

  it("gives active critical faults precedence over an excellent backend score", () => {
    const verdict = deriveDiagnosticsVerdict("LIVE", healthyStatus, {
      ...emptyCollection,
      dtcs: [activeCriticalDtc],
      total_count: 1,
      active_count: 1,
      by_severity: { critical: 1 },
      by_protocol: { rvc: 1 }
    });

    expect(verdict).toEqual({
      label: "Action required",
      detail: "1 active critical or high severity fault",
      tone: "critical"
    });
  });

  it("does not show a healthy verdict when a system is degraded", () => {
    const verdict = deriveDiagnosticsVerdict(
      "LIVE",
      { ...healthyStatus, degraded_systems: ["can_gateway"] },
      emptyCollection
    );

    expect(verdict.label).toBe("Attention needed");
    expect(verdict.tone).toBe("warning");
  });

  it("labels clean stale data as last known instead of excellent", () => {
    const verdict = deriveDiagnosticsVerdict("STALE", healthyStatus, emptyCollection);

    expect(verdict.label).toBe("Last known health");
    expect(verdict.tone).toBe("neutral");
  });

  it("shows the backend health only for clean live data", () => {
    const verdict = deriveDiagnosticsVerdict("LIVE", healthyStatus, emptyCollection);

    expect(verdict.label).toBe("Excellent");
    expect(verdict.tone).toBe("healthy");
  });
});
