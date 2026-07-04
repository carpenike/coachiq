/**
 * Device Mapping Page
 *
 * Manages device instance mappings and configurations.
 * Provides interface for viewing and editing device-to-entity relationships.
 */

import type { EntityData } from "@/api/types"
import { AppLayout } from "@/components/app-layout"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useCoachConfig, zoneDisplayName, type ICoachConfig } from "@/hooks/useCoachConfig"
import { useEntities } from "@/hooks/useEntities"
import { collectionToDisplayEntities } from "@/utils/entity-display"
import {
  IconAlertCircle,
  IconDeviceDesktop,
  IconDeviceGamepad,
  IconInfoCircle,
  IconMapPin,
  IconRefresh,
  IconSettings
} from "@tabler/icons-react"
import { useMemo } from "react"

/**
 * An entity counts as mapped only when the backend supplied a real area
 * (entity-display copies entity.area into suggested_area). "Unknown" or
 * empty means the device still needs configuration.
 */
function hasRealArea(entity: EntityData): boolean {
  const area = entity.suggested_area?.trim()
  return Boolean(area) && area !== "Unknown"
}

/**
 * Device mapping statistics component
 */
function DeviceMappingStats({ entities }: { entities: EntityData[] }) {
  const stats = useMemo(() => {
    const byDeviceType = entities.reduce((acc, entity) => {
      acc[entity.device_type] = (acc[entity.device_type] || 0) + 1
      return acc
    }, {} as Record<string, number>)

    const bySourceType = entities.reduce((acc, entity) => {
      const sourceType = entity.source_type || entity.device_type || 'unknown'
      acc[sourceType] = (acc[sourceType] || 0) + 1
      return acc
    }, {} as Record<string, number>)

    const withRealArea = entities.filter(hasRealArea).length
    const unmapped = entities.length - withRealArea

    return {
      total: entities.length,
      byDeviceType,
      bySourceType,
      withRealArea,
      unmapped,
    }
  }, [entities])

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Total Devices</CardTitle>
          <IconDeviceDesktop className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{stats.total}</div>
          <p className="text-xs text-muted-foreground">
            Across {Object.keys(stats.byDeviceType).length} device types
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Mapped Areas</CardTitle>
          <IconMapPin className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{stats.withRealArea}</div>
          <p className="text-xs text-muted-foreground">
            {stats.total > 0 ? `${Math.round((stats.withRealArea / stats.total) * 100)}% mapped` : "No devices"}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Unmapped</CardTitle>
          <IconAlertCircle className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{stats.unmapped}</div>
          <p className="text-xs text-muted-foreground">
            Need area assignment
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Source Types</CardTitle>
          <IconDeviceGamepad className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{Object.keys(stats.bySourceType).length}</div>
          <p className="text-xs text-muted-foreground">
            Different source protocols
          </p>
        </CardContent>
      </Card>
    </div>
  )
}

/**
 * Device mapping table component
 */
