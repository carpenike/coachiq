import { render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const { adminModuleLoaded } = vi.hoisted(() => ({
  adminModuleLoaded: vi.fn(),
}))

vi.mock("@/pages/admin", () => {
  adminModuleLoaded()
  return {
    default: () => <div>Lazy admin content</div>,
  }
})

describe("app route lazy loading", () => {
  beforeEach(() => {
    vi.resetModules()
    adminModuleLoaded.mockClear()
  })

  it("loads a route module only when rendered and shows a contextual fallback", async () => {
    const { appRoutes } = await import("@/lib/routes")
    const adminRoute = appRoutes.find((route) => route.path === "/admin")

    expect(adminRoute).toBeDefined()
    expect(adminModuleLoaded).not.toHaveBeenCalled()

    render(adminRoute!.element)

    expect(screen.getByRole("status")).toHaveTextContent("Loading Admin...")
    expect(await screen.findByText("Lazy admin content")).toBeInTheDocument()
    expect(adminModuleLoaded).toHaveBeenCalledTimes(1)
  })

  it("shares one module request between preload and render", async () => {
    const { appRoutes } = await import("@/lib/routes")
    const adminRoute = appRoutes.find((route) => route.path === "/admin")

    expect(adminRoute).toBeDefined()
    const firstPreload = adminRoute!.preload()
    const secondPreload = adminRoute!.preload()

    expect(secondPreload).toBe(firstPreload)
    await firstPreload
    render(adminRoute!.element)

    expect(await screen.findByText("Lazy admin content")).toBeInTheDocument()
  })
})
