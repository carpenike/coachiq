/**
 * App Shell — single layout route for all protected pages.
 *
 * Sidebar, header title, and page identity all derive from the route
 * registry (src/lib/routes.tsx). The header shows the coach connection
 * pill (LIVE/STALE/OFFLINE) from CoachConnectionProvider — the only
 * component allowed to render a connectivity verdict.
 */

import {
  IconChevronRight,
  IconInnerShadowTop,
} from "@tabler/icons-react"
import * as React from "react"
import { Link, Outlet, useLocation } from "react-router-dom"

import { ConnectionBanner } from "@/components/connection-banner"
import { RouteErrorBoundary } from "@/components/error-boundary"
import { ModeToggle } from "@/components/mode-toggle"
import { NavUser } from "@/components/nav-user"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import { Separator } from "@/components/ui/separator"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { useAuth } from "@/contexts"
import { useCoachConnection, type CoachState } from "@/contexts/coach-connection"
import { findRouteByPath, routesForSection, titleForPath, type AppRoute } from "@/lib/routes"
import { cn } from "@/lib/utils"

//
// ===== Connection pill =====
//

interface PillStyle {
  dot: string
  text: string
  label: string
}

const OFFLINE_PILL: PillStyle = {
  dot: "bg-red-500",
  text: "text-red-700 dark:text-red-400 border-red-300 dark:border-red-800",
  label: "Offline",
}

const PILL_STYLES = new Map<CoachState, PillStyle>([
  [
    "LIVE",
    {
      dot: "bg-green-500",
      text: "text-green-700 dark:text-green-400 border-green-300 dark:border-green-800",
      label: "Live",
    },
  ],
  [
    "STALE",
    {
      dot: "bg-amber-500",
      text: "text-amber-700 dark:text-amber-400 border-amber-300 dark:border-amber-800",
      label: "Stale",
    },
  ],
  ["OFFLINE", OFFLINE_PILL],
])

export function CoachConnectionPill() {
  const { coach, reason, lastDataAt } = useCoachConnection()
  const style = PILL_STYLES.get(coach) ?? OFFLINE_PILL

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          className={cn(
            "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium",
            style.text
          )}
        >
          <span className={cn("size-2 rounded-full", style.dot)} aria-hidden />
          {style.label}
        </span>
      </TooltipTrigger>
      <TooltipContent side="bottom">
        <p>{reason}</p>
        {lastDataAt && coach !== "LIVE" && (
          <p className="text-muted-foreground">
            Last data {lastDataAt.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}
          </p>
        )}
      </TooltipContent>
    </Tooltip>
  )
}

//
// ===== Sidebar =====
//

function NavRouteItem({ route, currentPath }: Readonly<{ route: AppRoute; currentPath: string }>) {
  const isActive =
    route.path === "/" ? currentPath === "/" : currentPath.startsWith(route.path)
  return (
    <SidebarMenuItem>
      <SidebarMenuButton tooltip={route.title} asChild isActive={isActive}>
        <Link to={route.path}>
          <route.icon />
          <span>{route.title}</span>
        </Link>
      </SidebarMenuButton>
    </SidebarMenuItem>
  )
}

function AppShellSidebar(props: React.ComponentProps<typeof Sidebar>) {
  const location = useLocation()
  const { user, authStatus } = useAuth()
  const isAdmin = user?.role === "admin" || authStatus?.mode === "none"

  const ownerRoutes = routesForSection("owner")
  const advancedRoutes = routesForSection("advanced")
  const accountRoutes = routesForSection("account").filter(
    (route) => !route.adminOnly || isAdmin
  )

  const advancedActive = advancedRoutes.some((route) =>
    location.pathname.startsWith(route.path)
  )

  return (
    <Sidebar collapsible="offcanvas" {...props}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton asChild className="data-[slot=sidebar-menu-button]:!p-1.5">
              <Link to="/">
                <IconInnerShadowTop className="!size-5" />
                <span className="text-base font-semibold">CoachIQ</span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              {ownerRoutes.map((route) => (
                <NavRouteItem key={route.path} route={route} currentPath={location.pathname} />
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <Collapsible defaultOpen={advancedActive} className="group/advanced">
          <SidebarGroup>
            <SidebarGroupLabel asChild>
              <CollapsibleTrigger className="w-full">
                Advanced
                <IconChevronRight className="ml-auto size-4 transition-transform group-data-[state=open]/advanced:rotate-90" />
              </CollapsibleTrigger>
            </SidebarGroupLabel>
            <CollapsibleContent>
              <SidebarGroupContent>
                <SidebarMenu>
                  {advancedRoutes.map((route) => (
                    <NavRouteItem
                      key={route.path}
                      route={route}
                      currentPath={location.pathname}
                    />
                  ))}
                </SidebarMenu>
              </SidebarGroupContent>
            </CollapsibleContent>
          </SidebarGroup>
        </Collapsible>
      </SidebarContent>
      <SidebarFooter>
        <SidebarMenu>
          {accountRoutes.map((route) => (
            <NavRouteItem key={route.path} route={route} currentPath={location.pathname} />
          ))}
        </SidebarMenu>
        <NavUser />
      </SidebarFooter>
    </Sidebar>
  )
}

//
// ===== Header =====
//

function AppShellHeader() {
  const location = useLocation()
  const title = titleForPath(location.pathname) ?? "CoachIQ"

  return (
    <header className="flex h-(--header-height) shrink-0 items-center gap-2 border-b transition-[width,height] ease-linear group-has-data-[collapsible=icon]/sidebar-wrapper:h-(--header-height)">
      <div className="flex w-full items-center gap-1 px-4 lg:gap-2 lg:px-6">
        <SidebarTrigger className="-ml-1" />
        <Separator orientation="vertical" className="mx-2 data-[orientation=vertical]:h-4" />
        <h1 className="text-base font-medium">{title}</h1>
        <div className="ml-auto flex items-center gap-2">
          <CoachConnectionPill />
          <ModeToggle />
        </div>
      </div>
    </header>
  )
}

//
// ===== Shell (layout route) =====
//

export function AppShell() {
  const location = useLocation()

  return (
    <SidebarProvider
      style={
        {
          "--sidebar-width": "calc(var(--spacing) * 72)",
          "--header-height": "calc(var(--spacing) * 12)",
        } as React.CSSProperties
      }
    >
      <AppShellSidebar variant="inset" />
      <SidebarInset>
        <AppShellHeader />
        <ConnectionBanner />
        <div className="flex min-h-[calc(100vh-var(--header-height))] flex-1 flex-col">
          <main className="@container/main flex flex-1 flex-col gap-2">
            <RouteErrorBoundary key={findRouteByPath(location.pathname)?.path ?? location.pathname}>
              <Outlet />
            </RouteErrorBoundary>
          </main>
        </div>
      </SidebarInset>
    </SidebarProvider>
  )
}
