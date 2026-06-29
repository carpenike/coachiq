/**
 * Network Map Page
 *
 * Canvas-based visualization of the RV-C network topology.
 * Shows real-time device connections and status.
 */

import {
    discoverDevices,
    fetchDeviceAvailability,
    fetchDeviceDiscoveryStatus,
    fetchNetworkTopology,
    fetchProtocolBridgeStatus,
    fetchProtocolThroughput,
} from "@/api/endpoints"
import { fetchEntitiesV2 } from "@/api/domains/entities"
import type { DeviceAvailability, EntityData, ProtocolBridgeStatus, SpartanK2Entity } from "@/api/types"
import { AppLayout } from "@/components/app-layout"
import { DeviceDiscoveryTable } from "@/components/network/DeviceDiscoveryTable"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useEntities } from "@/hooks/useEntities"
import { collectionToDisplayEntities } from "@/utils/entity-display"
import {
    IconActivity,
    IconAlertTriangle,
    IconGitBranch,
    IconInfoCircle,
    IconNetwork,
    IconRefresh
} from "@tabler/icons-react"
import { useQuery } from "@tanstack/react-query"
import { useMemo } from "react"


/**
 * Network statistics sidebar component
 */
function NetworkStatsSidebar({
  entities,
  availability
}: {
  entities: EntityData[]
  availability?: DeviceAvailability
}) {
  const stats = useMemo(() => {
    // Use device discovery data if available, fall back to entities
    if (availability) {
      return {
        total: availability.total_devices,
        online: availability.online_devices,
        offline: availability.offline_devices,
        recent: availability.recent_devices,
        errors: 0, // Not tracked in availability yet
        deviceTypes: availability.device_types,
        protocols: availability.protocols,
      }
    }

    // Legacy entity-based stats
    const deviceTypes = entities.reduce((acc, entity) => {
      acc[entity.device_type] = (acc[entity.device_type] || 0) + 1
      return acc
    }, {} as Record<string, number>)

    const statusCounts = entities.reduce((acc, entity) => {
      const status = entity.state === "on" || entity.state === "online" ? "online" :
                   entity.state === "error" ? "error" : "offline"
      acc[status] = (acc[status] || 0) + 1
      return acc
    }, {} as Record<string, number>)

    const sourceCounts = entities.reduce((acc, entity) => {
      const sourceType = entity.source_type || entity.device_type || 'unknown'
      acc[sourceType] = (acc[sourceType] || 0) + 1
      return acc
    }, {} as Record<string, number>)

    return {
      total: entities.length,
      deviceTypes,
      statusCounts,
      sourceCounts,
      online: statusCounts.online || 0,
      offline: statusCounts.offline || 0,
      errors: statusCounts.error || 0,
    }
  }, [entities, availability])

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Network Overview</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="text-center">
              <div className="text-2xl font-bold text-emerald-600">{stats.online}</div>
              <div className="text-xs text-muted-foreground">Online</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-gray-500">{stats.offline}</div>
              <div className="text-xs text-muted-foreground">Offline</div>
            </div>
          </div>

          {stats.errors > 0 && (
            <div className="text-center">
              <div className="text-2xl font-bold text-red-600">{stats.errors}</div>
              <div className="text-xs text-muted-foreground">Errors</div>
            </div>
          )}

          {availability && (stats.recent || 0) > 0 && (
            <div className="text-center">
              <div className="text-2xl font-bold text-blue-600">{stats.recent}</div>
              <div className="text-xs text-muted-foreground">Recent Activity</div>
            </div>
          )}

          <div className="text-center pt-2 border-t">
            <div className="text-xl font-bold">{stats.total}</div>
            <div className="text-xs text-muted-foreground">Total Devices</div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Device Types</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {Object.entries(stats.deviceTypes || {}).map(([type, count]) => (
              <div key={type} className="flex justify-between items-center">
                <span className="text-sm capitalize">{type.replace('_', ' ')}</span>
                <Badge variant="outline">{count}</Badge>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">
            {availability ? "Protocols" : "Source Protocols"}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {availability ? (
              Object.entries(stats.protocols || {}).map(([protocol, count]) => (
                <div key={protocol} className="flex justify-between items-center">
                  <span className="text-sm capitalize">{protocol}</span>
                  <Badge variant="secondary">{count}</Badge>
                </div>
              ))
            ) : (
              Object.entries(stats.sourceCounts || {}).map(([source, count]) => (
                <div key={source} className="flex justify-between items-center">
                  <span className="text-sm">{source}</span>
                  <Badge variant="secondary">{count}</Badge>
                </div>
              ))
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Network Health</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            <div className="flex justify-between text-sm">
              <span>Connectivity</span>
              <Badge variant="default">
                {stats.total > 0 ? Math.round((stats.online / stats.total) * 100) : 0}%
              </Badge>
            </div>
            <div className="flex justify-between text-sm">
              <span>Error Rate</span>
              <Badge variant={stats.errors > 0 ? "destructive" : "outline"}>
                {stats.total > 0 ? Math.round((stats.errors / stats.total) * 100) : 0}%
              </Badge>
            </div>
            <div className="flex justify-between text-sm">
              <span>Last Update</span>
              <Badge variant="outline">
                {new Date().toLocaleTimeString()}
              </Badge>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

/**
 * Protocol Bridge Status Component
 */
function ProtocolBridgeStatus() {
  const { data: bridgeStatus, isLoading } = useQuery({
    queryKey: ['protocol-bridge-status'],
    queryFn: fetchProtocolBridgeStatus,
    refetchInterval: 30000,
    staleTime: 15000,
  })

  const { data: throughput = {} } = useQuery({
    queryKey: ['protocol-throughput'],
    queryFn: fetchProtocolThroughput,
    refetchInterval: 15000,
    staleTime: 10000,
  })

  if (isLoading || !bridgeStatus) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Protocol Bridges</CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-32 w-full" />
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm flex items-center gap-2">
          <IconGitBranch className="h-4 w-4" />
          Protocol Bridges
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div className="text-center">
            <div className="text-lg font-bold text-blue-600">{bridgeStatus.bridges_active || 0}</div>
            <div className="text-xs text-muted-foreground">Active</div>
          </div>
          <div className="text-center">
            <div className="text-lg font-bold">{bridgeStatus.total_bridges || 0}</div>
            <div className="text-xs text-muted-foreground">Total</div>
          </div>
        </div>

        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span>Health Score</span>
            <span className="font-medium">{((bridgeStatus.health_score || 0) * 100).toFixed(1)}%</span>
          </div>
          <Progress value={(bridgeStatus.health_score || 0) * 100} className="h-2" />
        </div>

        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span>Translation Rate</span>
            <span className="font-medium">{(bridgeStatus.translation_rate || 0).toFixed(1)}/sec</span>
          </div>
          <div className="flex justify-between text-sm">
            <span>Error Rate</span>
            <Badge variant={(bridgeStatus.error_rate || 0) > 0.05 ? 'destructive' : 'outline'}>
              {((bridgeStatus.error_rate || 0) * 100).toFixed(2)}%
            </Badge>
          </div>
        </div>

        {Object.entries(bridgeStatus.bridge_statuses || {}).length > 0 && (
          <div className="space-y-2">
            <h6 className="text-xs font-semibold text-muted-foreground">Bridge Status</h6>
            {Object.entries(bridgeStatus.bridge_statuses || {}).map(([bridgeId, bridge]) => (
              <div key={bridgeId} className="flex items-center justify-between p-2 border rounded text-xs">
                <div>
                  <div className="font-medium">
                    {(bridge.from_protocol || 'Unknown').toUpperCase()} → {(bridge.to_protocol || 'Unknown').toUpperCase()}
                  </div>
                  <div className="text-muted-foreground">
                    {bridge.translation_count || 0} translations
                  </div>
                </div>
                <Badge variant={bridge.active ? 'default' : 'secondary'}>
                  {bridge.active ? 'Active' : 'Inactive'}
                </Badge>
              </div>
            ))}
          </div>
        )}

        <div className="space-y-2">
          <h6 className="text-xs font-semibold text-muted-foreground">Protocol Throughput</h6>
          {Object.entries(throughput || {}).map(([protocol, rate]) => (
            <div key={protocol} className="flex justify-between text-xs">
              <span className="capitalize">{protocol}</span>
              <span className="font-medium">{(rate || 0).toFixed(1)} msg/sec</span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * Multi-Protocol Entity Statistics Component
 */
function MultiProtocolStats({ entities }: { entities: EntityData[] }) {
  const stats = useMemo(() => {
    const protocolCounts = entities.reduce((acc, entity) => {
      const protocol = (entity as EntityData & { protocol?: string }).protocol || 'rvc'
      acc[protocol] = (acc[protocol] || 0) + 1
      return acc
    }, {} as Record<string, number>)

    const deviceTypes = entities.reduce((acc, entity) => {
      acc[entity.device_type] = (acc[entity.device_type] || 0) + 1
      return acc
    }, {} as Record<string, number>)

    const statusCounts = entities.reduce((acc, entity) => {
      const status = entity.state === "on" || entity.state === "online" ? "online" :
                   entity.state === "error" ? "error" : "offline"
      acc[status] = (acc[status] || 0) + 1
      return acc
    }, {} as Record<string, number>)

    const safetyIssues = entities.filter(entity =>
      (entity as SpartanK2Entity)?.safety_status === 'critical' ||
      (entity as SpartanK2Entity)?.safety_status === 'warning'
    ).length

    return {
      total: entities.length,
      protocolCounts,
      deviceTypes,
      statusCounts,
      safetyIssues,
      online: statusCounts.online || 0,
      offline: statusCounts.offline || 0,
      errors: statusCounts.error || 0,
    }
  }, [entities])

  const protocolColors = {
    rvc: "bg-blue-600",
    j1939: "bg-emerald-600",
    firefly: "bg-violet-600",
    spartan_k2: "bg-red-600",
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-sm flex items-center gap-2">
            <IconNetwork className="h-4 w-4" />
            Multi-Protocol Network
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="text-center">
              <div className="text-2xl font-bold text-emerald-600">{stats.online}</div>
              <div className="text-xs text-muted-foreground">Online</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-gray-500">{stats.offline}</div>
              <div className="text-xs text-muted-foreground">Offline</div>
            </div>
          </div>

          {stats.errors > 0 && (
            <div className="text-center">
              <div className="text-2xl font-bold text-red-600">{stats.errors}</div>
              <div className="text-xs text-muted-foreground">Errors</div>
            </div>
          )}

          {stats.safetyIssues > 0 && (
            <Alert className="border-red-200 bg-red-50">
              <IconAlertTriangle className="h-4 w-4" />
              <AlertDescription className="text-sm">
                {stats.safetyIssues} safety issue{stats.safetyIssues > 1 ? 's' : ''} detected
              </AlertDescription>
            </Alert>
          )}

          <div className="text-center pt-2 border-t">
            <div className="text-xl font-bold">{stats.total}</div>
            <div className="text-xs text-muted-foreground">Total Devices</div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Protocol Distribution</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {Object.entries(stats.protocolCounts || {}).map(([protocol, count]) => (
              <div key={protocol} className="flex justify-between items-center">
                <div className="flex items-center gap-2">
                  <div className={`w-3 h-3 rounded-full ${protocolColors[protocol as keyof typeof protocolColors] || 'bg-gray-500'}`} />
                  <span className="text-sm capitalize">{protocol}</span>
                </div>
                <Badge variant="outline">{count}</Badge>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Device Types</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {Object.entries(stats.deviceTypes || {}).map(([type, count]) => (
              <div key={type} className="flex justify-between items-center">
                <span className="text-sm capitalize">{type.replace('_', ' ')}</span>
                <Badge variant="outline">{count}</Badge>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

/**
 * Main Network Map page component
 */
export default function NetworkMap() {
  const { data: entities, isLoading, error, refetch } = useEntities()

  // Device discovery queries
  const { data: networkTopology, refetch: refetchTopology } = useQuery({
    queryKey: ['network-topology'],
    queryFn: fetchNetworkTopology,
    refetchInterval: 30000,
    staleTime: 15000,
  })

  const { data: deviceAvailability } = useQuery({
    queryKey: ['device-availability'],
    queryFn: fetchDeviceAvailability,
    refetchInterval: 15000,
    staleTime: 10000,
  })

  const { data: discoveryStatus } = useQuery({
    queryKey: ['discovery-status'],
    queryFn: fetchDeviceDiscoveryStatus,
    refetchInterval: 60000,
    staleTime: 30000,
  })

  // Multi-protocol entity queries
  const { data: j1939Entities } = useQuery({
    queryKey: ['j1939-entities'],
    queryFn: () => fetchEntitiesV2({ protocol: 'j1939' }),
    refetchInterval: 30000,
    staleTime: 15000,
  })

  const { data: fireflyEntities } = useQuery({
    queryKey: ['firefly-entities'],
    queryFn: () => fetchEntitiesV2({ protocol: 'firefly' }),
    refetchInterval: 30000,
    staleTime: 15000,
  })

  const { data: spartanK2Entities } = useQuery({
    queryKey: ['spartan-k2-entities'],
    queryFn: () => fetchEntitiesV2({ protocol: 'spartan_k2' }),
    refetchInterval: 30000,
    staleTime: 15000,
  })

  const { data: bridgeStatus } = useQuery({
    queryKey: ['protocol-bridge-status'],
    queryFn: fetchProtocolBridgeStatus,
    refetchInterval: 30000,
    staleTime: 15000,
  })

  const { data: throughput } = useQuery({
    queryKey: ['protocol-throughput'],
    queryFn: fetchProtocolThroughput,
    refetchInterval: 15000,
    staleTime: 10000,
  })

  // Combine all entities
  const allEntities = useMemo(() => {
    const rvcEntities = collectionToDisplayEntities(entities).map(entity => ({ ...entity, protocol: 'rvc' }))
    const j1939Array = collectionToDisplayEntities(j1939Entities)
    const fireflyArray = collectionToDisplayEntities(fireflyEntities)
    const spartanK2Array = collectionToDisplayEntities(spartanK2Entities)

    return [
      ...rvcEntities,
      ...j1939Array,
      ...fireflyArray,
      ...spartanK2Array,
    ] as EntityData[]
  }, [entities, j1939Entities, fireflyEntities, spartanK2Entities])

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

          <div className="grid gap-8 lg:grid-cols-4">
            <div className="lg:col-span-3">
              <Card>
                <CardHeader>
                  <Skeleton className="h-6 w-48" />
                </CardHeader>
                <CardContent>
                  <Skeleton className="h-96 w-full" />
                </CardContent>
              </Card>
            </div>
            <div>
              <Skeleton className="h-96 w-full" />
            </div>
          </div>
        </div>
      </AppLayout>
    )
  }

  if (error) {
    return (
      <AppLayout>
        <div className="flex-1 space-y-6 p-4 pt-6">
          <Alert variant="destructive">
            <IconAlertTriangle className="h-4 w-4" />
            <AlertTitle>Error Loading Network Map</AlertTitle>
            <AlertDescription>
              Failed to load network topology data. Please try again.
            </AlertDescription>
          </Alert>
        </div>
      </AppLayout>
    )
  }

  return (
    <AppLayout>
      <div className="flex-1 space-y-6 p-4 pt-6">
        {/* Header */}
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Network Map</h1>
            <p className="text-muted-foreground">
              Device discovery and monitoring for CAN bus networks
            </p>
            {discoveryStatus && (
              <div className="flex items-center gap-2 mt-2">
                <Badge variant={discoveryStatus.health.status === "healthy" ? "default" :
                               discoveryStatus.health.status === "warning" ? "secondary" : "destructive"}>
                  {discoveryStatus.service_status}
                </Badge>
                {networkTopology && (
                  <span className="text-sm text-muted-foreground">
                    {networkTopology.total_devices} devices discovered
                  </span>
                )}
              </div>
            )}
          </div>
          <div className="flex gap-2">
            <Button
              onClick={() => void (async () => {
                await discoverDevices("rvc");
                void refetchTopology();
              })()}
              variant="outline"
              className="gap-2"
            >
              <IconNetwork className="h-4 w-4" />
              Discover Devices
            </Button>
            <Button
              onClick={() => {
                void refetch();
                void refetchTopology();
              }}
              variant="outline"
              className="gap-2"
            >
              <IconRefresh className="h-4 w-4" />
              Refresh
            </Button>
          </div>
        </div>

        {/* Info Alert */}
        <Alert>
          <IconInfoCircle className="h-4 w-4" />
          <AlertTitle>Device Discovery & Monitoring</AlertTitle>
          <AlertDescription>
            Monitor discovered CAN bus devices with real-time status updates.
            Use polling actions to query individual devices and export device inventories.
          </AlertDescription>
        </Alert>

        <Tabs defaultValue="topology" className="space-y-4">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="topology">Device Discovery</TabsTrigger>
            <TabsTrigger value="protocols">Multi-Protocol View</TabsTrigger>
            <TabsTrigger value="performance">Performance View</TabsTrigger>
          </TabsList>

          <TabsContent value="topology" className="space-y-4">
            <div className="grid gap-8 lg:grid-cols-4">
              {/* Device Discovery Table - Takes 3/4 width */}
              <div className="lg:col-span-3">
                {networkTopology && deviceAvailability ? (
                  <DeviceDiscoveryTable
                    topology={networkTopology}
                    availability={deviceAvailability}
                    isLoading={isLoading}
                    onRefresh={() => {
                      void refetch();
                      void refetchTopology();
                    }}
                  />
                ) : (
                  <DeviceDiscoveryTable
                    isLoading={isLoading}
                    onRefresh={() => {
                      void refetch();
                      void refetchTopology();
                    }}
                  />
                )}
              </div>

              {/* Network Stats Sidebar - Takes 1/4 width */}
              <div>
                {deviceAvailability ? (
                  <NetworkStatsSidebar entities={entitiesArray} availability={deviceAvailability} />
                ) : (
                  <NetworkStatsSidebar entities={entitiesArray} />
                )}
              </div>
            </div>
          </TabsContent>

          <TabsContent value="protocols" className="space-y-4">
            <div className="grid gap-6 lg:grid-cols-4">
              <div className="lg:col-span-3 space-y-6">
                <div className="grid gap-6 md:grid-cols-2">
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-lg flex items-center gap-2">
                        <IconNetwork className="h-5 w-5" />
                        Protocol Overview
                      </CardTitle>
                      <CardDescription>
                        Cross-protocol communication and bridge status
                      </CardDescription>
                    </CardHeader>
                    <CardContent>
                      {bridgeStatus ? (
                        <div className="space-y-4">
                          <div className="grid grid-cols-2 gap-4">
                            <div className="text-center">
                              <div className="text-2xl font-bold text-blue-600">
                                {bridgeStatus.bridges_active || 0}
                              </div>
                              <div className="text-sm text-muted-foreground">Active Bridges</div>
                            </div>
                            <div className="text-center">
                              <div className="text-2xl font-bold">
                                {((bridgeStatus.health_score || 0) * 100).toFixed(0)}%
                              </div>
                              <div className="text-sm text-muted-foreground">Bridge Health</div>
                            </div>
                          </div>
                          <Progress value={(bridgeStatus.health_score || 0) * 100} className="h-3" />
                          <div className="text-center text-sm text-muted-foreground">
                            {(bridgeStatus.translation_rate || 0).toFixed(1)} translations/sec
                          </div>
                        </div>
                      ) : (
                        <div className="text-center py-8">
                          <IconGitBranch className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
                          <p className="text-muted-foreground">No protocol bridges active</p>
                        </div>
                      )}
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader>
                      <CardTitle className="text-lg flex items-center gap-2">
                        <IconActivity className="h-5 w-5" />
                        Protocol Throughput
                      </CardTitle>
                      <CardDescription>
                        Real-time message rates by protocol
                      </CardDescription>
                    </CardHeader>
                    <CardContent>
                      {throughput && Object.keys(throughput).length > 0 ? (
                        <div className="space-y-3">
                          {Object.entries(throughput || {}).map(([protocol, rate]) => (
                            <div key={protocol}>
                              <div className="flex justify-between text-sm mb-1">
                                <span className="capitalize">{protocol}</span>
                                <span className="font-medium">{(rate || 0).toFixed(1)} msg/sec</span>
                              </div>
                              <Progress value={Math.min(((rate || 0) / 100) * 100, 100)} className="h-2" />
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="text-center py-8">
                          <IconActivity className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
                          <p className="text-muted-foreground">No throughput data available</p>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                </div>

                <Card>
                  <CardHeader>
                    <CardTitle>Protocol Entity Distribution</CardTitle>
                    <CardDescription>
                      Entity breakdown across all supported protocols
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                      <div className="text-center p-4 border rounded-lg">
                        <div className="w-4 h-4 bg-blue-600 rounded-full mx-auto mb-2" />
                        <div className="text-lg font-bold">
                          {allEntities.filter(e => (e as EntityData & { protocol?: string }).protocol === 'rvc').length}
                        </div>
                        <div className="text-sm text-muted-foreground">RV-C</div>
                      </div>
                      <div className="text-center p-4 border rounded-lg">
                        <div className="w-4 h-4 bg-emerald-600 rounded-full mx-auto mb-2" />
                        <div className="text-lg font-bold">
                          {allEntities.filter(e => (e as EntityData & { protocol?: string }).protocol === 'j1939').length}
                        </div>
                        <div className="text-sm text-muted-foreground">J1939</div>
                      </div>
                      <div className="text-center p-4 border rounded-lg">
                        <div className="w-4 h-4 bg-violet-600 rounded-full mx-auto mb-2" />
                        <div className="text-lg font-bold">
                          {allEntities.filter(e => (e as EntityData & { protocol?: string }).protocol === 'firefly').length}
                        </div>
                        <div className="text-sm text-muted-foreground">Firefly</div>
                      </div>
                      <div className="text-center p-4 border rounded-lg">
                        <div className="w-4 h-4 bg-red-600 rounded-full mx-auto mb-2" />
                        <div className="text-lg font-bold">
                          {allEntities.filter(e => (e as EntityData & { protocol?: string }).protocol === 'spartan_k2').length}
                        </div>
                        <div className="text-sm text-muted-foreground">Spartan K2</div>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </div>

              <div className="space-y-4">
                <ProtocolBridgeStatus />
                <MultiProtocolStats entities={allEntities} />
              </div>
            </div>
          </TabsContent>

          <TabsContent value="performance" className="space-y-4">
            <div className="grid gap-6 lg:grid-cols-3">
              <div className="lg:col-span-2 space-y-6">
                <Card>
                  <CardHeader>
                    <CardTitle className="text-lg">Network Performance Overview</CardTitle>
                    <CardDescription>
                      Real-time performance metrics and health indicators
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="grid gap-4 md:grid-cols-3">
                      <div className="text-center">
                        <div className="text-2xl font-bold text-green-600">
                          {Math.round((allEntities.filter(e => {
                            const entity = e;
                            return entity.state === 'on' || entity.state === 'online';
                          }).length / Math.max(allEntities.length, 1)) * 100)}%
                        </div>
                        <div className="text-sm text-muted-foreground">Connectivity</div>
                      </div>
                      <div className="text-center">
                        <div className="text-2xl font-bold text-blue-600">
                          {Object.values(throughput || {}).reduce((a, b) => a + b, 0).toFixed(1)}
                        </div>
                        <div className="text-sm text-muted-foreground">Total msg/sec</div>
                      </div>
                      <div className="text-center">
                        <div className="text-2xl font-bold text-purple-600">
                          {bridgeStatus ? ((bridgeStatus.health_score || 0) * 100).toFixed(0) : 0}%
                        </div>
                        <div className="text-sm text-muted-foreground">Bridge Health</div>
                      </div>
                    </div>
                  </CardContent>
                </Card>

                <Alert>
                  <IconInfoCircle className="h-4 w-4" />
                  <AlertTitle>Performance Monitoring</AlertTitle>
                  <AlertDescription>
                    For detailed performance analytics, visit the dedicated{' '}
                    <a href="/performance" className="font-medium underline">Performance Analytics</a> page.
                  </AlertDescription>
                </Alert>
              </div>

              <div>
                <MultiProtocolStats entities={allEntities} />
              </div>
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </AppLayout>
  )
}
