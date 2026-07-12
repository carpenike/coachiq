import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { CoachConnectionPill } from "@/components/app-shell"

vi.mock("@/contexts/coach-connection-context", () => ({
  useCoachConnection: () => ({
    coach: "STALE",
    reason: "Coach updates have paused",
    lastDataAt: new Date("2026-07-11T12:30:00Z"),
  }),
}))

describe("CoachConnectionPill", () => {
  it("announces static connection detail as status text", () => {
    render(<CoachConnectionPill />)

    expect(
      screen.getByRole("status", { name: /Stale\. Coach updates have paused\. Last data/i })
    ).toHaveTextContent("Stale")
  })
})
