import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import type { EntitySchema } from "@/api/types/domains"
import { DevicePowerControl } from "@/pages/devices"
import { ToggleDeviceRow } from "@/pages/home"
import { LightRow } from "@/pages/lights"

const { mutateMock } = vi.hoisted(() => ({ mutateMock: vi.fn() }))

vi.mock("@/hooks/useEntities", () => ({
  useBulkControlEntities: vi.fn(),
  useControlEntity: () => ({ mutate: mutateMock, isPending: false }),
  useEntities: vi.fn(),
}))

vi.mock("@/components/ui/slider", () => ({
  Slider: ({
    value,
    onValueChange,
    onValueCommit,
    "aria-label": ariaLabel,
  }: {
    value: number[]
    onValueChange?: (value: number[]) => void
    onValueCommit?: (value: number[]) => void
    "aria-label"?: string
  }) => (
    <div role="slider" aria-label={ariaLabel} aria-valuenow={value[0]}>
      <button type="button" onClick={() => onValueChange?.([65])}>
        Drag brightness
      </button>
      <button type="button" onClick={() => onValueCommit?.([65])}>
        Commit brightness
      </button>
    </div>
  ),
}))

function lightEntity(): EntitySchema {
  return {
    entity_id: "galley-light",
    name: "Galley light",
    device_type: "light",
    protocol: "rvc",
    state: { state: "on", brightness: 40 },
    last_updated: "2026-07-11T12:00:00Z",
    available: true,
  }
}

describe("binary control semantics", () => {
  beforeEach(() => vi.clearAllMocks())

  it("sends the Home switch's explicit target state", async () => {
    const user = userEvent.setup()
    render(
      <ToggleDeviceRow
        entity={lightEntity()}
        controlsDisabled={false}
        disabledReason=""
        showTimestamps={false}
      />
    )

    await user.click(screen.getByRole("switch", { name: "Galley light" }))

    expect(mutateMock).toHaveBeenCalledWith(
      {
        entityId: "galley-light",
        command: { command: "set", state: false },
      },
      expect.any(Object)
    )
  })

  it("sends the Lights switch's explicit target state", async () => {
    const user = userEvent.setup()
    render(
      <LightRow
        entity={lightEntity()}
        controlsDisabled={false}
        disabledReason=""
        showTimestamp={false}
      />
    )

    await user.click(screen.getByRole("switch", { name: "Galley light" }))

    expect(mutateMock).toHaveBeenCalledWith(
      {
        entityId: "galley-light",
        command: { command: "set", state: false },
      },
      expect.any(Object)
    )
  })
})

describe("direct manipulation and inventory semantics", () => {
  beforeEach(() => vi.clearAllMocks())

  it("tracks a Home brightness drag locally and sends only on commit", async () => {
    const user = userEvent.setup()
    render(
      <ToggleDeviceRow
        entity={lightEntity()}
        controlsDisabled={false}
        disabledReason=""
        showTimestamps={false}
      />
    )

    await user.click(screen.getByRole("button", { name: "Drag brightness" }))

    expect(screen.getByText("65%")).toBeInTheDocument()
    expect(mutateMock).not.toHaveBeenCalled()

    await user.click(screen.getByRole("button", { name: "Commit brightness" }))

    expect(mutateMock).toHaveBeenCalledWith(
      {
        entityId: "galley-light",
        command: { command: "set", state: true, brightness: 65 },
      },
      expect.any(Object)
    )
  })

  it("presents one labeled device power switch", async () => {
    const onCheckedChange = vi.fn()
    const user = userEvent.setup()
    render(
      <DevicePowerControl
        checked
        disabled={false}
        entityName="Water pump"
        onCheckedChange={onCheckedChange}
      />
    )

    expect(screen.queryByRole("button", { name: /turn on|turn off|toggle/i })).not.toBeInTheDocument()
    await user.click(screen.getByRole("switch", { name: "Water pump power" }))
    expect(onCheckedChange).toHaveBeenCalledWith(false)
  })

  it("does not present an unknown device state as off", () => {
    render(
      <DevicePowerControl
        checked={null}
        disabled={false}
        entityName="Unreported light"
        onCheckedChange={vi.fn()}
      />
    )

    expect(screen.getByText("State unavailable")).toBeInTheDocument()
    expect(screen.getByRole("switch", { name: "Unreported light power" })).toBeDisabled()
  })
})
