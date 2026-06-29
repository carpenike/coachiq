# Legacy to Domain API Migration Guide

This guide provides a comprehensive strategy for migrating from the existing monolithic API to the new Domain API v1, ensuring zero downtime and maintaining backward compatibility during the transition.

## Migration Overview

### Current State (Legacy API)
- Monolithic `/api/entities` endpoints
- Single large `entities.ts` API client
- Centralized types in `types.ts`
- Direct service calls from components
- Limited bulk operations support

### Target State (Domain API v1)
- Domain-driven `/api/v1/{domain}` endpoints
- Domain-specific API clients and hooks
- Type-safe schemas with runtime validation
- Enhanced bulk operations with optimistic updates
- Comprehensive monitoring and caching

### Migration Principles

1. **Zero Downtime**: Legacy and domain APIs run side-by-side
2. **Progressive Migration**: Gradual rollout with feature flags
3. **Backward Compatibility**: Legacy endpoints remain functional
4. **Safe Rollback**: Ability to revert changes quickly
5. **Data Consistency**: Shared data layer ensures consistency

## Migration Phases

### Phase 1: Foundation (✅ Completed)
- [x] Domain API backend infrastructure
- [x] Authentication and authorization
- [x] Monitoring and observability
- [x] Rate limiting and caching
- [x] Comprehensive testing

### Phase 2: Parallel Implementation (Current)
- [ ] Deploy domain APIs alongside legacy APIs
- [ ] Implement feature flags for gradual rollout
- [ ] Create migration utilities and helpers
- [ ] Establish monitoring and alerting

### Phase 3: Gradual Migration (Planned)
- [ ] Migrate low-risk endpoints first
- [ ] Update frontend components progressively
- [ ] Monitor performance and error rates
- [ ] Collect user feedback

### Phase 4: Full Migration (Future)
- [ ] Migrate all remaining endpoints
- [ ] Update all frontend components
- [ ] Remove legacy code paths
- [ ] Clean up technical debt

### Phase 5: Legacy Deprecation (Future)
- [ ] Mark legacy endpoints as deprecated
- [ ] Provide deprecation timeline
- [ ] Remove legacy endpoints
- [ ] Clean up legacy code

## Technical Migration Strategy

### Backend Migration

#### 1. Feature Flag Configuration

```yaml
# backend/services/feature_flags.yaml
api_migration:
  enabled: true
  core: false
  description: "Progressive API migration control"
  config:
    # Domain-specific rollout percentages
    entities_domain_rollout: 0.1  # Start with 10%
    diagnostics_domain_rollout: 0.0
    analytics_domain_rollout: 0.0

    # Fallback settings
    enable_legacy_fallback: true
    log_migration_events: true

    # Performance thresholds
    max_error_rate: 0.05  # 5% error rate threshold
    max_latency_p95: 2000  # 2 second P95 latency threshold
```

#### 2. Migration Middleware

```python
# backend/middleware/migration_middleware.py
import random
from typing import Optional
from fastapi import Request, Response
from backend.core.config import get_settings

class APIMigrationMiddleware:
    """Middleware to handle progressive API migration."""

    def __init__(self):
        self.settings = get_settings()

    async def __call__(self, request: Request, call_next):
        """Handle API migration routing."""

        # Check if this is a legacy API request
        if self._is_legacy_api_request(request):
            # Determine if we should migrate this request
            if self._should_migrate_request(request):
                # Attempt domain API first, fallback to legacy
                return await self._try_domain_api_with_fallback(request, call_next)
            else:
                # Use legacy API
                return await call_next(request)

        # Non-legacy requests continue normally
        return await call_next(request)

    def _is_legacy_api_request(self, request: Request) -> bool:
        """Check if request is for legacy API."""
        return request.url.path.startswith('/api/entities')

    def _should_migrate_request(self, request: Request) -> bool:
        """Determine if request should use domain API."""

        # Get migration configuration
        migration_config = self._get_migration_config(request)

        if not migration_config.get('enabled', False):
            return False

        # Get rollout percentage
        rollout_percentage = migration_config.get('rollout_percentage', 0.0)

        # Use user-based or session-based deterministic migration
        user_id = getattr(request.state, 'user_id', None)
        if user_id:
            # Deterministic based on user ID
            hash_value = hash(user_id) % 100
            return hash_value < (rollout_percentage * 100)
        else:
            # Random for anonymous users
            return random.random() < rollout_percentage

    async def _try_domain_api_with_fallback(self, request: Request, call_next):
        """Try domain API with automatic fallback to legacy."""

        try:
            # Transform legacy request to domain API request
            domain_request = await self._transform_to_domain_request(request)

            # Execute domain API
            response = await self._execute_domain_api(domain_request)

            # Log successful migration
            self._log_migration_event(request, 'domain_api_success')

            return response

        except Exception as e:
            # Log fallback event
            self._log_migration_event(request, 'fallback_to_legacy', error=str(e))

            # Fallback to legacy API
            return await call_next(request)
```

