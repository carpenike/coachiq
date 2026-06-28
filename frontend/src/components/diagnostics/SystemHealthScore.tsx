/**
 * System Health Score Component
 *
 * Displays a comprehensive system health visualization with 0.0-1.0 scoring,
 * subsystem breakdown, and real-time status indicators following modern
 * CAN bus diagnostic interface patterns.
 */

import React from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import {
  Activity,
  AlertCircle,
  CheckCircle,
  AlertTriangle,
  RefreshCw,
  TrendingUp,
  TrendingDown,
  Minus
} from 'lucide-react';
import type {
  DiagnosticFaultSummarySchema,
  DiagnosticsSystemStatusSchema
} from '@/api/types/domains';

interface SystemHealthScoreProps {
  systemStatus: DiagnosticsSystemStatusSchema;
  faultSummary: DiagnosticFaultSummarySchema;
  isLoading?: boolean;
  onRefresh?: () => void;
  showSubsystems?: boolean;
  showRecommendations?: boolean;
  compact?: boolean;
}

// Health status configuration
const getHealthConfig = (score: number, status: string) => {
  if (status === 'critical' || score < 0.5) {
    return {
      color: 'text-red-500',
      bgColor: 'bg-red-50 border-red-200',
      progressColor: 'bg-red-500',
      icon: AlertCircle,
      label: 'Critical',
      trend: 'down' as const
    };
  } else if (status === 'warning' || score < 0.8) {
    return {
      color: 'text-yellow-500',
      bgColor: 'bg-yellow-50 border-yellow-200',
      progressColor: 'bg-yellow-500',
      icon: AlertTriangle,
      label: 'Warning',
      trend: 'stable' as const
    };
  } else {
    return {
      color: 'text-green-500',
      bgColor: 'bg-green-50 border-green-200',
      progressColor: 'bg-green-500',
      icon: CheckCircle,
      label: 'Healthy',
      trend: 'up' as const
    };
  }
};

const getTrendIcon = (trend: 'up' | 'down' | 'stable') => {
  switch (trend) {
    case 'up': return TrendingUp;
    case 'down': return TrendingDown;
    default: return Minus;
  }
};

const normalizeHealthScore = (healthScore: number) => Math.max(0, Math.min(1, healthScore / 100));

const diagnosticsHealthToWidgetStatus = (overallHealth: string) => {
  switch (overallHealth) {
    case 'excellent':
    case 'good':
      return 'healthy';
    case 'fair':
      return 'warning';
    case 'poor':
    case 'critical':
      return 'critical';
    default:
      return 'warning';
  }
};

const buildSystemScores = (
  systemStatus: DiagnosticsSystemStatusSchema,
  faultSummary: DiagnosticFaultSummarySchema
) => {
  const degradedSystems = new Set(systemStatus.degraded_systems);
  const scoreMap = new Map<string, number>();

  systemStatus.active_systems.forEach((system) => {
    scoreMap.set(system, degradedSystems.has(system) ? 0.5 : 1);
  });

  Object.entries(faultSummary.by_system).forEach(([system, faultCount]) => {
    if (faultCount > 0) {
      const degradedScore = faultSummary.critical_faults > 0 ? 0.25 : 0.5;
      scoreMap.set(system, Math.min(scoreMap.get(system) ?? 1, degradedScore));
    }
  });

  return Object.fromEntries(scoreMap);
};

const getSubsystemStatusColor = (score: number) => {
  if (score >= 0.7) {
    return 'bg-green-500';
  }
  if (score >= 0.5) {
    return 'bg-yellow-500';
  }
  return 'bg-red-500';
};

