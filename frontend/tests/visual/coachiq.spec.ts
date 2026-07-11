import { expect, test, type Page } from "@playwright/test"

const now = "2025-01-15T15:16:00.000Z"
const nowSeconds = Date.parse(now) / 1000

const entities = [
  {
    entity_id: "living_light",
    name: "Living Ceiling",
    device_type: "light",
    protocol: "rvc",
    state: { operating_status: 150, brightness: 75 },
    area: "interior.living_main",
    available: true,
    capabilities: ["on_off", "brightness"],
    supported_commands: ["set", "toggle", "brightness_up", "brightness_down"],
    last_updated: now,
    last_seen_at: now,
    data_received_at: now,
    state_changed_at: now
  },
  {
    entity_id: "fresh_tank",
    name: "Fresh Water",
    device_type: "tank",
    protocol: "rvc",
    state: { level: 73 },
    area: "exterior.basement",
    available: true,
    capabilities: ["level"],
    supported_commands: [],
    last_updated: now,
    last_seen_at: now,
    data_received_at: now,
    state_changed_at: now
  }
]

async function mockCoachApi(page: Page) {
  const json = (route: Parameters<Parameters<Page["route"]>[1]>[0], body: unknown) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) })

  await page.route("**/*", async (route) => {
    const path = new URL(route.request().url()).pathname
    if (!path.startsWith("/api/")) return route.continue()
    if (route.request().method() !== "GET") {
      return route.fulfill({ status: 503, contentType: "application/json", body: "{}" })
    }
    if (path === "/api/auth/status") {
      return json(route, {
        enabled: false,
        mode: "none",
        jwt_available: false,
        magic_links_enabled: false,
        oidc_enabled: false
      })
    }
    if (path === "/api/events") {
      return route.fulfill({ status: 200, contentType: "text/event-stream", body: ": heartbeat\n\n" })
    }
    if (path === "/api/v1/networks/status") {
      return json(route, {
        interfaces: [
          {
            logical_name: "house",
            physical_interface: "can1",
            state: "UP",
            bitrate: 250000,
            message_rate: 42,
            bus_load_percent: 8,
            rx_packets: 100,
            tx_packets: 10,
            rx_errors: 0,
            tx_errors: 0,
            bus_errors: 0,
            last_activity: now
          }
        ],
        can_service_health: { healthy: true }
      })
    }
    if (path === "/api/v1/entities/config/coach") {
      return json(route, {
        coach_info: {},
        areas: {
          interior: {
            display_name: "Interior",
            zones: { living_main: { display_name: "Living Area" } }
          }
        },
        lighting_scenes: {
          all_off: { name: "All Off", action: "off", entities: ["*_light"] }
        },
        lighting_groups: {}
      })
    }
    if (path === "/api/v1/entities") {
      return json(route, {
        entities,
        total_count: entities.length,
        page: 1,
        page_size: 100,
        has_next: false,
        filters_applied: {}
      })
    }
    if (path === "/api/v1/diagnostics/system-status") {
      return json(route, {
        overall_health: "excellent",
        health_score: 98,
        active_systems: ["rvc"],
        degraded_systems: ["diagnostics"],
        last_assessment: nowSeconds,
        verdict: {
          code: "action_required",
          label: "Action required",
          severity: "critical",
          reason_codes: ["active_critical_dtc"],
          requires_attention: true,
          data_freshness: "current"
        }
      })
    }
    if (path === "/api/v1/diagnostics/statistics") {
      return json(route, {
        metrics: {
          total_dtcs: 1,
          active_dtcs: 1,
          resolved_dtcs: 0,
          processing_rate: 1,
          system_health_trend: "stable"
        }
      })
    }
    if (path === "/api/v1/diagnostics/dtcs") {
      return json(route, {
        dtcs: [
          {
            code: 101,
            protocol: "rvc",
            system_type: "climate",
            severity: "critical",
            first_occurrence: nowSeconds,
            last_occurrence: nowSeconds,
            occurrence_count: 4,
            source_address: 12,
            pgn: 65280,
            dgn: null,
            description: "Climate controller offline",
            active: true,
            intermittent: false,
            resolved: false,
            acknowledged: false
          }
        ],
        total_count: 1,
        active_count: 1,
        by_severity: { critical: 1 },
        by_protocol: { rvc: 1 }
      })
    }
    return json(route, {})
  })
}

