import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { EntitySchema, OperationResultSchema } from "@/api/types/domains";
import { HeatZoneCard, SetpointStepper } from "./climate";

const { mutateMock, toastMock } = vi.hoisted(() => ({
  mutateMock: vi.fn(),
  toastMock: vi.fn()
}));

vi.mock("@/hooks/useEntities", () => ({
  useControlEntity: () => ({ mutate: mutateMock, isPending: false }),
  useEntities: vi.fn()
}));

vi.mock("@/hooks/use-toast", () => ({ toast: toastMock }));

const climateEntity: EntitySchema = {
  entity_id: "climate_front",
  name: "Front climate",
  device_type: "climate",
  protocol: "rvc",
  state: {
    operating_mode: 1,
    setpoint_cool_f: 70
  },
  last_updated: "2026-07-11T12:00:00Z",
  available: true
};

const heatLoopEntity: EntitySchema = {
  entity_id: "climate_bay_heat",
  name: "Bay Heat (Aqua-Hot)",
  device_type: "climate",
  protocol: "rvc",
  state: {
    operating_mode: 0,
    current_temp_f: 79,
    setpoint_heat_f: 70
  },
  capabilities: ["heat_only", "setpoint"],
  supported_commands: ["set"],
  last_updated: "2026-07-11T12:00:00Z",
  available: true
};

interface ICommandCallbacks {
  onSuccess: (result: OperationResultSchema) => void;
  onError: (error: Error) => void;
}

function commandCallbacks(): ICommandCallbacks {
  const callbacks = mutateMock.mock.calls.at(-1)?.at(1) as ICommandCallbacks | undefined;
  if (!callbacks) throw new Error("Expected command callbacks");
  return callbacks;
}

describe("SetpointStepper", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mutateMock.mockReset();
    toastMock.mockReset();
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
  });

  it("coalesces rapid taps and announces pending, sending, and confirmed states", async () => {
    render(<SetpointStepper entity={climateEntity} heatOnly={false} disabled={false} />);

    const raiseButton = screen.getByRole("button", {
      name: "Raise Front climate setpoint"
    });
    fireEvent.click(raiseButton);
    fireEvent.click(raiseButton);

    expect(screen.getByText("72°")).toBeInTheDocument();
    expect(screen.getByText("Setpoint 72 degrees pending")).toHaveAttribute(
      "aria-live",
      "polite"
    );
    expect(mutateMock).not.toHaveBeenCalled();

    await act(async () => vi.advanceTimersByTime(349));
    expect(mutateMock).not.toHaveBeenCalled();

    await act(async () => vi.advanceTimersByTime(1));
    expect(mutateMock).toHaveBeenCalledTimes(1);
    expect(mutateMock).toHaveBeenCalledWith(
      {
        entityId: "climate_front",
        command: { command: "set", parameters: { setpoint_f: 72 } }
      },
      expect.any(Object)
    );
    expect(screen.getByText("Sending setpoint 72 degrees")).toBeInTheDocument();

    const result: OperationResultSchema = {
      operation_id: "setpoint-test",
      entity_id: "climate_front",
      status: "success"
    };
    await act(async () => commandCallbacks().onSuccess(result));

    expect(screen.getByText("Setpoint 72 degrees confirmed")).toBeInTheDocument();

    await act(async () => vi.advanceTimersByTime(1_500));
    expect(screen.getByText("70°")).toBeInTheDocument();
    expect(screen.queryByText(/setpoint 72 degrees/i)).not.toBeInTheDocument();
  });

  it("reverts the optimistic setpoint when the command fails", async () => {
    render(<SetpointStepper entity={climateEntity} heatOnly={false} disabled={false} />);

    fireEvent.click(screen.getByRole("button", { name: "Raise Front climate setpoint" }));
    expect(screen.getByText("71°")).toBeInTheDocument();

    await act(async () => vi.advanceTimersByTime(350));
    await act(async () => commandCallbacks().onError(new Error("control unavailable")));

    expect(screen.getByText("70°")).toBeInTheDocument();
    expect(screen.queryByText(/setpoint 71 degrees/i)).not.toBeInTheDocument();
    expect(toastMock).toHaveBeenCalledWith(
      expect.objectContaining({ title: "Command failed: Front climate" })
    );
  });
});

describe("HeatZoneCard", () => {
  beforeEach(() => {
    mutateMock.mockReset();
    toastMock.mockReset();
  });

  it("separates loop power from setpoint and sends an explicit heat mode", () => {
    render(
      <HeatZoneCard
        entity={heatLoopEntity}
        controlsDisabled={false}
        disabledReason=""
      />
    );

    expect(screen.getByText("Loop heat")).toBeInTheDocument();
    expect(screen.getByText("Setpoint")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("switch", { name: "Bay Heat (Aqua-Hot) heat" }));

    expect(mutateMock).toHaveBeenCalledWith(
      {
        entityId: "climate_bay_heat",
        command: { command: "set", parameters: { mode: "heat" } }
      },
      expect.any(Object)
    );
  });
});