#### 3. Response Transformation Layer

```python
# backend/services/migration_service.py
from typing import Dict, Any, Optional
from backend.schemas.entities import EntitySchema, EntityCollectionSchema

class APIMigrationService:
    """Service to handle API response transformations."""

    def transform_legacy_to_domain_response(
        self,
        legacy_response: Dict[str, Any],
        endpoint_type: str
    ) -> Dict[str, Any]:
        """Transform legacy response to domain API format."""

        if endpoint_type == 'entity_list':
            return self._transform_entity_list(legacy_response)
        elif endpoint_type == 'single_entity':
            return self._transform_single_entity(legacy_response)
        elif endpoint_type == 'control_result':
            return self._transform_control_result(legacy_response)

        return legacy_response

    def transform_domain_to_legacy_response(
        self,
        domain_response: Dict[str, Any],
        endpoint_type: str
    ) -> Dict[str, Any]:
        """Transform domain response to legacy API format."""

        if endpoint_type == 'entity_collection':
            return self._transform_to_legacy_entity_list(domain_response)
        elif endpoint_type == 'entity_schema':
            return self._transform_to_legacy_entity(domain_response)

        return domain_response

    def _transform_entity_list(self, legacy_data: Dict) -> EntityCollectionSchema:
        """Transform legacy entity list to domain format."""
        entities = []

        for entity_id, entity_data in legacy_data.items():
            entities.append(EntitySchema(
                entity_id=entity_id,
                name=entity_data.get('friendly_name', entity_data.get('name', entity_id)),
                device_type=entity_data.get('device_type', 'unknown'),
                protocol=entity_data.get('protocol', 'rvc'),
                state=entity_data.get('raw', {}),
                area=entity_data.get('suggested_area'),
                last_updated=entity_data.get('last_updated', datetime.now().isoformat()),
                available=entity_data.get('available', True)
            ))

        return EntityCollectionSchema(
            entities=entities,
            total_count=len(entities),
            page=1,
            page_size=len(entities),
            has_next=False,
            filters_applied={}
        )
```

### Frontend Migration

#### 1. Progressive Migration Hook

```typescript
// frontend/src/hooks/useMigrationStrategy.ts
import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';

interface MigrationConfig {
  entities_domain_enabled: boolean;
  rollout_percentage: number;
  enable_fallback: boolean;
}

export function useMigrationStrategy() {
  const [migrationConfig, setMigrationConfig] = useState<MigrationConfig | null>(null);

  // Fetch migration configuration
  const { data: config } = useQuery({
    queryKey: ['migration-config'],
    queryFn: () => fetch('/api/config/migration').then(r => r.json()),
    staleTime: 60000, // Cache for 1 minute
  });

  useEffect(() => {
    if (config) {
      setMigrationConfig(config);
    }
  }, [config]);

  const shouldUseDomainAPI = (domain: string, userId?: string): boolean => {
    if (!migrationConfig || !migrationConfig[`${domain}_domain_enabled`]) {
      return false;
    }

    const rolloutPercentage = migrationConfig.rollout_percentage;

    if (userId) {
      // Deterministic based on user ID
      const hash = hashCode(userId);
      return (hash % 100) < (rolloutPercentage * 100);
    }

    // Use stored migration flag for session consistency
    const storageKey = `migration_${domain}`;
    const stored = localStorage.getItem(storageKey);

    if (stored !== null) {
      return stored === 'true';
    }

    // Determine migration status and store it
    const shouldMigrate = Math.random() < rolloutPercentage;
    localStorage.setItem(storageKey, shouldMigrate.toString());

    return shouldMigrate;
  };

  return {
    migrationConfig,
    shouldUseDomainAPI,
  };
}

function hashCode(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash; // Convert to 32-bit integer
  }
  return Math.abs(hash);
}
```

