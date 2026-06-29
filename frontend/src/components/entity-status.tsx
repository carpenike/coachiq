/**
 * Entity Status Component
 *
 * Demonstrates the enhanced state management system with Domain API v1 progressive enhancement.
 * This component serves as an example of how to use the enhanced React Query hooks that
 * automatically use Domain API v1 when available and fall back to legacy API.
 */

import type { ReactNode } from "react";
import type { LightEntity } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useEntities, useHealthStatus, useLightControl, useLights, useBulkEntityControl } from "@/hooks";
import { useEntitiesDomainAPIAvailability } from "@/hooks/domains/useEntitiesV2";

/**
 * Simple loading skeleton for entity cards
 */
function EntityCardSkeleton() {
  return (
    <Card>
      <CardHeader>
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-3 w-32" />
      </CardHeader>
      <CardContent>
        <div className="flex flex-col gap-2">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * Light Control Component
 * Demonstrates entity control with optimistic updates
 */
function LightControlCard() {
  const { data: lightsData, isLoading, error } = useLights();
  const lightControl = useLightControl();

  // Convert EntityCollection to array
  const lights = lightsData ? Object.values(lightsData) as LightEntity[] : [];

  if (isLoading) {
    return <EntityCardSkeleton />;
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Lighting System</CardTitle>
          <CardDescription>Control RV interior and exterior lights</CardDescription>
        </CardHeader>
        <CardContent>
          <Badge variant="destructive">Error loading lights</Badge>
        </CardContent>
      </Card>
    );
  }

  const handleLightToggle = (light: LightEntity) => {
    lightControl.toggle.mutate({ entityId: light.entity_id });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Lighting System</CardTitle>
        <CardDescription>
          Control RV interior and exterior lights ({lights?.length || 0} lights found)
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col gap-2">
          {lights && lights.length > 0 ? (
            lights.slice(0, 3).map((light) => (
              <Button
                key={light.entity_id}
                variant={light.state === 'on' ? 'default' : 'outline'}
                onClick={() => handleLightToggle(light)}
                disabled={lightControl.toggle.isPending}
                className="justify-between"
              >
                <span>{light.name || light.entity_id}</span>
                <Badge variant={light.state === 'on' ? 'default' : 'secondary'}>
                  {light.state}
                </Badge>
              </Button>
            ))
          ) : (
            <Badge variant="secondary">No lights available</Badge>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * System Status Component
 * Shows system health and CAN bus status
 */
function SystemStatusCard() {
  const { data: health, isLoading, error } = useHealthStatus();

  if (isLoading) {
    return <EntityCardSkeleton />;
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>System Status</CardTitle>
          <CardDescription>Monitor system health and connectivity</CardDescription>
        </CardHeader>
        <CardContent>
          <Badge variant="destructive">Error loading status</Badge>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>System Status</CardTitle>
        <CardDescription>Monitor system health and connectivity</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col gap-2">
          <div className="flex justify-between items-center">
            <span>Overall Status</span>
            <Badge variant={health?.status === 'healthy' ? 'default' :
                          health?.status === 'degraded' ? 'secondary' : 'destructive'}>
              {health?.status || 'Unknown'}
            </Badge>
          </div>
          <div className="flex justify-between items-center">
            <span>Database</span>
            <Badge variant={health?.features?.database ? 'default' : 'destructive'}>
              {health?.features?.database ? 'Connected' : 'Disconnected'}
            </Badge>
          </div>
          <div className="flex justify-between items-center">
            <span>CAN Bus</span>
            <Badge variant={health?.features?.can_interface ? 'default' : 'destructive'}>
              {health?.features?.can_interface ? 'Active' : 'Inactive'}
            </Badge>
          </div>
          <div className="flex justify-between items-center">
            <span>WebSocket</span>
            <Badge variant={health?.features?.websocket ? 'default' : 'destructive'}>
              {health?.features?.websocket ? 'Connected' : 'Disconnected'}
            </Badge>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * Entity Overview Component
 * Shows total entity counts and types
 */
function EntityOverviewCard() {
  const { data: entitiesData, isLoading, error } = useEntities();

  // Convert EntityCollection to array
  const entities = entitiesData ? Object.values(entitiesData) : [];

  if (isLoading) {
    return <EntityCardSkeleton />;
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Entity Overview</CardTitle>
          <CardDescription>Connected devices and sensors</CardDescription>
        </CardHeader>
        <CardContent>
          <Badge variant="destructive">Error loading entities</Badge>
        </CardContent>
      </Card>
    );
  }

  // Count entities by type
  const entityCounts = entities.reduce((acc, entity) => {
    acc[entity.device_type] = (acc[entity.device_type] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Entity Overview</CardTitle>
        <CardDescription>
          Connected devices and sensors ({entities.length} total)
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col gap-2">
          {Object.entries(entityCounts).map(([type, count]) => (
            <div key={type} className="flex justify-between items-center">
              <span className="capitalize">{type.replace('_', ' ')}</span>
              <Badge variant="secondary">{count as ReactNode}</Badge>
            </div>
          ))}
          {Object.keys(entityCounts).length === 0 && (
            <Badge variant="secondary">No entities found</Badge>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * Domain API v1 Status Component
 * Demonstrates the enhanced Domain API v1 progressive enhancement features
 */
function DomainAPIStatusCard() {
  const { data: isDomainAPIAvailable, isLoading, error } = useEntitiesDomainAPIAvailability();
  const { data: entities } = useEntities(); // Uses enhanced hook with progressive enhancement
  const bulkControl = useBulkEntityControl(); // Enhanced bulk operations

  if (isLoading) {
    return <EntityCardSkeleton />;
  }

  // Convert entities to array for bulk operations demo
  const entitiesArray = entities ? Object.values(entities) : [];
  const lightEntities = entitiesArray.filter(entity => entity.device_type === 'light');

  const handleBulkLightControl = (action: 'on' | 'off') => {
    const lightIds = lightEntities.map(light => light.entity_id);
    if (lightIds.length === 0) return;

    bulkControl.mutate({
      entityIds: lightIds.slice(0, 5), // Limit to first 5 for demo
      command: { command: 'set', state: action === 'on' },
      ignoreErrors: true,
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Domain API v1 Status</CardTitle>
        <CardDescription>Progressive enhancement with fallback support</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col gap-3">
          {/* API Status */}
          <div className="flex justify-between items-center">
            <span>Domain API v1</span>
            <Badge variant={isDomainAPIAvailable ? 'default' : 'secondary'}>
              {isDomainAPIAvailable ? 'Available' : 'Legacy Fallback'}
            </Badge>
          </div>

          {/* Features Status */}
          <div className="flex justify-between items-center">
            <span>Enhanced Features</span>
            <Badge variant={isDomainAPIAvailable ? 'default' : 'outline'}>
              {isDomainAPIAvailable ? 'Validation + Bulk Ops' : 'Basic Operations'}
            </Badge>
          </div>

          {/* Bulk Operations Demo */}
          {lightEntities.length > 0 && (
            <div className="flex flex-col gap-2 pt-2 border-t">
              <span className="text-sm font-medium">Bulk Light Control Demo</span>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => handleBulkLightControl('on')}
                  disabled={bulkControl.isPending}
                >
                  {bulkControl.isPending ? 'Processing...' : `Turn On ${Math.min(lightEntities.length, 5)} Lights`}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => handleBulkLightControl('off')}
                  disabled={bulkControl.isPending}
                >
                  Turn Off
                </Button>
              </div>
              <span className="text-xs text-muted-foreground">
                {isDomainAPIAvailable
                  ? 'Using Domain API v1 with validation and safety-aware optimistic updates'
                  : 'Using legacy API with individual calls fallback'}
              </span>
            </div>
          )}

          {/* Error State */}
          {error && (
            <Badge variant="destructive">
              Error: {error.message}
            </Badge>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * Main component export
 */
export {
  EntityCardSkeleton, EntityOverviewCard, LightControlCard,
  SystemStatusCard, DomainAPIStatusCard
};
