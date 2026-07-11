/**
 * Route Registry
 *
 * Single source of truth for all protected app routes. Sidebar labels,
 * header title, and page <h1> all derive from this registry — no more
 * triple naming / "Application" fallbacks.
 *
 * Pages not yet rebuilt are temporarily routed to the old page components;
 * later agents replace them one by one.
 */

import type { Icon } from "@tabler/icons-react"
import {
  IconAdjustments,
  IconBolt,
  IconBulb,
  IconCircuitSwitchOpen,
  IconCpu,
  IconFileWord,
  IconHome,
  IconListDetails,
  IconMapPin,
  IconQuestionMark,
  IconRoute,
  IconSettings,
  IconShield,
  IconStethoscope,
  IconTemperature,
  IconTool,
  IconWifi,
} from "@tabler/icons-react"
import { lazy, Suspense, type ComponentType, type ReactElement } from "react"

export type RouteSection = "owner" | "advanced" | "account"

export interface IAppRoute {
  /** Route path (also used as sidebar link target) */
  path: string
  /** Nav label == header title == page h1 */
  title: string
  icon: Icon
  section: RouteSection
  element: ReactElement
  /** Warm the route module without rendering it. */
  preload: () => Promise<unknown>
  /** Only render in nav / allow for admin users */
  adminOnly?: boolean
}

interface IPageModule {
  default: ComponentType
}
type PageLoader = () => Promise<IPageModule>

export function RouteLoadingFallback({ title }: Readonly<{ title: string }>) {
  return (
    <div
      className="flex min-h-48 items-center justify-center gap-3 p-6 text-sm text-muted-foreground"
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <span
        className="size-5 animate-spin rounded-full border-2 border-muted border-t-primary motion-reduce:animate-none"
        aria-hidden="true"
      />
      <span>Loading {title}...</span>
    </div>
  )
}

function lazyPage(title: string, preload: PageLoader) {
  let modulePromise: Promise<IPageModule> | undefined
  const load = () => {
    modulePromise ??= preload()
    return modulePromise
  }
  const Page = lazy(load)

  return {
    element: (
      <Suspense fallback={<RouteLoadingFallback title={title} />}>
        <Page />
      </Suspense>
    ),
    preload: load,
  }
}

export const appRoutes: IAppRoute[] = [
  // ===== Owner section =====
  { path: "/", title: "Home", icon: IconHome, section: "owner", ...lazyPage("Home", () => import("@/pages/home")) },
  { path: "/lights", title: "Lights", icon: IconBulb, section: "owner", ...lazyPage("Lights", () => import("@/pages/lights")) },
  { path: "/climate", title: "Climate", icon: IconTemperature, section: "owner", ...lazyPage("Climate", () => import("@/pages/climate")) },
  { path: "/power", title: "Power", icon: IconBolt, section: "owner", ...lazyPage("Power", () => import("@/pages/power")) },
  { path: "/location", title: "Location", icon: IconRoute, section: "owner", ...lazyPage("Location", () => import("@/pages/location")) },
  { path: "/devices", title: "Devices", icon: IconCpu, section: "owner", ...lazyPage("Devices", () => import("@/pages/devices")) },
  { path: "/diagnostics", title: "Diagnostics", icon: IconStethoscope, section: "owner", ...lazyPage("Diagnostics", () => import("@/pages/diagnostics")) },
  { path: "/system", title: "System", icon: IconListDetails, section: "owner", ...lazyPage("System", () => import("@/pages/system")) },

  // ===== Advanced (technician) section =====
  { path: "/advanced/can-sniffer", title: "CAN Sniffer", icon: IconWifi, section: "advanced", ...lazyPage("CAN Sniffer", () => import("@/pages/can-sniffer")) },
  { path: "/advanced/can-tools", title: "CAN Tools", icon: IconTool, section: "advanced", ...lazyPage("CAN Tools", () => import("@/pages/can-tools")) },
  { path: "/advanced/network-map", title: "Network Map", icon: IconMapPin, section: "advanced", ...lazyPage("Network Map", () => import("@/pages/network-map")) },
  { path: "/advanced/unknown-pgns", title: "Unknown PGNs", icon: IconQuestionMark, section: "advanced", ...lazyPage("Unknown PGNs", () => import("@/pages/unknown-pgns")) },
  { path: "/advanced/unmapped-entries", title: "Unmapped Entries", icon: IconCircuitSwitchOpen, section: "advanced", ...lazyPage("Unmapped Entries", () => import("@/pages/unmapped-entries")) },
  { path: "/advanced/device-mapping", title: "Device Mapping", icon: IconAdjustments, section: "advanced", ...lazyPage("Device Mapping", () => import("@/pages/device-mapping")) },
  { path: "/advanced/rvc-spec", title: "RV-C Spec", icon: IconFileWord, section: "advanced", ...lazyPage("RV-C Spec", () => import("@/pages/rvc-spec")) },

  // ===== Account section =====
  { path: "/account", title: "Account", icon: IconSettings, section: "account", ...lazyPage("Account", () => import("@/pages/account")) },
  { path: "/admin", title: "Admin", icon: IconShield, section: "account", ...lazyPage("Admin", () => import("@/pages/admin")), adminOnly: true },
]

/** Routes for a given sidebar section, in registry order. */
export function routesForSection(section: RouteSection): IAppRoute[] {
  return appRoutes.filter((route) => route.section === section)
}

/**
 * Resolve the registry entry matching a location pathname.
 * Exact match wins; falls back to the longest non-root prefix match
 * (so nested paths still highlight/title their parent).
 */
export function findRouteByPath(pathname: string): IAppRoute | undefined {
  const exact = appRoutes.find((route) => route.path === pathname)
  if (exact) return exact

  return appRoutes
    .filter((route) => route.path !== "/" && pathname.startsWith(`${route.path}/`))
    .sort((a, b) => b.path.length - a.path.length)[0]
}

/** Header/page title for a pathname; undefined when the path is not registered. */
export function titleForPath(pathname: string): string | undefined {

  return findRouteByPath(pathname)?.title
}
