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
  IconBulb,
  IconCircuitSwitchOpen,
  IconCpu,
  IconFileWord,
  IconHome,
  IconListDetails,
  IconMapPin,
  IconQuestionMark,
  IconSettings,
  IconShield,
  IconStethoscope,
  IconTemperature,
  IconTool,
  IconWifi,
} from "@tabler/icons-react"
import type { ReactElement } from "react"

import AdminPage from "@/pages/admin"
import HomePage from "@/pages/home"
// Temporary routings to old pages (to be replaced by later agents):
import CanSniffer from "@/pages/can-sniffer"
import CanTools from "@/pages/can-tools"
import DeviceMapping from "@/pages/device-mapping"
import ClimatePage from "@/pages/climate"
import DevicesPage from "@/pages/devices"
import DiagnosticsPage from "@/pages/diagnostics"
import Lights from "@/pages/lights"
import NetworkMap from "@/pages/network-map"
import RVCSpec from "@/pages/rvc-spec"
import AccountPage from "@/pages/account"
import SystemPage from "@/pages/system"
import UnknownPGNs from "@/pages/unknown-pgns"
import UnmappedEntries from "@/pages/unmapped-entries"

export type RouteSection = "owner" | "advanced" | "account"

export interface IAppRoute {
  /** Route path (also used as sidebar link target) */
  path: string
  /** Nav label == header title == page h1 */
  title: string
  icon: Icon
  section: RouteSection
  element: ReactElement
  /** Only render in nav / allow for admin users */
  adminOnly?: boolean
}

export const appRoutes: IAppRoute[] = [
  // ===== Owner section =====
  { path: "/", title: "Home", icon: IconHome, section: "owner", element: <HomePage /> },
  { path: "/lights", title: "Lights", icon: IconBulb, section: "owner", element: <Lights /> },
  { path: "/climate", title: "Climate", icon: IconTemperature, section: "owner", element: <ClimatePage /> },
  { path: "/devices", title: "Devices", icon: IconCpu, section: "owner", element: <DevicesPage /> },
  { path: "/diagnostics", title: "Diagnostics", icon: IconStethoscope, section: "owner", element: <DiagnosticsPage /> },
  { path: "/system", title: "System", icon: IconListDetails, section: "owner", element: <SystemPage /> },

  // ===== Advanced (technician) section =====
  { path: "/advanced/can-sniffer", title: "CAN Sniffer", icon: IconWifi, section: "advanced", element: <CanSniffer /> },
  { path: "/advanced/can-tools", title: "CAN Tools", icon: IconTool, section: "advanced", element: <CanTools /> },
  { path: "/advanced/network-map", title: "Network Map", icon: IconMapPin, section: "advanced", element: <NetworkMap /> },
  { path: "/advanced/unknown-pgns", title: "Unknown PGNs", icon: IconQuestionMark, section: "advanced", element: <UnknownPGNs /> },
  { path: "/advanced/unmapped-entries", title: "Unmapped Entries", icon: IconCircuitSwitchOpen, section: "advanced", element: <UnmappedEntries /> },
  { path: "/advanced/device-mapping", title: "Device Mapping", icon: IconAdjustments, section: "advanced", element: <DeviceMapping /> },
  { path: "/advanced/rvc-spec", title: "RV-C Spec", icon: IconFileWord, section: "advanced", element: <RVCSpec /> },

  // ===== Account section =====
  { path: "/account", title: "Account", icon: IconSettings, section: "account", element: <AccountPage /> },
  { path: "/admin", title: "Admin", icon: IconShield, section: "account", element: <AdminPage />, adminOnly: true },
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
