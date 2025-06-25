/**
 * Configuration Management Page
 *
 * Provides comprehensive configuration management interface for CoachIQ system
 * with multi-protocol support, feature flag management, and real-time validation.
 */

import {
    disableFeature,
    enableFeature,
    fetchCANInterfaceMappings,
    fetchCoachConfiguration,
    fetchDatabaseConfiguration,
    fetchFeatureManagement,
    fetchSystemSettings
} from '@/api/endpoints';
import type {
    CANInterfaceMapping,
    FeatureFlag
} from '@/api/types';
import { AppLayout } from '@/components/app-layout';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
    AlertTriangle,
    ChevronDown,
    ChevronRight,
    Database,
    GitBranch,
    Network,
    RefreshCw,
    Search,
    Settings,
    Shield,
    Zap
} from 'lucide-react';
import { useMemo, useState } from 'react';

export default function ConfigurationPage() {
  const [activeTab, setActiveTab] = useState('overview');
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [selectedStability, setSelectedStability] = useState<string>('all');
  const [collapsedSections, setCollapsedSections] = useState<Record<string, boolean>>({});
  const queryClient = useQueryClient();

  // Data queries
  const { data: systemSettings, isLoading: settingsLoading, error: settingsError } = useQuery({
    queryKey: ['systemSettings'],
    queryFn: fetchSystemSettings,
    refetchInterval: 30000, // Refresh every 30 seconds
  });

  const { data: databaseConfig, isLoading: dbLoading } = useQuery({
    queryKey: ['databaseConfiguration'],
    queryFn: fetchDatabaseConfiguration,
    refetchInterval: 30000,
  });

  const { data: featureManagement, isLoading: featuresLoading } = useQuery({
    queryKey: ['featureManagement'],
    queryFn: fetchFeatureManagement,
    refetchInterval: 15000,
  });

  const { data: canInterfaces, isLoading: interfacesLoading } = useQuery({
    queryKey: ['canInterfaceMappings'],
    queryFn: fetchCANInterfaceMappings,
    refetchInterval: 15000,
  });

  const { data: coachConfig, isLoading: coachLoading } = useQuery({
    queryKey: ['coachConfiguration'],
    queryFn: fetchCoachConfiguration,
  });

  // Mutations
  const updateFeatureMutation = useMutation({
    mutationFn: ({ featureName, enabled }: { featureName: string; enabled: boolean }) =>
      enabled ? enableFeature(featureName) : disableFeature(featureName),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['featureManagement'] });
    },
  });

  // Helper functions
  const handleFeatureToggle = (featureName: string, enabled: boolean) => {
    updateFeatureMutation.mutate({ featureName, enabled });
  };

  const toggleSectionCollapse = (category: string) => {
    setCollapsedSections(prev => ({
      ...prev,
      [category]: !prev[category]
    }));
  };

  // Calculate dependency chain impact
  const getDependencyChain = (featureName: string, direction: 'up' | 'down', visited = new Set<string>()): string[] => {
    if (visited.has(featureName) || !featureManagement?.features[featureName]) return [];

    visited.add(featureName);
    const feature = featureManagement.features[featureName];
    const deps = direction === 'up' ? feature.dependencies : feature.dependent_features;

    const chain: string[] = [];
    deps?.forEach(dep => {
      chain.push(dep);
      chain.push(...getDependencyChain(dep, direction, visited));
    });

    return [...new Set(chain)]; // Remove duplicates
  };

  const getFeatureRisk = (feature: FeatureFlag, featureName: string) => {
    const missingDeps = feature.dependencies?.filter(dep => !featureManagement?.features[dep]?.enabled) || [];
    const affectedDependents = feature.dependent_features?.filter(dep => featureManagement?.features[dep]?.enabled) || [];
    const upstreamChain = getDependencyChain(featureName, 'up');
    const downstreamChain = getDependencyChain(featureName, 'down');

    return {
      missingDeps,
      affectedDependents,
      upstreamChain,
      downstreamChain,
      riskLevel: missingDeps.length > 0 ? 'high' : affectedDependents.length > 0 ? 'medium' : 'low'
    };
  };

  // Filter and group features
  const { filteredFeatures, groupedFeatures, categories, stabilities } = useMemo(() => {
    if (!featureManagement?.features) {
      return { filteredFeatures: [], groupedFeatures: {}, categories: [], stabilities: [] };
    }

    const features = Object.entries(featureManagement.features);

    // Extract unique categories and stabilities
    const uniqueCategories = [...new Set(features.map(([, feature]) => feature.category))];
    const uniqueStabilities = [...new Set(features.map(([, feature]) => feature.stability))];

    // Filter features
    const filtered = features.filter(([_featureName, feature]) => {
      const matchesSearch = !searchTerm ||
        feature.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        feature.description?.toLowerCase().includes(searchTerm.toLowerCase());

      const matchesCategory = selectedCategory === 'all' || feature.category === selectedCategory;
      const matchesStability = selectedStability === 'all' || feature.stability === selectedStability;

      return matchesSearch && matchesCategory && matchesStability;
    });

    // Group filtered features by category
    const grouped = filtered.reduce((acc, [featureName, feature]) => {
      const category = feature.category;
      if (!acc[category]) {
        acc[category] = [];
      }
      acc[category].push([featureName, feature]);
      return acc;
    }, {} as Record<string, [string, FeatureFlag][]>);

    return {
      filteredFeatures: filtered,
      groupedFeatures: grouped,
      categories: uniqueCategories,
      stabilities: uniqueStabilities
    };
  }, [featureManagement?.features, searchTerm, selectedCategory, selectedStability]);

  return (
    <AppLayout pageTitle="Configuration Management">
      <div className="container mx-auto p-6 space-y-6">
        {/* Action Buttons */}
        <div className="flex items-center justify-end space-x-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => void queryClient.invalidateQueries()}
          >
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
        </div>

        {/* Error State */}
        {settingsError && (
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>Configuration Error</AlertTitle>
            <AlertDescription>
              Failed to load system configuration. Please check your connection and try again.
            </AlertDescription>
          </Alert>
        )}

        {/* Configuration Tabs */}
        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
          <TabsList className="grid w-full grid-cols-5">
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="features">Features</TabsTrigger>
            <TabsTrigger value="interfaces">CAN Interfaces</TabsTrigger>
            <TabsTrigger value="protocols">Protocols</TabsTrigger>
            <TabsTrigger value="coach">Coach Config</TabsTrigger>
          </TabsList>

          {/* Overview Tab */}
          <TabsContent value="overview" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center">
                  <Settings className="h-5 w-5 mr-2" />
                  System Settings Overview
                </CardTitle>
                <CardDescription>
                  Current system configuration and operational parameters
                </CardDescription>
              </CardHeader>
              <CardContent>
                {settingsLoading ? (
                  <div className="flex items-center justify-center py-8">
                    <RefreshCw className="h-6 w-6 animate-spin text-blue-600 mr-2" />
                    <span>Loading system settings...</span>
                  </div>
                ) : systemSettings ? (
                  <div className="space-y-6">
                    {/* Basic Overview */}
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                      <div className="space-y-2">
                        <h4 className="font-semibold text-sm">Environment</h4>
                        <div className="text-sm space-y-1">
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Variables:</span>
                            <span>{Object.keys(systemSettings.environment_variables || {}).length}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Environment:</span>
                            <span>{systemSettings.metadata?.environment || 'N/A'}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Debug:</span>
                            <span>{systemSettings.metadata?.debug ? 'Yes' : 'No'}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">App Name:</span>
                            <span>{systemSettings.metadata?.app_name || 'N/A'}</span>
                          </div>
                        </div>
                      </div>
                      <div className="space-y-2">
                        <h4 className="font-semibold text-sm">Server</h4>
                        <div className="text-sm space-y-1">
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Host:</span>
                            <span>{systemSettings.sections?.server?.host || 'N/A'}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Port:</span>
                            <span>{systemSettings.sections?.server?.port || 'N/A'}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Workers:</span>
                            <span>{systemSettings.sections?.server?.workers || 'N/A'}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Reload:</span>
                            <span>{systemSettings.sections?.server?.reload ? 'Yes' : 'No'}</span>
                          </div>
                        </div>
                      </div>
                      <div className="space-y-2">
                        <h4 className="font-semibold text-sm">Persistence</h4>
                        <div className="text-sm space-y-1">
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Enabled:</span>
                            <span>{systemSettings.sections?.persistence?.enabled ? 'Yes' : 'No'}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Backend:</span>
                            <span>{systemSettings.sections?.persistence?.backend_type || 'N/A'}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Compression:</span>
                            <span>{systemSettings.sections?.persistence?.enable_compression ? 'Yes' : 'No'}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Retention:</span>
                            <span>{systemSettings.sections?.persistence?.retention_days || 'N/A'} days</span>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Detailed Configuration Sections */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <h4 className="font-semibold text-sm">Security</h4>
                        <div className="text-sm space-y-1">
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">CSRF Protection:</span>
                            <span>{systemSettings.sections?.security?.enable_csrf ? 'Yes' : 'No'}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">XSS Protection:</span>
                            <span>{systemSettings.sections?.security?.enable_xss_protection ? 'Yes' : 'No'}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Rate Limiting:</span>
                            <span>{systemSettings.sections?.security?.rate_limit_enabled ? 'Yes' : 'No'}</span>
                          </div>
                          {systemSettings.sections?.security?.rate_limit_enabled && (
                            <div className="flex justify-between">
                              <span className="text-muted-foreground">Rate Limit:</span>
                              <span>{systemSettings.sections?.security?.rate_limit_requests}/{systemSettings.sections?.security?.rate_limit_window}s</span>
                            </div>
                          )}
                        </div>
                      </div>
                      <div className="space-y-2">
                        <h4 className="font-semibold text-sm">Logging</h4>
                        <div className="text-sm space-y-1">
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Level:</span>
                            <span>{systemSettings.sections?.logging?.level || 'N/A'}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Console:</span>
                            <span>{systemSettings.sections?.logging?.console_enabled ? 'Yes' : 'No'}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">File:</span>
                            <span>{systemSettings.sections?.logging?.file_enabled ? 'Yes' : 'No'}</span>
                          </div>
                          {systemSettings.sections?.logging?.file_enabled && (
                            <div className="flex justify-between">
                              <span className="text-muted-foreground">Backup Count:</span>
                              <span>{systemSettings.sections?.logging?.backup_count || 'N/A'}</span>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* RV-C and CAN Configuration */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <h4 className="font-semibold text-sm">RV-C Protocol</h4>
                        <div className="text-sm space-y-1">
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Encoder:</span>
                            <span>{systemSettings.sections?.rvc?.enable_encoder ? 'Yes' : 'No'}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Decoder:</span>
                            <span>{systemSettings.sections?.rvc?.enable_decoder ? 'Yes' : 'No'}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Validation:</span>
                            <span>{systemSettings.sections?.rvc?.enable_validation ? 'Yes' : 'No'}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Caching:</span>
                            <span>{systemSettings.sections?.rvc?.enable_caching ? 'Yes' : 'No'}</span>
                          </div>
                        </div>
                      </div>
                      <div className="space-y-2">
                        <h4 className="font-semibold text-sm">CAN Bus</h4>
                        <div className="text-sm space-y-1">
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Interfaces:</span>
                            <span>{systemSettings.sections?.can?.interfaces?.length || 0}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Bitrate:</span>
                            <span>{systemSettings.sections?.can?.bitrate || 'N/A'}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">FD Support:</span>
                            <span>{systemSettings.sections?.can?.enable_fd ? 'Yes' : 'No'}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Statistics:</span>
                            <span>{systemSettings.sections?.can?.enable_statistics ? 'Yes' : 'No'}</span>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Authentication and Notifications */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <h4 className="font-semibold text-sm">Authentication</h4>
                        <div className="text-sm space-y-1">
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Enabled:</span>
                            <span>{systemSettings.sections?.auth?.enabled ? 'Yes' : 'No'}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Provider:</span>
                            <span>{systemSettings.sections?.auth?.provider || 'N/A'}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Session Timeout:</span>
                            <span>{systemSettings.sections?.auth?.session_timeout || 'N/A'}s</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Email Verification:</span>
                            <span>{systemSettings.sections?.auth?.require_email_verification ? 'Yes' : 'No'}</span>
                          </div>
                        </div>
                      </div>
                      <div className="space-y-2">
                        <h4 className="font-semibold text-sm">Notifications</h4>
                        <div className="text-sm space-y-1">
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Enabled:</span>
                            <span>{systemSettings.sections?.notifications?.enabled ? 'Yes' : 'No'}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Max History:</span>
                            <span>{systemSettings.sections?.notifications?.max_history || 'N/A'}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Default Severity:</span>
                            <span>{systemSettings.sections?.notifications?.default_severity || 'N/A'}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Rate Limit:</span>
                            <span>{systemSettings.sections?.notifications?.rate_limit_per_minute || 'N/A'}/min</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="text-center py-8 text-muted-foreground">
                    No system settings available
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Database Configuration Card */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center">
                  <Database className="h-5 w-5 mr-2" />
                  Database Configuration
                </CardTitle>
                <CardDescription>
                  Current database backend and connection settings
                </CardDescription>
              </CardHeader>
              <CardContent>
                {dbLoading ? (
                  <div className="flex items-center justify-center py-8">
                    <RefreshCw className="h-6 w-6 animate-spin text-blue-600 mr-2" />
                    <span>Loading database configuration...</span>
                  </div>
                ) : databaseConfig ? (
                  <div className="space-y-4">
                    <div className="flex items-center justify-between">
                      <span className="text-lg font-medium">Backend: {databaseConfig.backend.toUpperCase()}</span>
                      <Badge variant={databaseConfig.health_status === 'healthy' ? 'default' : 'destructive'}>
                        {databaseConfig.health_status}
                      </Badge>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {/* SQLite Configuration */}
                      {databaseConfig.backend === 'sqlite' && (
                        <div className="space-y-2">
                          <h4 className="font-semibold text-sm">SQLite Settings</h4>
                          <div className="text-sm space-y-1">
                            <div className="flex justify-between">
                              <span className="text-muted-foreground">Path:</span>
                              <span className="text-xs font-mono">{databaseConfig.sqlite.path}</span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-muted-foreground">Timeout:</span>
                              <span>{databaseConfig.sqlite.timeout}s</span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-muted-foreground">Optimizations:</span>
                              <span>{databaseConfig.sqlite.optimizations_enabled ? 'Yes' : 'No'}</span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-muted-foreground">Cache Size:</span>
                              <span>{databaseConfig.sqlite.cache_size} pages</span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-muted-foreground">Memory Map:</span>
                              <span>{(databaseConfig.sqlite.mmap_size / 1024 / 1024).toFixed(0)} MB</span>
                            </div>
                          </div>
                        </div>
                      )}

                      {/* PostgreSQL Configuration */}
                      {databaseConfig.backend === 'postgresql' && (
                        <div className="space-y-2">
                          <h4 className="font-semibold text-sm">PostgreSQL Settings</h4>
                          <div className="text-sm space-y-1">
                            <div className="flex justify-between">
                              <span className="text-muted-foreground">Host:</span>
                              <span>{databaseConfig.postgresql.host}:{databaseConfig.postgresql.port}</span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-muted-foreground">Database:</span>
                              <span>{databaseConfig.postgresql.database}</span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-muted-foreground">User:</span>
                              <span>{databaseConfig.postgresql.user}</span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-muted-foreground">Schema:</span>
                              <span>{databaseConfig.postgresql.schema}</span>
                            </div>
                          </div>
                        </div>
                      )}

                      {/* Connection Pool Settings */}
                      <div className="space-y-2">
                        <h4 className="font-semibold text-sm">Connection Pool</h4>
                        <div className="text-sm space-y-1">
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Pool Size:</span>
                            <span>{databaseConfig.pool.size}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Max Overflow:</span>
                            <span>{databaseConfig.pool.max_overflow}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Timeout:</span>
                            <span>{databaseConfig.pool.timeout}s</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Recycle:</span>
                            <span>{databaseConfig.pool.recycle}s</span>
                          </div>
                        </div>
                      </div>

                      {/* Performance Settings */}
                      <div className="space-y-2">
                        <h4 className="font-semibold text-sm">Performance</h4>
                        <div className="text-sm space-y-1">
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Echo SQL:</span>
                            <span>{databaseConfig.performance.echo_sql ? 'Yes' : 'No'}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Echo Pool:</span>
                            <span>{databaseConfig.performance.echo_pool ? 'Yes' : 'No'}</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="text-center py-8 text-muted-foreground">
                    No database configuration available
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Features Tab */}
          <TabsContent value="features" className="space-y-4">
            {/* Feature Summary */}
            {featuresLoading ? (
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                {[...Array(4)].map((_, i) => (
                  <Card key={i}>
                    <CardContent className="p-4">
                      <div className="text-center">
                        <div className="h-8 w-16 bg-gray-200 rounded mx-auto mb-2 animate-pulse" />
                        <div className="h-4 w-24 bg-gray-200 rounded mx-auto animate-pulse" />
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            ) : featureManagement && (
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <Card>
                  <CardContent className="p-4">
                    <div className="text-center">
                      <div className="text-2xl font-bold text-blue-600">
                        {Object.keys(featureManagement.features).length}
                      </div>
                      <div className="text-sm text-muted-foreground">Total Features</div>
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="p-4">
                    <div className="text-center">
                      <div className="text-2xl font-bold text-green-600">
                        {Object.values(featureManagement.features).filter(f => f.enabled).length}
                      </div>
                      <div className="text-sm text-muted-foreground">Enabled</div>
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="p-4">
                    <div className="text-center">
                      <div className="text-2xl font-bold text-orange-600">
                        {Object.values(featureManagement.features).filter(f => f.category === 'core').length}
                      </div>
                      <div className="text-sm text-muted-foreground">Core Features</div>
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="p-4">
                    <div className="text-center">
                      <div className="text-2xl font-bold text-purple-600">
                        {featureManagement.validation_errors?.length || 0}
                      </div>
                      <div className="text-sm text-muted-foreground">Validation Errors</div>
                    </div>
                  </CardContent>
                </Card>
              </div>
            )}

            {/* Validation Errors Alert */}
            {featureManagement?.validation_errors && featureManagement.validation_errors.length > 0 && (
              <Alert variant="destructive">
                <AlertTriangle className="h-4 w-4" />
                <AlertTitle>Feature Configuration Issues</AlertTitle>
                <AlertDescription>
                  <ul className="list-disc list-inside space-y-1">
                    {featureManagement.validation_errors.map((error, index) => (
                      <li key={index}>{error}</li>
                    ))}
                  </ul>
                </AlertDescription>
              </Alert>
            )}

            {/* Search and Filter Controls */}
            {!featuresLoading && (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center">
                    <Search className="h-5 w-5 mr-2" />
                    Search & Filter Features
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="flex flex-col md:flex-row gap-4">
                    <div className="flex-1">
                      <Input
                        placeholder="Search features by name or description..."
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        className="w-full"
                      />
                    </div>
                    <div className="flex gap-2">
                      <Select value={selectedCategory} onValueChange={setSelectedCategory}>
                        <SelectTrigger className="w-40">
                          <SelectValue placeholder="Category" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all">All Categories</SelectItem>
                          {categories.map((category) => (
                            <SelectItem key={category} value={category} className="capitalize">
                              {category}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <Select value={selectedStability} onValueChange={setSelectedStability}>
                        <SelectTrigger className="w-36">
                          <SelectValue placeholder="Stability" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all">All Stability</SelectItem>
                          {stabilities.map((stability) => (
                            <SelectItem key={stability} value={stability} className="capitalize">
                              {stability}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                  <div className="mt-4 text-sm text-muted-foreground">
                    Showing {filteredFeatures.length} of {Object.keys(featureManagement?.features || {}).length} features
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Grouped Features Display */}
            {featureManagement && Object.keys(featureManagement.features).length > 0 ? (
              <div className="space-y-6">
                {Object.entries(groupedFeatures).map(([category, features]) => {
                  const isCollapsed = collapsedSections[category];
                  return (
                    <Card key={category}>
                      <CardHeader
                        className="cursor-pointer hover:bg-muted/50 transition-colors"
                        onClick={() => toggleSectionCollapse(category)}
                      >
                        <CardTitle className="flex items-center">
                          {isCollapsed ? (
                            <ChevronRight className="h-5 w-5 mr-2" />
                          ) : (
                            <ChevronDown className="h-5 w-5 mr-2" />
                          )}
                          <Zap className="h-5 w-5 mr-2" />
                          <span className="capitalize">{category} Features</span>
                          <Badge variant="outline" className="ml-2">
                            {features.length}
                          </Badge>
                        </CardTitle>
                        <CardDescription>
                          {category === 'core' && 'Essential system features required for basic operation'}
                          {category === 'protocol' && 'Protocol-specific features and integrations'}
                          {category === 'advanced' && 'Advanced features for enhanced functionality'}
                          {category === 'experimental' && 'Experimental features in development'}
                        </CardDescription>
                      </CardHeader>
                      {!isCollapsed && (
                        <CardContent>
                          <div className="space-y-4">
                            {features.map(([featureName, feature]: [string, FeatureFlag]) => (
                              <div key={featureName} className="flex items-start justify-between p-4 border rounded-lg hover:shadow-sm transition-shadow">
                                <div className="space-y-2 flex-1">
                                  <div className="flex items-center space-x-2 flex-wrap">
                                    <h4 className="font-medium text-lg">{feature.name}</h4>
                                    <Badge
                                      variant={feature.enabled ? 'default' : 'secondary'}
                                      className={feature.enabled ? 'bg-green-100 text-green-800 border-green-200' : 'bg-gray-100 text-gray-600 border-gray-200'}
                                    >
                                      {feature.enabled ? '✓ Enabled' : '○ Disabled'}
                                    </Badge>
                                    <Badge
                                      variant={feature.stability === 'stable' ? 'default' :
                                              feature.stability === 'beta' ? 'secondary' : 'destructive'}
                                      className="capitalize text-xs"
                                    >
                                      {feature.stability}
                                    </Badge>
                                  </div>
                                  <p className="text-sm text-muted-foreground leading-relaxed">
                                    {feature.description || 'No description available'}
                                  </p>
                                  {(() => {
                                    const risk = getFeatureRisk(feature, featureName);
                                    const hasDependencies = (feature.dependencies?.length || 0) > 0;
                                    const hasDependents = (feature.dependent_features?.length || 0) > 0;
                                    const hasRestrictions = (feature.environment_restrictions?.length || 0) > 0;

                                    if (!hasDependencies && !hasDependents && !hasRestrictions) return null;

                                    return (
                                      <TooltipProvider>
                                        <div className="border-t pt-2 space-y-2">
                                          {/* Compact Header with Risk and Summary */}
                                          <div className="flex items-center justify-between">
                                            <div className="flex items-center gap-2">
                                              <GitBranch className="h-3 w-3 text-slate-400" />
                                              <span className="text-xs font-medium text-slate-300">
                                                {feature.dependencies?.length || 0} deps • {feature.dependent_features?.length || 0} dependents
                                                {hasRestrictions && ` • ${feature.environment_restrictions?.length || 0} restrictions`}
                                              </span>
                                            </div>
                                            <div className="flex items-center gap-2">
                                              {/* Risk Indicator */}
                                              <Tooltip>
                                                <TooltipTrigger asChild>
                                                  <div className={`h-2 w-2 rounded-full ${
                                                    risk.riskLevel === 'high' ? 'bg-red-400' :
                                                    risk.riskLevel === 'medium' ? 'bg-amber-400' :
                                                    'bg-emerald-400'
                                                  }`} />
                                                </TooltipTrigger>
                                                <TooltipContent>
                                                  <div className="space-y-1 text-xs">
                                                    <div><strong>Risk Level:</strong> {risk.riskLevel.toUpperCase()}</div>
                                                    {risk.missingDeps.length > 0 && <div>Missing {risk.missingDeps.length} dependencies</div>}
                                                    {risk.affectedDependents.length > 0 && <div>Affects {risk.affectedDependents.length} dependents</div>}
                                                  </div>
                                                </TooltipContent>
                                              </Tooltip>
                                              {/* Warning Count */}
                                              {(risk.missingDeps.length > 0 || risk.affectedDependents.length > 0) && (
                                                <Tooltip>
                                                  <TooltipTrigger asChild>
                                                    <Badge variant="outline" className="h-5 px-1 text-xs bg-amber-900/30 border-amber-500/50 text-amber-300">
                                                      ⚠ {risk.missingDeps.length + risk.affectedDependents.length}
                                                    </Badge>
                                                  </TooltipTrigger>
                                                  <TooltipContent>
                                                    <div className="space-y-1 text-xs">
                                                      {risk.missingDeps.length > 0 && <div>{risk.missingDeps.length} missing dependencies</div>}
                                                      {risk.affectedDependents.length > 0 && <div>{risk.affectedDependents.length} affected dependents</div>}
                                                    </div>
                                                  </TooltipContent>
                                                </Tooltip>
                                              )}
                                            </div>
                                          </div>

                                          {/* Compact Dependencies */}
                                          {(hasDependencies || hasDependents || hasRestrictions) && (
                                            <div className="flex flex-wrap gap-1">
                                              {/* Dependencies */}
                                              {hasDependencies && (
                                                <div className="flex items-center gap-1">
                                                  <span className="text-xs text-blue-400">↑</span>
                                                  {feature.dependencies.map((dep, _index) => {
                                                    const depFeature = featureManagement?.features[dep];
                                                    const isEnabled = depFeature?.enabled;

                                                    return (
                                                      <Tooltip key={dep}>
                                                        <TooltipTrigger asChild>
                                                          <Badge
                                                            variant="outline"
                                                            className={`h-5 px-1.5 text-xs cursor-help transition-colors ${isEnabled
                                                              ? 'bg-emerald-900/50 border-emerald-500/50 text-emerald-300 hover:bg-emerald-900/70'
                                                              : 'bg-red-900/50 border-red-500/50 text-red-300 hover:bg-red-900/70'
                                                            }`}
                                                          >
                                                            {isEnabled ? '✓' : '✗'} {dep}
                                                          </Badge>
                                                        </TooltipTrigger>
                                                        <TooltipContent>
                                                          <div className="space-y-1 text-xs">
                                                            <div><strong>Required:</strong> {dep}</div>
                                                            <div>Status: {isEnabled ? 'Enabled' : 'Disabled'}</div>
                                                            {depFeature?.category && <div>Category: {depFeature.category}</div>}
                                                            {depFeature?.description && <div className="max-w-48">{depFeature.description}</div>}
                                                          </div>
                                                        </TooltipContent>
                                                      </Tooltip>
                                                    );
                                                  })}
                                                </div>
                                              )}

                                              {/* Dependents */}
                                              {hasDependents && (
                                                <div className="flex items-center gap-1">
                                                  <span className="text-xs text-amber-400">↓</span>
                                                  {feature.dependent_features.map((dep, _index) => {
                                                    const depFeature = featureManagement?.features[dep];
                                                    const isEnabled = depFeature?.enabled;

                                                    return (
                                                      <Tooltip key={dep}>
                                                        <TooltipTrigger asChild>
                                                          <Badge
                                                            variant="outline"
                                                            className={`h-5 px-1.5 text-xs cursor-help transition-colors ${isEnabled
                                                              ? 'bg-emerald-900/50 border-emerald-500/50 text-emerald-300 hover:bg-emerald-900/70'
                                                              : 'bg-slate-800/50 border-slate-500/50 text-slate-400 hover:bg-slate-800/70'
                                                            }`}
                                                          >
                                                            {isEnabled ? '🟢' : '⚪'} {dep}
                                                          </Badge>
                                                        </TooltipTrigger>
                                                        <TooltipContent>
                                                          <div className="space-y-1 text-xs">
                                                            <div><strong>Dependent:</strong> {dep}</div>
                                                            <div>Status: {isEnabled ? 'Enabled' : 'Disabled'}</div>
                                                            {depFeature?.category && <div>Category: {depFeature.category}</div>}
                                                            {!feature.enabled && isEnabled && <div className="text-amber-300">⚠️ Will be affected if disabled</div>}
                                                          </div>
                                                        </TooltipContent>
                                                      </Tooltip>
                                                    );
                                                  })}
                                                </div>
                                              )}

                                              {/* Environment Restrictions */}
                                              {hasRestrictions && (
                                                <div className="flex items-center gap-1">
                                                  <span className="text-xs text-red-400">🚫</span>
                                                  {(feature.environment_restrictions || []).map((restriction) => (
                                                    <Tooltip key={restriction}>
                                                      <TooltipTrigger asChild>
                                                        <Badge className="h-5 px-1.5 text-xs bg-red-900/50 border-red-500/50 text-red-300 cursor-help">
                                                          {restriction}
                                                        </Badge>
                                                      </TooltipTrigger>
                                                      <TooltipContent>
                                                        <div className="text-xs">
                                                          <div><strong>Environment Restriction:</strong></div>
                                                          <div>Not available in: {restriction}</div>
                                                        </div>
                                                      </TooltipContent>
                                                    </Tooltip>
                                                  ))}
                                                </div>
                                              )}
                                            </div>
                                          )}

                                        </div>
                                      </TooltipProvider>
                                    );
                                  })()}
                                </div>
                                <div className="ml-6 flex-shrink-0 flex flex-col items-center gap-2">
                                  <div className="text-xs text-muted-foreground text-center">
                                    {feature.enabled ? 'Disable' : 'Enable'}
                                  </div>
                                  <Switch
                                    checked={feature.enabled}
                                    onCheckedChange={(enabled) => handleFeatureToggle(featureName, enabled)}
                                    disabled={updateFeatureMutation.isPending}
                                    aria-label={`${feature.enabled ? 'Disable' : 'Enable'} ${feature.name}`}
                                    className="data-[state=checked]:bg-green-600"
                                  />
                                </div>
                              </div>
                            ))}
                          </div>
                        </CardContent>
                      )}
                    </Card>
                  );
                })}
              </div>
            ) : (
              <div className="text-center py-8 text-muted-foreground">
                {featuresLoading ? 'Loading features...' : 'No features available'}
              </div>
            )}
          </TabsContent>

          {/* CAN Interfaces Tab */}
          <TabsContent value="interfaces" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center">
                  <Network className="h-5 w-5 mr-2" />
                  CAN Interface Mappings
                </CardTitle>
                <CardDescription>
                  Current CAN bus interface configurations and status
                </CardDescription>
              </CardHeader>
              <CardContent>
                {interfacesLoading ? (
                  <div className="flex items-center justify-center py-8">
                    <RefreshCw className="h-6 w-6 animate-spin text-blue-600 mr-2" />
                    <span>Loading CAN interfaces...</span>
                  </div>
                ) : canInterfaces && canInterfaces.length > 0 ? (
                  <div className="space-y-4">
                    {canInterfaces.map((iface: CANInterfaceMapping) => (
                      <div key={iface.logical_name} className="p-4 border rounded-lg">
                        <div className="flex items-center justify-between mb-2">
                          <h4 className="font-medium">{iface.logical_name}</h4>
                          <Badge variant={iface.is_active ? 'default' : 'secondary'}>
                            {iface.is_active ? 'Active' : 'Inactive'}
                          </Badge>
                        </div>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                          <div>
                            <span className="text-muted-foreground">Physical:</span>
                            <span className="ml-2">{iface.physical_interface}</span>
                          </div>
                          <div>
                            <span className="text-muted-foreground">Bitrate:</span>
                            <span className="ml-2">{iface.bitrate}</span>
                          </div>
                          <div>
                            <span className="text-muted-foreground">Messages:</span>
                            <span className="ml-2">{iface.message_count}</span>
                          </div>
                          <div>
                            <span className="text-muted-foreground">Status:</span>
                            <span className="ml-2">{iface.validation_status}</span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-8 text-muted-foreground">
                    {interfacesLoading ? 'Loading interfaces...' : 'No CAN interfaces configured'}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Protocols Tab */}
          <TabsContent value="protocols" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center">
                  <Shield className="h-5 w-5 mr-2" />
                  Protocol Configuration
                </CardTitle>
                <CardDescription>
                  Multi-protocol support and configuration status
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="text-center py-8 text-muted-foreground">
                  Protocol configuration coming soon
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Coach Configuration Tab */}
          <TabsContent value="coach" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center">
                  <Database className="h-5 w-5 mr-2" />
                  Coach Configuration
                </CardTitle>
                <CardDescription>
                  Vehicle-specific configuration and device mappings
                </CardDescription>
              </CardHeader>
              <CardContent>
                {coachLoading ? (
                  <div className="flex items-center justify-center py-8">
                    <RefreshCw className="h-6 w-6 animate-spin text-blue-600 mr-2" />
                    <span>Loading coach configuration...</span>
                  </div>
                ) : coachConfig ? (
                  <div className="space-y-4">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <h4 className="font-semibold">Vehicle Information</h4>
                        <div className="text-sm space-y-1">
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Manufacturer:</span>
                            <span>{coachConfig.manufacturer || 'N/A'}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Model:</span>
                            <span>{coachConfig.model || 'N/A'}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Year:</span>
                            <span>{coachConfig.year || 'N/A'}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Config File:</span>
                            <span>{coachConfig.config_file || 'N/A'}</span>
                          </div>
                        </div>
                      </div>
                      <div className="space-y-2">
                        <h4 className="font-semibold">System Configuration</h4>
                        <div className="text-sm space-y-1">
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Device Mappings:</span>
                            <span>{Object.keys(coachConfig.device_mappings || {}).length}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Interface Requirements:</span>
                            <span>{coachConfig.interface_requirements?.length || 0}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Validation Status:</span>
                            <Badge variant={coachConfig.validation_status === 'valid' ? 'default' : 'destructive'}>
                              {coachConfig.validation_status || 'Unknown'}
                            </Badge>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="text-center py-8 text-muted-foreground">
                    {coachLoading ? 'Loading coach configuration...' : 'No coach configuration available'}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

        </Tabs>
      </div>
    </AppLayout>
  );
}