#### 2. Migration-Aware API Client

```typescript
// frontend/src/api/migratedEntitiesClient.ts
import { withDomainAPIFallback } from './domains';
import { fetchEntities as fetchEntitiesLegacy } from './endpoints';
import { fetchEntitiesV2 } from './domains/entities';
import { useMigrationStrategy } from '../hooks/useMigrationStrategy';

interface MigratedEntitiesClientOptions {
  preferDomainAPI?: boolean;
  enableFallback?: boolean;
  userId?: string;
}

export class MigratedEntitiesClient {
  private migrationStrategy = useMigrationStrategy();

  async fetchEntities(
    params?: any,
    options: MigratedEntitiesClientOptions = {}
  ) {
    const shouldUseDomain = options.preferDomainAPI ??
      this.migrationStrategy.shouldUseDomainAPI('entities', options.userId);

    if (shouldUseDomain) {
      return withDomainAPIFallback(
        () => fetchEntitiesV2(params),
        () => fetchEntitiesLegacy(params),
        {
          preferDomainAPI: true,
          fallbackToLegacy: options.enableFallback ?? true,
          logMigration: true,
        }
      );
    }

    return fetchEntitiesLegacy(params);
  }

  async controlEntity(entityId: string, command: any, options: MigratedEntitiesClientOptions = {}) {
    const shouldUseDomain = options.preferDomainAPI ??
      this.migrationStrategy.shouldUseDomainAPI('entities', options.userId);

    if (shouldUseDomain) {
      return withDomainAPIFallback(
        () => controlEntityV2(entityId, command),
        () => controlEntityLegacy(entityId, command),
        {
          preferDomainAPI: true,
          fallbackToLegacy: options.enableFallback ?? true,
          logMigration: true,
        }
      );
    }

    return controlEntityLegacy(entityId, command);
  }
}

// Singleton instance
export const migratedEntitiesClient = new MigratedEntitiesClient();
```

#### 3. Progressive Component Migration

```typescript
// frontend/src/components/EntityListV2.tsx
import React from 'react';
import { useEntitiesV2 } from '@/hooks/domains/useEntitiesV2';
import { useEntities } from '@/hooks/useEntities';
import { useMigrationStrategy } from '@/hooks/useMigrationStrategy';
import { useAuth } from '@/contexts/auth-context';

interface EntityListV2Props {
  forceDomainAPI?: boolean;
  forceLegacyAPI?: boolean;
}

export function EntityListV2({
  forceDomainAPI = false,
  forceLegacyAPI = false
}: EntityListV2Props) {
  const { user } = useAuth();
  const { shouldUseDomainAPI } = useMigrationStrategy();

  // Determine which API to use
  const useDomainAPI = forceDomainAPI || (
    !forceLegacyAPI && shouldUseDomainAPI('entities', user?.id)
  );

  // Use appropriate hook based on migration decision
  const domainResult = useEntitiesV2(undefined, { enabled: useDomainAPI });
  const legacyResult = useEntities({ enabled: !useDomainAPI });

  const result = useDomainAPI ? domainResult : legacyResult;

  // Transform data to common format if needed
  const entities = useDomainAPI
    ? result.data?.entities || []
    : Object.values(result.data || {});

  if (result.isLoading) {
    return <div>Loading entities...</div>;
  }

  if (result.error) {
    return <div>Error loading entities: {result.error.message}</div>;
  }

  return (
    <div className="space-y-4">
      {/* Migration indicator (development only) */}
      {process.env.NODE_ENV === 'development' && (
        <div className="text-xs text-gray-500 bg-gray-100 p-2 rounded">
          Using {useDomainAPI ? 'Domain API v1' : 'Legacy API'}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {entities.map((entity) => (
          <EntityCard
            key={entity.entity_id}
            entity={entity}
            useDomainAPI={useDomainAPI}
          />
        ))}
      </div>
    </div>
  );
}

interface EntityCardProps {
  entity: any;
  useDomainAPI: boolean;
}

function EntityCard({ entity, useDomainAPI }: EntityCardProps) {
  // Use appropriate control hook based on API version
  const domainControl = useControlEntityV2();
  const legacyControl = useControlEntity();

  const control = useDomainAPI ? domainControl : legacyControl;

  const handleToggle = () => {
    if (useDomainAPI) {
      control.mutate({
        entityId: entity.entity_id,
        command: { command: 'toggle' }
      });
    } else {
      control.mutate({
        entityId: entity.entity_id,
        command: 'toggle'
      });
    }
  };

  return (
    <div className="border rounded p-4 space-y-2">
      <h3 className="font-medium">{entity.name || entity.friendly_name}</h3>
      <div className="text-sm text-gray-600">
        State: {useDomainAPI ? entity.state?.state : entity.state}
      </div>
      <button
        onClick={handleToggle}
        disabled={control.isPending}
        className="px-3 py-1 bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-50"
      >
        {control.isPending ? 'Updating...' : 'Toggle'}
      </button>
    </div>
  );
}
```

