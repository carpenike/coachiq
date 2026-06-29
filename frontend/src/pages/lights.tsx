/**
 * Lights Management Page
 *
 * Provides entity-based light control using /api/entities endpoint.
 * Features group-based organization, individual controls, and real-time updates.
 */

import type { EntityData, LightEntity } from "@/api/types"
import { AppLayout } from "@/components/app-layout"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Slider } from "@/components/ui/slider"
import { useEntities } from "@/hooks/useEntities"
import { useOptimisticLightControl } from "@/hooks/useOptimisticMutations"
import { cn } from "@/lib/utils"
import { collectionToDisplayEntities } from "@/utils/entity-display"
import {
  IconBulb,
  IconBulbOff,
  IconBolt,
  IconMinus,
  IconPlus,
  IconPower,
  IconSun,
  IconMoon,
  IconTrendingUp
} from "@tabler/icons-react"
import { useMemo } from "react"

/**
 * Lighting statistics overview component
 */
function LightingStatistics({ lights }: { lights: EntityData[] }) {
  const stats = useMemo(() => {
    const total = lights.length
    const active = lights.filter(light => light.state === "on" || light.state === "true").length
    const averageBrightness = lights
      .filter(light => light.state === "on" || light.state === "true")
      .reduce((sum, light) => sum + ((light as LightEntity).brightness || 0), 0) / Math.max(active, 1)

    const energyEfficiency = active > 0 ? Math.round((averageBrightness / 100) * 85) : 0 // Mock calculation

    return { total, active, averageBrightness: Math.round(averageBrightness), energyEfficiency }
  }, [lights])

  return (
    <div className="*:data-[slot=card]:from-primary/5 *:data-[slot=card]:to-card dark:*:data-[slot=card]:bg-card grid grid-cols-2 md:grid-cols-4 gap-4 *:data-[slot=card]:bg-gradient-to-t *:data-[slot=card]:shadow-xs">
      <Card className="@container/card">
        <CardContent className="p-4 text-center">
          <div className="text-2xl font-semibold tabular-nums @[150px]/card:text-3xl">{stats.total}</div>
          <div className="text-xs text-muted-foreground">Total Lights</div>
        </CardContent>
      </Card>
      <Card className="@container/card">
        <CardContent className="p-4 text-center">
          <div className="text-2xl font-semibold tabular-nums @[150px]/card:text-3xl text-yellow-600">{stats.active}</div>
          <div className="text-xs text-muted-foreground flex items-center justify-center gap-1">
            <IconBolt className="h-3 w-3" />
            Currently On
          </div>
        </CardContent>
      </Card>
      <Card className="@container/card">
        <CardContent className="p-4 text-center">
          <div className="text-2xl font-semibold tabular-nums @[150px]/card:text-3xl">{stats.averageBrightness}%</div>
          <div className="text-xs text-muted-foreground">Avg Brightness</div>
        </CardContent>
      </Card>
      <Card className="@container/card">
        <CardContent className="p-4 text-center">
          <div className="text-2xl font-semibold tabular-nums @[150px]/card:text-3xl text-green-600">{stats.energyEfficiency}%</div>
          <div className="text-xs text-muted-foreground flex items-center justify-center gap-1">
            <IconTrendingUp className="h-3 w-3" />
            Efficiency
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

/**
 * Quick presets component
 */
function LightingPresets({ lights }: { lights: EntityData[] }) {
  const { toggle, setBrightness } = useOptimisticLightControl()

  const handleAllOff = () => {
    lights.forEach(light => {
      if (light.state === "on" || light.state === "true") {
        toggle.mutate({ entityId: light.entity_id })
      }
    })
  }

  const handleAllOn = () => {
    lights.forEach(light => {
      if (light.state === "off" || light.state === "false") {
        toggle.mutate({ entityId: light.entity_id })
      }
    })
  }

  const handleDimMode = () => {
    lights.forEach(light => {
      if (light.capabilities?.includes("brightness")) {
        setBrightness.mutate({ entityId: light.entity_id, brightness: 25 })
      }
    })
  }

  const handleBrightMode = () => {
    lights.forEach(light => {
      if (light.capabilities?.includes("brightness")) {
        setBrightness.mutate({ entityId: light.entity_id, brightness: 100 })
      }
    })
  }

  return (
    <Card className="@container/card from-primary/5 to-card bg-gradient-to-t shadow-xs">
      <CardHeader>
        <CardTitle className="@[250px]/card:text-lg flex items-center gap-2">
          <IconBolt className="size-5" />
          Quick Controls
        </CardTitle>
        <CardDescription>Control all lights at once</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Button
            variant="outline"
            onClick={handleAllOn}
            className="flex flex-col h-auto p-4 gap-2"
            disabled={toggle.isPending || setBrightness.isPending}
          >
            <IconSun className="h-5 w-5" />
            <span className="text-xs">All On</span>
          </Button>
          <Button
            variant="outline"
            onClick={handleAllOff}
            className="flex flex-col h-auto p-4 gap-2"
            disabled={toggle.isPending || setBrightness.isPending}
          >
            <IconMoon className="h-5 w-5" />
            <span className="text-xs">All Off</span>
          </Button>
          <Button
            variant="outline"
            onClick={handleDimMode}
            className="flex flex-col h-auto p-4 gap-2"
            disabled={toggle.isPending || setBrightness.isPending}
          >
            <IconBulb className="h-5 w-5 opacity-50" />
            <span className="text-xs">Dim Mode</span>
          </Button>
          <Button
            variant="outline"
            onClick={handleBrightMode}
            className="flex flex-col h-auto p-4 gap-2"
            disabled={toggle.isPending || setBrightness.isPending}
          >
            <IconBolt className="h-5 w-5" />
            <span className="text-xs">Bright Mode</span>
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * Individual light control component
 */
interface LightControlProps {
  light: EntityData
}

function LightControl({ light }: LightControlProps) {
  const { toggle, setBrightness, brightnessUp, brightnessDown } = useOptimisticLightControl()

  const isOn = light.state === "on" || light.state === "true"
  const lightEntity = light as LightEntity
  const brightness = lightEntity.brightness || 0
  const hasBrightnessControl = light.capabilities?.includes("brightness")
  const isOnline = light.timestamp && (Date.now() - light.timestamp) < 300000

  const handleSliderChange = (value: number[]) => {
    const newBrightness = value[0];
    if (newBrightness !== undefined) {
      setBrightness.mutate({ entityId: light.entity_id, brightness: newBrightness });
    }
  }

  const handlePresetBrightness = (level: number) => {
    setBrightness.mutate({ entityId: light.entity_id, brightness: level })
  }

  return (
    <Card className={cn(
      "@container/card from-primary/5 to-card bg-gradient-to-t shadow-xs transition-all duration-200 hover:shadow-md",
      isOn && "ring-2 ring-yellow-500/20 bg-yellow-50/10 dark:bg-yellow-950/10"
    )}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className={cn(
              "p-1.5 rounded-lg transition-colors",
              isOn ? "bg-yellow-100 dark:bg-yellow-900/50" : "bg-muted"
            )}>
              {isOn ? (
                <IconBulb className="size-4 text-yellow-600 dark:text-yellow-400" />
              ) : (
                <IconBulbOff className="size-4 text-muted-foreground" />
              )}
            </div>
            <CardTitle className="@[200px]/card:text-base text-sm">
              {light.friendly_name}
            </CardTitle>
          </div>
          <CardAction>
            <Badge variant={isOn ? "default" : "secondary"} className={cn(
              "text-xs",
              isOn && "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200"
            )}>
              {isOn ? "ON" : "OFF"}
            </Badge>
          </CardAction>
        </div>
        {!isOnline && (
          <CardDescription>
            <Badge variant="destructive" className="text-xs">
              Offline
            </Badge>
          </CardDescription>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Main Controls */}
        <div className="flex gap-2">
          <Button
            onClick={() => void toggle.mutate({ entityId: light.entity_id })}
            disabled={toggle.isPending || setBrightness.isPending}
            className="flex-1"
            variant={isOn ? "default" : "outline"}
          >
            <IconPower className="mr-2 h-4 w-4" />
            {isOn ? "Turn Off" : "Turn On"}
          </Button>
        </div>

        {/* Enhanced Brightness Control */}
        {hasBrightnessControl && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">Brightness</span>
              <Badge variant="outline" className="text-xs">
                {brightness}%
              </Badge>
            </div>

            {/* Slider Control with +/- buttons */}
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => void brightnessDown.mutate({ entityId: light.entity_id })}
                disabled={toggle.isPending || setBrightness.isPending || brightnessUp.isPending || brightnessDown.isPending || brightness <= 0}
                className="shrink-0"
              >
                <IconMinus className="h-3 w-3" />
              </Button>
              <div className="flex-1 px-1">
                <Slider
                  value={[brightness]}
                  onValueChange={handleSliderChange}
                  max={100}
                  step={1}
                  className="w-full"
                  disabled={toggle.isPending || setBrightness.isPending || brightnessUp.isPending || brightnessDown.isPending}
                />
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={() => void brightnessUp.mutate({ entityId: light.entity_id })}
                disabled={toggle.isPending || setBrightness.isPending || brightnessUp.isPending || brightnessDown.isPending || brightness >= 100}
                className="shrink-0"
              >
                <IconPlus className="h-3 w-3" />
              </Button>
            </div>

            {/* Quick Preset Buttons */}
            <div className="flex gap-1">
              <Button
                size="sm"
                variant="outline"
                onClick={() => handlePresetBrightness(25)}
                disabled={toggle.isPending || setBrightness.isPending || brightnessUp.isPending || brightnessDown.isPending}
                className="flex-1 text-xs"
              >
                25%
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => handlePresetBrightness(50)}
                disabled={toggle.isPending || setBrightness.isPending || brightnessUp.isPending || brightnessDown.isPending}
                className="flex-1 text-xs"
              >
                50%
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => handlePresetBrightness(75)}
                disabled={toggle.isPending || setBrightness.isPending || brightnessUp.isPending || brightnessDown.isPending}
                className="flex-1 text-xs"
              >
                75%
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => handlePresetBrightness(100)}
                disabled={toggle.isPending || setBrightness.isPending || brightnessUp.isPending || brightnessDown.isPending}
                className="flex-1 text-xs"
              >
                100%
              </Button>
            </div>
          </div>
        )}

        {/* Status Footer */}
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <div className="flex items-center gap-1">
            <div className={cn(
              "w-2 h-2 rounded-full",
              isOnline ? "bg-green-500" : "bg-red-500"
            )} />
            {isOnline ? "Online" : "Offline"}
          </div>
          {light.timestamp && (
            <span>
              {new Date(light.timestamp).toLocaleTimeString()}
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * Loading skeleton for light controls
 */
function LightControlSkeleton() {
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Skeleton className="size-5" />
            <Skeleton className="h-5 w-24" />
          </div>
          <Skeleton className="h-5 w-12" />
        </div>
        <Skeleton className="h-4 w-16" />
      </CardHeader>
      <CardContent className="space-y-3">
        <Skeleton className="h-10 w-full" />
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Skeleton className="h-4 w-16" />
            <Skeleton className="h-4 w-8" />
          </div>
          <div className="flex items-center gap-2">
            <Skeleton className="h-8 w-8" />
            <Skeleton className="h-2 flex-1" />
            <Skeleton className="h-8 w-8" />
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * Enhanced group-based light organization
 */
interface LightGroupProps {
  title: string
  lights: EntityData[]
}

function LightGroup({ title, lights }: LightGroupProps) {
  const { toggle, setBrightness } = useOptimisticLightControl()

  if (lights.length === 0) return null

  const onLights = lights.filter(light => light.state === "on" || light.state === "true")
  const groupEfficiency = lights.length > 0 ? Math.round((onLights.length / lights.length) * 100) : 0

  const handleGroupToggle = () => {
    if (onLights.length > lights.length / 2) {
      // Most lights are on, turn all off
      lights.forEach(light => {
        if (light.state === "on" || light.state === "true") {
          toggle.mutate({ entityId: light.entity_id })
        }
      })
    } else {
      // Most lights are off, turn all on
      lights.forEach(light => {
        if (light.state === "off" || light.state === "false") {
          toggle.mutate({ entityId: light.entity_id })
        }
      })
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h3 className="text-lg font-semibold">{title}</h3>
          <Badge variant="outline" className="text-xs">
            {lights.length} lights
          </Badge>
          {onLights.length > 0 && (
            <Badge variant="default" className="text-xs">
              <IconBolt className="mr-1 h-3 w-3" />
              {onLights.length} active
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Badge
            variant={groupEfficiency > 50 ? "default" : "secondary"}
            className="text-xs"
          >
            {groupEfficiency}% on
          </Badge>
          <Button
            size="sm"
            variant="outline"
            onClick={handleGroupToggle}
            disabled={toggle.isPending || setBrightness.isPending}
            className="text-xs"
          >
            <IconPower className="mr-1 h-3 w-3" />
            {onLights.length > lights.length / 2 ? "All Off" : "All On"}
          </Button>
        </div>
      </div>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {lights.map((light) => (
          <LightControl key={light.entity_id} light={light} />
        ))}
      </div>
    </div>
  )
}

/**
 * Lights Management Page Component
 */
export default function Lights() {
  const { data: lights, isLoading, error } = useEntities({ device_type: "light" })

  if (isLoading) {
    return (
      <AppLayout pageTitle="Lights">
        <div className="flex-1 space-y-6 p-4 pt-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold tracking-tight">Lights</h1>
              <p className="text-muted-foreground">
                Control and monitor all lighting systems
              </p>
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }).map((_, index) => (
              <LightControlSkeleton key={index} />
            ))}
          </div>
        </div>
      </AppLayout>
    )
  }

  if (error) {
    return (
      <AppLayout pageTitle="Lights">
        <div className="flex-1 space-y-6 p-4 pt-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold tracking-tight">Lights</h1>
              <p className="text-muted-foreground">
                Control and monitor all lighting systems
              </p>
            </div>
          </div>
          <Card>
            <CardHeader>
              <CardTitle className="text-destructive">Error Loading Lights</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Unable to load light information. Please check your connection and try again.
              </p>
            </CardContent>
          </Card>
        </div>
      </AppLayout>
    )
  }

  const lightArray = collectionToDisplayEntities(lights)

  if (lightArray.length === 0) {
    return (
      <AppLayout pageTitle="Lights">
        <div className="flex-1 space-y-6 p-4 pt-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold tracking-tight">Lights</h1>
              <p className="text-muted-foreground">
                Control and monitor all lighting systems
              </p>
            </div>
          </div>
          <Card>
            <CardHeader>
              <CardTitle>No Lights Found</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                No light entities are currently detected. Check your RV-C network connection
                and ensure light devices are properly configured.
              </p>
            </CardContent>
          </Card>
        </div>
      </AppLayout>
    )
  }

  // Group lights by area
  const groupedLights = lightArray.reduce((groups, light) => {
    const area = light.suggested_area || "Other"
    if (!groups[area]) {
      groups[area] = []
    }
    groups[area].push(light)
    return groups
  }, {} as Record<string, EntityData[]>)

  const sortedGroups = Object.entries(groupedLights).sort(([a], [b]) => {
    // Put "Other" group last
    if (a === "Other") return 1
    if (b === "Other") return -1
    return a.localeCompare(b)
  })

  return (
    <AppLayout pageTitle="Lights">
      <div className="flex-1 space-y-6 p-4 pt-6">
        {/* Page Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Lights</h1>
            <p className="text-muted-foreground">
              Control and monitor all lighting systems
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="outline">
              {lightArray.length} devices
            </Badge>
            <Badge variant="outline">
              {lightArray.filter(light => light.state === "on" || light.state === "true").length} active
            </Badge>
          </div>
        </div>

        {/* Statistics Overview */}
        <LightingStatistics lights={lightArray} />

        {/* Quick Controls */}
        <LightingPresets lights={lightArray} />

        {/* Light Groups */}
        <div className="space-y-8">
          {sortedGroups.map(([groupName, groupLights]) => (
            <LightGroup
              key={groupName}
              title={groupName}
              lights={groupLights}
            />
          ))}
        </div>
      </div>
    </AppLayout>
  )
}
