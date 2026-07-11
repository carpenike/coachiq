import { describe, expect, it } from "vitest";

import {
  buildJ1939InjectionRequest,
  buildRawInjectionRequest,
} from "../can-tools";

describe("CAN injection request review builders", () => {
  it("requires an operator reason for burst injection", () => {
    expect(() =>
      buildRawInjectionRequest({
        canIdInput: "0x123",
        dataInput: "01 02",
        interfaceInput: "can0",
        mode: "burst",
        count: "5",
        interval: "1",
        duration: "0",
        description: "Diagnostic burst",
        reason: "   ",
      })
    ).toThrow("A reason is required for burst and periodic injection");
  });

  it("normalizes and validates a periodic request without sending it", () => {
    expect(
      buildRawInjectionRequest({
        canIdInput: "0x18FEEE00",
        dataInput: "01 02 0a ff",
        interfaceInput: "can1",
        mode: "periodic",
        count: "1",
        interval: "0.5",
        duration: "10",
        description: "Temperature probe",
        reason: "Verify decoder behavior",
      })
    ).toEqual({
      can_id: 0x18feee00,
      data: "01020AFF",
      interface: "can1",
      mode: "periodic",
      interval: 0.5,
      duration: 10,
      description: "Temperature probe",
      reason: "Verify decoder behavior",
    });
  });

  it("forces the J1939 helper to a reviewed single-message request", () => {
    expect(
      buildJ1939InjectionRequest({
        pgnInput: "FEEE",
        dataInput: "01 02",
        priorityInput: "6",
        sourceAddressInput: "254",
        destinationAddressInput: "255",
        interfaceInput: "can0",
      })
    ).toMatchObject({
      pgn: 0xfeee,
      data: "0102",
      priority: 6,
      source_address: 254,
      destination_address: 255,
      interface: "can0",
      mode: "single",
    });
  });
});