## Migration Monitoring

### 1. Migration Metrics Dashboard

```typescript
// frontend/src/components/admin/MigrationDashboard.tsx
import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';

interface MigrationMetrics {
  domain_api_usage: number;
  legacy_api_usage: number;
  error_rate: number;
  avg_response_time: number;
  migration_percentage: number;
}

export function MigrationDashboard() {
  const { data: metrics } = useQuery({
    queryKey: ['migration-metrics'],
    queryFn: () => fetch('/api/admin/migration/metrics').then(r => r.json()),
    refetchInterval: 30000, // Refresh every 30 seconds
  });

  if (!metrics) {
    return <div>Loading migration metrics...</div>;
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">API Migration Dashboard</h1>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Migration Progress</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <Progress value={metrics.migration_percentage} />
              <div className="text-2xl font-bold">{metrics.migration_percentage}%</div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Domain API Usage</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{metrics.domain_api_usage}</div>
            <div className="text-sm text-gray-600">requests/hour</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Legacy API Usage</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{metrics.legacy_api_usage}</div>
            <div className="text-sm text-gray-600">requests/hour</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Error Rate</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{(metrics.error_rate * 100).toFixed(2)}%</div>
            <div className={`text-sm ${metrics.error_rate > 0.05 ? 'text-red-600' : 'text-green-600'}`}>
              {metrics.error_rate > 0.05 ? 'Above threshold' : 'Normal'}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Migration Controls */}
      <MigrationControls />
    </div>
  );
}
```

### 2. Migration Control Panel

```typescript
// frontend/src/components/admin/MigrationControls.tsx
import React, { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Slider } from '@/components/ui/slider';
import { Switch } from '@/components/ui/switch';

export function MigrationControls() {
  const [rolloutPercentage, setRolloutPercentage] = useState([10]);
  const [enableFallback, setEnableFallback] = useState(true);
  const queryClient = useQueryClient();

  const updateMigrationConfig = useMutation({
    mutationFn: (config: any) =>
      fetch('/api/admin/migration/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['migration-metrics'] });
    },
  });

  const handleUpdateConfig = () => {
    updateMigrationConfig.mutate({
      entities_domain_rollout: rolloutPercentage[0] / 100,
      enable_legacy_fallback: enableFallback,
    });
  };

  const handleEmergencyRollback = () => {
    updateMigrationConfig.mutate({
      entities_domain_rollout: 0,
      enable_legacy_fallback: true,
      emergency_rollback: true,
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Migration Controls</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="space-y-4">
          <div>
            <label className="text-sm font-medium">
              Domain API Rollout: {rolloutPercentage[0]}%
            </label>
            <Slider
              value={rolloutPercentage}
              onValueChange={setRolloutPercentage}
              max={100}
              step={5}
              className="mt-2"
            />
          </div>

          <div className="flex items-center justify-between">
            <label className="text-sm font-medium">Enable Legacy Fallback</label>
            <Switch
              checked={enableFallback}
              onCheckedChange={setEnableFallback}
            />
          </div>
        </div>

        <div className="flex gap-2">
          <Button
            onClick={handleUpdateConfig}
            disabled={updateMigrationConfig.isPending}
          >
            Update Configuration
          </Button>

          <Button
            variant="destructive"
            onClick={handleEmergencyRollback}
            disabled={updateMigrationConfig.isPending}
          >
            Emergency Rollback
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
```

