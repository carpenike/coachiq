import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import type { EntitySchema } from "@/api/types/domains"
import { InverterModeCard, ShoreLimitCard } from "@/pages/power"

const { setInputCurrentLimitMock } = vi.hoisted(() => ({
  setInputCurrentLimitMock: vi.fn(),
}))

vi.mock("@/api/victron", () => ({
  fetchVictronStatus: vi.fn(),
  setGeneratorManual: vi.fn(),
  setInputCurrentLimit: setInputCurrentLimitMock,
  setInverterMode: vi.fn(),
}))

function inverterEntity(state: Record<string, unknown>): EntitySchema {
  return {
    entity_id: "victron-inverter",
    name: "Inverter/charger",
    device_type: "inverter",
    protocol: "victron",
    state,
    last_updated: "2026-07-11T12:00:00Z",
    available: true,
  }
}

function renderWithQueryClient(ui: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>)
}

describe("Power selection controls", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setInputCurrentLimitMock.mockResolvedValue({ input_current_limit: 50 })
  })

  it("keeps the current inverter mode selected and focusable", () => {
    renderWithQueryClient(
      <InverterModeCard
        inverter={inverterEntity({ mode: 3, mode_adjustable: 1 })}
        controlsDisabled={false}
      />
    )

    expect(screen.getByRole("radio", { name: "On" })).toBeChecked()
    expect(screen.getByRole("radio", { name: "On" })).not.toBeDisabled()
    expect(screen.getByRole("radio", { name: "Charger only" })).not.toBeChecked()
  })

  it("leaves presets unselected for a custom current limit", () => {
    renderWithQueryClient(
      <ShoreLimitCard
        inverter={inverterEntity({
          input_current_limit: 45,
          input_current_limit_adjustable: 1,
        })}
        controlsDisabled={false}
      />
    )

    for (const preset of screen.getAllByRole("radio")) {
      expect(preset).not.toBeChecked()
    }
  })

  it("applies a selected shore-current preset", async () => {
    const user = userEvent.setup()
    renderWithQueryClient(
      <ShoreLimitCard
        inverter={inverterEntity({
          input_current_limit: 30,
          input_current_limit_adjustable: 1,
        })}
        controlsDisabled={false}
      />
    )

    expect(screen.getByRole("radio", { name: "30 A" })).toBeChecked()
    await user.click(screen.getByRole("radio", { name: "50 A" }))

    await waitFor(() => expect(setInputCurrentLimitMock).toHaveBeenCalledWith(50))
  })
})
