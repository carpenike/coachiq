import { AppLayout } from "@/components/app-layout"
import { ChartAreaInteractive } from "@/components/chart-area-interactive"
import { DataTable } from "@/components/data-table"
import { SectionCards } from "@/components/section-cards"

import data from "./demo-dashboard-data.json"

export default function DemoDashboard() {
  return (
    <AppLayout pageTitle="Demo Dashboard" sidebarVariant="inset">
      <div className="flex-1 space-y-6 p-4 pt-6">
        <SectionCards />
        <ChartAreaInteractive />
        <DataTable data={data} />
      </div>
    </AppLayout>
  )
}