test.beforeEach(async ({ page }) => {
  await mockCoachApi(page)
  await page.goto("/")
  await expect(page.getByRole("heading", { name: "Home" })).toBeVisible()
})

test("home is responsive and only renders real controls", async ({ page, isMobile }) => {
  const dimensions = await page.locator("body").evaluate((body) => ({
    clientWidth: body.clientWidth,
    scrollWidth: body.scrollWidth
  }))
  expect(dimensions.scrollWidth).toBe(dimensions.clientWidth)
  await expect(page.getByRole("switch", { name: "Toggle Living Ceiling" })).toBeVisible()
  await expect(page.getByRole("switch", { name: /Fresh Water/ })).toHaveCount(0)

  if (isMobile) {
    const smallTargets = await page
      .locator("main button, main [role=switch]")
      .evaluateAll((nodes) =>
        nodes
          .map((node) => ({
            label: node.getAttribute("aria-label") ?? node.textContent?.trim(),
            rect: node.getBoundingClientRect(),
            visible: getComputedStyle(node).visibility !== "hidden"
          }))
          .filter(({ rect, visible }) => visible && rect.width > 0 && rect.height > 0)
          .filter(({ rect }) => rect.width < 44 || rect.height < 44)
          .map(({ label, rect }) => ({ label, width: rect.width, height: rect.height }))
      )
    expect(smallTargets).toEqual([])
  }
  await expect(page).toHaveScreenshot("home.png", {
    fullPage: true,
    animations: "disabled"
  })
})

test("mobile drawer closes and restores trigger focus", async ({ page, isMobile }) => {
  test.skip(!isMobile, "mobile-only behavior")
  const trigger = page.getByRole("button", { name: "Toggle Sidebar" })
  await trigger.click()
  await page.getByRole("link", { name: "Home", exact: true }).click()
  await expect(page.getByRole("dialog", { name: "Sidebar" })).toHaveCount(0)
  await expect(trigger).toBeFocused()
})

test("reduced motion disables sheet animation", async ({ page, isMobile }) => {
  test.skip(!isMobile, "mobile-only behavior")
  await page.emulateMedia({ reducedMotion: "reduce" })
  await page.getByRole("button", { name: "Toggle Sidebar" }).click()
  const motion = await page.locator("[data-mobile=true]").evaluate((element) => {
    const style = getComputedStyle(element)
    return { animationName: style.animationName, transitionDuration: style.transitionDuration }
  })
  expect(motion.animationName).toBe("none")
  expect(Number.parseFloat(motion.transitionDuration)).toBeLessThanOrEqual(0.001)
})

test("critical diagnostics remain visible without horizontal scrolling", async ({ page }) => {
  await page.goto("/diagnostics")
  await expect(page.getByRole("heading", { name: "Diagnostics" })).toBeVisible()
  await expect(page.getByText("Action required")).toBeVisible()
  await expect(page.getByText("Climate controller offline").filter({ visible: true }).first()).toBeVisible()
  await expect(page.getByText("score 98/100")).toHaveCount(0)
  const dimensions = await page.locator("body").evaluate((body) => ({
    clientWidth: body.clientWidth,
    scrollWidth: body.scrollWidth
  }))
  expect(dimensions.scrollWidth).toBe(dimensions.clientWidth)
  await expect(page).toHaveScreenshot("diagnostics.png", {
    fullPage: true,
    animations: "disabled"
  })
})
