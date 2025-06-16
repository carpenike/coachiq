import {
  IconAnalyze,
  IconBulb,
  IconChartBar,
  IconCircuitSwitchOpen,
  IconCpu,
  IconDashboard,
  IconFileDescription,
  IconFileWord,
  IconHelp,
  IconHeartRateMonitor,
  IconInnerShadowTop,
  IconListDetails,
  IconMapPin,
  IconQuestionMark,
  IconSettings,
  IconShield,
  IconTerminal2,
  IconTool,
  IconWifi,
} from "@tabler/icons-react"
import * as React from "react"

import { NavDiagnostics } from "@/components/nav-diagnostics"
import { NavDocuments } from "@/components/nav-documents"
import { NavMain } from "@/components/nav-main"
import { NavSecondary } from "@/components/nav-secondary"
import { NavSection } from "@/components/nav-section"
import { NavUser } from "@/components/nav-user"
import { SystemStatusIndicator } from "@/components/system-status-indicator"
import { Sidebar, SidebarContent, SidebarFooter, SidebarHeader, SidebarMenu, SidebarMenuButton, SidebarMenuItem } from "@/components/ui/sidebar"

const data = {
  navMain: [
    {
      title: "Dashboard",
      url: "/dashboard",
      icon: IconDashboard,
    },
    {
      title: "Lights",
      url: "/lights",
      icon: IconBulb,
    },
    {
      title: "Entities",
      url: "/entities",
      icon: IconCpu,
    },
  ],
  navMonitoring: [
    {
      title: "CAN Sniffer",
      url: "/can-sniffer",
      icon: IconWifi,
    },
    {
      title: "CAN Tools",
      url: "/can-tools",
      icon: IconTool,
    },
    {
      title: "Network Map",
      url: "/network-map",
      icon: IconMapPin,
    },
    {
      title: "System Status",
      url: "/system-status",
      icon: IconListDetails,
    },
    {
      title: "Health Dashboard",
      url: "/health",
      icon: IconHeartRateMonitor,
    },
    {
      title: "Performance Analytics",
      url: "/performance",
      icon: IconChartBar,
    },
    {
      title: "Analytics Dashboard",
      url: "/analytics-dashboard",
      icon: IconAnalyze,
    },
    {
      title: "Security Dashboard",
      url: "/security",
      icon: IconShield,
    },
  ],
  navDiagnostics: [
    {
      title: "Advanced Diagnostics",
      url: "/diagnostics",
      icon: IconShield,
      badge: false, // TODO: Implement dynamic DTC count notification
    },
    {
      title: "Logs",
      url: "/logs",
      icon: IconTerminal2,
      badge: false, // TODO: Implement dynamic error-level notification
    },
    {
      title: "Unknown PGNs",
      url: "/unknown-pgns",
      icon: IconQuestionMark,
    },
    {
      title: "Unmapped Entries",
      url: "/unmapped-entries",
      icon: IconCircuitSwitchOpen,
    },
  ],
  navSecondary: [
    {
      title: "Configuration",
      url: "/config",
      icon: IconSettings,
    },
    {
      title: "User Settings",
      url: "/settings",
      icon: IconShield,
    },
    {
      title: "Documentation",
      url: "/documentation",
      icon: IconFileDescription,
    },
    {
      title: "RV-C Spec",
      url: "/rvc-spec",
      icon: IconFileWord,
    },
  ],
  navDevelopment: [
    {
      title: "Demo Dashboard",
      url: "/demo-dashboard",
      icon: IconChartBar,
    },
    {
      title: "Theme Test",
      url: "/theme-test",
      icon: IconSettings,
    },
  ],
  documents: [
    {
      name: "Configuration",
      url: "#",
      icon: IconSettings,
    },
    {
      name: "Help",
      url: "#",
      icon: IconHelp,
    },
  ],
}

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {

  return (
    <Sidebar collapsible="offcanvas" {...props}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              className="data-[slot=sidebar-menu-button]:!p-1.5"
            >
              <IconInnerShadowTop className="!size-5" />
              <span className="text-base font-semibold">CoachIQ</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <NavMain items={data.navMain} />
        <NavSection
          title="Monitoring"
          items={data.navMonitoring}
          className="mt-4"
        />
        <NavDiagnostics
          title="Diagnostics"
          items={data.navDiagnostics}
          className="mt-4"
        />
        <NavDocuments items={data.documents} />
        <NavSecondary items={data.navSecondary} className="mt-auto" />

        {/* Development tools - TODO: Hide based on user role (admin vs operator) */}
        <NavSection
          title="Development"
          items={data.navDevelopment}
          className="mt-4 border-t pt-4"
        />
      </SidebarContent>
      <SidebarFooter>
        <SystemStatusIndicator />
        <NavUser />
      </SidebarFooter>
    </Sidebar>
  )
}