## Migration Runbook

### Pre-Migration Checklist

- [ ] **Infrastructure Ready**
  - [ ] Domain API endpoints deployed and tested
  - [ ] Monitoring and alerting configured
  - [ ] Database migrations completed
  - [ ] Feature flags configured

- [ ] **Testing Complete**
  - [ ] Unit tests passing for all components
  - [ ] Integration tests covering migration scenarios
  - [ ] Performance tests meeting benchmarks
  - [ ] User acceptance testing completed

- [ ] **Rollback Plan**
  - [ ] Emergency rollback procedure documented
  - [ ] Database rollback scripts prepared
  - [ ] Monitoring alerts for migration issues
  - [ ] Communication plan for issues

### Migration Execution Steps

#### Phase 1: Initial Rollout (1% traffic)
1. Enable domain API for 1% of users
2. Monitor error rates and performance
3. Collect initial feedback
4. Address any critical issues

#### Phase 2: Gradual Increase (5% → 25% → 50%)
1. Increase rollout percentage in stages
2. Monitor metrics at each stage
3. Gather user feedback
4. Optimize performance based on data

#### Phase 3: Majority Migration (75% → 95%)
1. Continue increasing percentage
2. Focus on edge cases and error scenarios
3. Prepare for legacy deprecation
4. Update documentation

#### Phase 4: Complete Migration (100%)
1. Migrate all remaining traffic
2. Monitor for any final issues
3. Begin legacy deprecation process
4. Celebrate successful migration! 🎉

### Post-Migration Tasks

- [ ] **Performance Optimization**
  - [ ] Analyze performance metrics
  - [ ] Optimize slow endpoints
  - [ ] Tune caching strategies
  - [ ] Update monitoring thresholds

- [ ] **Documentation Updates**
  - [ ] Update API documentation
  - [ ] Create migration guides for other teams
  - [ ] Document lessons learned
  - [ ] Update onboarding materials

- [ ] **Legacy Cleanup**
  - [ ] Mark legacy endpoints as deprecated
  - [ ] Set deprecation timeline
  - [ ] Remove unused code paths
  - [ ] Clean up technical debt

## Troubleshooting Guide

### Common Migration Issues

#### 1. High Error Rate During Migration
**Symptoms**: Error rate exceeds 5% threshold
**Diagnosis**:
- Check logs for specific error patterns
- Verify data transformation correctness
- Check authentication/authorization issues

**Resolution**:
- Reduce rollout percentage
- Fix specific error patterns
- Update transformation logic
- Increase monitoring frequency

#### 2. Performance Degradation
**Symptoms**: Response times increase significantly
**Diagnosis**:
- Check database query performance
- Verify caching effectiveness
- Monitor resource usage

**Resolution**:
- Optimize database queries
- Adjust cache TTL settings
- Scale infrastructure if needed
- Optimize data transformation

#### 3. Data Inconsistency
**Symptoms**: Different responses from domain vs legacy APIs
**Diagnosis**:
- Compare response structures
- Check data transformation logic
- Verify database state

**Resolution**:
- Fix transformation logic
- Update schema mappings
- Synchronize data sources
- Add data validation

### Emergency Procedures

#### Immediate Rollback
```bash
# Emergency rollback to 0% domain API usage
curl -X POST /api/admin/migration/emergency-rollback \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"reason": "High error rate detected"}'
```

#### Health Check Commands
```bash
# Check migration status
curl /api/admin/migration/status

# Check domain API health
curl /api/v1/entities/health

# Check legacy API health
curl /api/entities/health
```

## Success Metrics

### Key Performance Indicators

1. **Migration Progress**: Percentage of traffic using domain API
2. **Error Rate**: Domain API error rate vs legacy API
3. **Performance**: Response time comparison
4. **User Satisfaction**: User feedback and adoption metrics
5. **Developer Experience**: Development velocity and bug reports

### Success Criteria

- [ ] 100% traffic migrated to domain API
- [ ] Error rate below 1%
- [ ] Performance improvement of 20%+
- [ ] Zero data loss during migration
- [ ] Positive developer feedback
- [ ] Successful legacy API deprecation

This comprehensive migration strategy ensures a smooth, safe, and successful transition from the legacy monolithic API to the new Domain API v1 architecture.