const buildRecommendations = (
  systemStatus: DiagnosticsSystemStatusSchema,
  faultSummary: DiagnosticFaultSummarySchema
) => {
  const recommendations: string[] = [];

  if (faultSummary.critical_faults > 0) {
    recommendations.push(`Address ${faultSummary.critical_faults} critical diagnostic fault(s).`);
  }
  if (faultSummary.active_faults > 0) {
    recommendations.push(`Review ${faultSummary.active_faults} active diagnostic fault(s).`);
  }
  if (systemStatus.degraded_systems.length > 0) {
    recommendations.push(`Investigate degraded systems: ${systemStatus.degraded_systems.join(', ')}.`);
  }

  return recommendations;
};


// Compact version for dashboard widgets
const CompactHealthScore: React.FC<SystemHealthScoreProps> = ({
  systemStatus,
  faultSummary,
  isLoading,
  onRefresh
}) => {
  const healthScore = normalizeHealthScore(systemStatus.health_score);
  const status = diagnosticsHealthToWidgetStatus(systemStatus.overall_health);
  const healthConfig = getHealthConfig(healthScore, status);
  const HealthIcon = healthConfig.icon;
  const TrendIcon = getTrendIcon(healthConfig.trend);

  if (isLoading) {
    return (
      <Card className="w-full">
        <CardContent className="p-4">
          <div className="flex items-center space-x-3">
            <div className="animate-pulse bg-gray-200 rounded-full h-10 w-10" />
            <div className="flex-1 space-y-2">
              <div className="animate-pulse bg-gray-200 h-4 rounded w-20" />
              <div className="animate-pulse bg-gray-200 h-2 rounded w-full" />
            </div>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className={`w-full ${healthConfig.bgColor}`}>
      <CardContent className="p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="relative">
              <HealthIcon className={`h-10 w-10 ${healthConfig.color}`} />
              <TrendIcon className={`h-4 w-4 ${healthConfig.color} absolute -bottom-1 -right-1 bg-white rounded-full p-0.5`} />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <span className="text-2xl font-bold">
                  {Math.round(healthScore * 100)}%
                </span>
                <Badge variant="outline" className="text-xs">
                  {healthConfig.label}
                </Badge>
              </div>
              <Progress
                value={healthScore * 100}
                className="w-32 h-1 mt-1"
              />
            </div>
          </div>
          {onRefresh && (
            <Button variant="ghost" size="sm" onClick={onRefresh}>
              <RefreshCw className="h-4 w-4" />
            </Button>
          )}
        </div>

        {faultSummary.active_faults > 0 && (
          <div className="mt-3 pt-3 border-t">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Active Issues</span>
              <Badge variant="secondary">{faultSummary.active_faults} DTCs</Badge>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

// Full version for detailed views
const FullHealthScore: React.FC<SystemHealthScoreProps> = ({
  systemStatus,
  faultSummary,
  isLoading,
  onRefresh,
  showSubsystems = true,
  showRecommendations = true
}) => {
  const healthScore = normalizeHealthScore(systemStatus.health_score);
  const status = diagnosticsHealthToWidgetStatus(systemStatus.overall_health);
  const systemScores = buildSystemScores(systemStatus, faultSummary);
  const recommendations = buildRecommendations(systemStatus, faultSummary);
  const healthConfig = getHealthConfig(healthScore, status);
  const HealthIcon = healthConfig.icon;
  const TrendIcon = getTrendIcon(healthConfig.trend);

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Activity className="h-5 w-5" />
            System Health
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <div className="animate-pulse bg-gray-200 h-4 rounded" />
            <div className="animate-pulse bg-gray-200 h-20 rounded" />
            <div className="animate-pulse bg-gray-200 h-32 rounded" />
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className={healthConfig.bgColor}>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Activity className="h-5 w-5" />
            System Health
          </div>
          {onRefresh && (
            <Button variant="ghost" size="sm" onClick={onRefresh}>
              <RefreshCw className="h-4 w-4" />
            </Button>
          )}
        </CardTitle>
        <CardDescription>
          Overall system health and performance monitoring
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-6">
          {/* Main Health Score Display */}
          <div className="text-center">
            <div className="flex items-center justify-center gap-3 mb-2">
              <div className="relative">
                <HealthIcon className={`h-12 w-12 ${healthConfig.color}`} />
                <TrendIcon className={`h-5 w-5 ${healthConfig.color} absolute -bottom-1 -right-1 bg-white rounded-full p-0.5`} />
              </div>
              <div>
                <div className="text-4xl font-bold">
                  {Math.round(healthScore * 100)}%
                </div>
                <Badge variant="outline" className="mt-1">
                  {healthConfig.label}
                </Badge>
              </div>
            </div>
            <Progress
              value={healthScore * 100}
              className="w-full h-3 mb-2"
            />
            <p className="text-sm text-muted-foreground">
              System Health Score • Last assessed {new Date(systemStatus.last_assessment * 1000).toLocaleTimeString()}
            </p>
          </div>

          {/* Subsystem Health Breakdown */}
          {showSubsystems && Object.keys(systemScores).length > 0 && (
            <>
              <Separator />
              <div>
                <h4 className="text-sm font-medium mb-3 flex items-center gap-2">
                  <Activity className="h-4 w-4" />
                  Subsystem Health
                </h4>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {Object.entries(systemScores).map(([system, score]) => {
                    return (
                      <div key={system} className="flex items-center justify-between p-3 rounded border bg-white/50">
                        <div className="flex items-center gap-2">
                          <div className={`h-2 w-2 rounded-full ${getSubsystemStatusColor(score)}`} />
                          <span className="text-sm capitalize font-medium">
                            {system.replace(/_/g, ' ')}
                          </span>
                        </div>
                        <div className="flex items-center gap-2">
                          <Progress value={score * 100} className="w-16 h-2" />
                          <span className="text-xs font-medium w-8 text-right">
                            {Math.round(score * 100)}%
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </>
          )}

          {/* Active Issues Alert */}
          {faultSummary.active_faults > 0 && (
            <>
              <Separator />
              <div className="flex items-center justify-between p-3 rounded border border-orange-200 bg-orange-50">
                <div className="flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4 text-orange-500" />
                  <span className="text-sm font-medium">Active Diagnostic Issues</span>
                </div>
                <Badge variant="secondary">{faultSummary.active_faults} DTCs require attention</Badge>
              </div>
            </>
          )}

          {/* System Recommendations */}
          {showRecommendations && recommendations.length > 0 && (
            <>
              <Separator />
              <div>
                <h4 className="text-sm font-medium mb-3 flex items-center gap-2">
                  <CheckCircle className="h-4 w-4" />
                  System Recommendations
                </h4>
                <div className="space-y-2">
                  {recommendations.slice(0, 4).map((recommendation, index) => (
                    <div key={index} className="flex items-start gap-2 p-2 rounded bg-white/50 text-sm">
                      <div className="h-1.5 w-1.5 rounded-full bg-blue-500 mt-2 flex-shrink-0" />
                      <span className="text-muted-foreground">{recommendation}</span>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}

          {/* Health Status Summary */}
          <div className="pt-2 border-t bg-white/30 -mx-6 px-6 py-3 rounded-b-lg">
            <div className="grid grid-cols-3 gap-4 text-center">
              <div>
                <div className="text-lg font-semibold">{Object.keys(systemScores).length}</div>
                <div className="text-xs text-muted-foreground">Monitored Systems</div>
              </div>
              <div>
                <div className={`text-lg font-semibold ${faultSummary.active_faults > 0 ? 'text-red-500' : 'text-green-500'}`}>
                  {faultSummary.active_faults}
                </div>
                <div className="text-xs text-muted-foreground">Active Issues</div>
              </div>
              <div>
                <div className="text-lg font-semibold">{recommendations.length}</div>
                <div className="text-xs text-muted-foreground">Recommendations</div>
              </div>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

// Main component that chooses between compact and full views
export const SystemHealthScore: React.FC<SystemHealthScoreProps> = (props) => {
  if (props.compact) {
    return <CompactHealthScore {...props} />;
  }
  return <FullHealthScore {...props} />;
};

export default SystemHealthScore;