function DeviceMappingTable({
  entities,
  coachConfig,
}: {
  entities: EntityData[]
  coachConfig?: ICoachConfig | undefined
}) {
  const getDeviceTypeIcon = (deviceType: string) => {
    switch (deviceType.toLowerCase()) {
      case 'light':
        return '💡'
      case 'lock':
        return '🔒'
      case 'temperature':
        return '🌡️'
      case 'tank':
        return '⛽'
      default:
        return '⚙️'
    }
  }

  const getStateVariant = (state: unknown) => {
    if (state === true || state === "on" || state === "unlocked") {
      return "default"
    }
    if (state === false || state === "off" || state === "locked") {
      return "secondary"
    }
    return "outline"
  }

  const formatState = (state: unknown) => {
    if (typeof state === 'boolean') {
      return state ? 'On' : 'Off'
    }
    if (typeof state === 'string') {
      return state.charAt(0).toUpperCase() + state.slice(1)
    }
    return String(state)
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <IconSettings className="h-5 w-5" />
          Device Mappings
        </CardTitle>
        <CardDescription>
          Current device instances and their area assignments
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Device</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Area</TableHead>
              <TableHead>Source</TableHead>
              <TableHead>State</TableHead>
              <TableHead>Last Updated</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {entities.map((entity) => (
              <TableRow key={entity.id || entity.entity_id}>
                <TableCell>
                  <div className="flex items-center gap-2">
                    <span className="text-lg">{getDeviceTypeIcon(entity.device_type)}</span>
                    <div>
                      <div className="font-medium">{entity.name}</div>
                      <div className="text-sm text-muted-foreground">{entity.id}</div>
                    </div>
                  </div>
                </TableCell>
                <TableCell>
                  <Badge variant="outline">{entity.device_type}</Badge>
                </TableCell>
                <TableCell>
                  {hasRealArea(entity) ? (
                    <Badge variant="secondary">
                      {zoneDisplayName(entity.suggested_area, coachConfig)}
                    </Badge>
                  ) : (
                    <Badge variant="destructive">Needs configuration</Badge>
                  )}
                </TableCell>
                <TableCell>
                  <Badge variant="outline">{entity.source_type}</Badge>
                </TableCell>
                <TableCell>
                  <Badge variant={getStateVariant(entity.state)}>
                    {formatState(entity.state)}
                  </Badge>
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {entity.last_updated ? new Date(entity.last_updated).toLocaleString() :
                   entity.timestamp ? new Date(entity.timestamp).toLocaleString() :
                   '—'}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}

/**
 * Device type breakdown component
 */
function DeviceTypeBreakdown({
  entities,
  coachConfig,
}: {
  entities: EntityData[]
  coachConfig?: ICoachConfig | undefined
}) {
  const deviceTypeGroups = useMemo(() => {
    const groups = entities.reduce((acc, entity) => {
      const deviceType = entity.device_type || 'unknown';
      if (!acc[deviceType]) {
        acc[deviceType] = []
      }
      acc[deviceType].push(entity)
      return acc
    }, {} as Record<string, EntityData[]>)

    return Object.entries(groups)
      .sort(([, a], [, b]) => b.length - a.length)
  }, [entities])

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <IconDeviceDesktop className="h-5 w-5" />
          Device Type Breakdown
        </CardTitle>
        <CardDescription>
          Distribution of devices by type
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {deviceTypeGroups.map(([deviceType, devices]) => (
            <div key={deviceType} className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Badge variant="outline">{deviceType}</Badge>
                <span className="text-sm text-muted-foreground">
                  {devices.length} device{devices.length !== 1 ? 's' : ''}
                </span>
              </div>
              <div className="flex gap-1">
                {devices.slice(0, 3).map((device) => (
                  <Badge
                    key={device.id || device.entity_id}
                    variant={hasRealArea(device) ? "secondary" : "outline"}
                    className="text-xs"
                  >
                    {hasRealArea(device)
                      ? zoneDisplayName(device.suggested_area, coachConfig)
                      : "Needs configuration"}
                  </Badge>
                ))}
                {devices.length > 3 && (
                  <Badge variant="outline" className="text-xs">
                    +{devices.length - 3}
                  </Badge>
                )}
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * Main Device Mapping page component
 */
export default function DeviceMapping() {
  const { data: entities, isLoading, error, refetch } = useEntities()
  const { data: coachConfig } = useCoachConfig()

  const entitiesArray = collectionToDisplayEntities(entities)

  if (isLoading) {
    return (
      <AppLayout>
        <div className="flex-1 space-y-6 p-4 pt-6">
          <div className="flex justify-between items-center">
            <div>
              <Skeleton className="h-8 w-48 mb-2" />
              <Skeleton className="h-4 w-96" />
            </div>
            <Skeleton className="h-10 w-24" />
          </div>

          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Card key={i}>
                <CardHeader className="pb-2">
                  <Skeleton className="h-4 w-24" />
                </CardHeader>
                <CardContent>
                  <Skeleton className="h-8 w-16 mb-1" />
                  <Skeleton className="h-3 w-32" />
                </CardContent>
              </Card>
            ))}
          </div>

          <Card>
            <CardHeader>
              <Skeleton className="h-6 w-32" />
              <Skeleton className="h-4 w-64" />
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className="h-12 w-full" />
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      </AppLayout>
    )
  }

  if (error) {
    return (
      <AppLayout>
        <div className="flex-1 space-y-6 p-4 pt-6">
          <Alert variant="destructive">
            <IconAlertCircle className="h-4 w-4" />
            <AlertTitle>Error Loading Device Mappings</AlertTitle>
            <AlertDescription>
              Failed to load device mapping data. Please try again.
            </AlertDescription>
          </Alert>
        </div>
      </AppLayout>
    )
  }

  return (
    <AppLayout>
      <div className="flex-1 space-y-6 p-4 pt-6">
        {/* Header (title comes from the app shell) */}
        <div className="flex justify-between items-center">
          <div>
            <p className="text-muted-foreground">
              Manage device instances and their area assignments
            </p>
          </div>
          <Button
            onClick={() => void refetch()}
            variant="outline"
            className="gap-2"
          >
            <IconRefresh className="h-4 w-4" />
            Refresh
          </Button>
        </div>

        {/* Statistics Cards */}
        <DeviceMappingStats entities={entitiesArray} />

        {/* Info Alert */}
        <Alert>
          <IconInfoCircle className="h-4 w-4" />
          <AlertTitle>Device Mapping Overview</AlertTitle>
          <AlertDescription>
            This page shows all discovered devices and their current area assignments.
            Devices without suggested areas may need manual configuration.
          </AlertDescription>
        </Alert>

        <div className="grid gap-8 lg:grid-cols-3">
          {/* Device Mapping Table - Takes 2/3 width */}
          <div className="lg:col-span-2">
            <DeviceMappingTable entities={entitiesArray} coachConfig={coachConfig} />
          </div>

          {/* Device Type Breakdown - Takes 1/3 width */}
          <div>
            <DeviceTypeBreakdown entities={entitiesArray} coachConfig={coachConfig} />
          </div>
        </div>
      </div>
    </AppLayout>
  )
}
